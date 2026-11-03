"""Командная строка независимого прототипа генератора школьных мероприятий.

Публичные команды ``generate`` и ``compose`` всегда используют штатный режим
``context_mode=full`` и включённый культурный контекст. Режимы H2/H3 доступны только
через отдельную команду ``experiment`` и не могут попасть во внешний контракт 01.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .catalog import Catalog, CatalogError
from .contracts import llm as c03
from .contracts.request import GenerationRequest
from .llm.client import LLMError, build_client, strict_schema
from .normalize import RequestError, normalize
from .prompting.composer import Composer
from .render import render_variant
from .settings import Settings
from .sources import check_sources
from .trace import RunTrace
from .validation.checks import report_status, validate_variant


def _load(path: str) -> dict[str, Any]:
    """Читает UTF-8 JSON-файл и возвращает корневой объект.

    Параметры:
        path: Путь к JSON-файлу.

    Возвращает:
        Десериализованный JSON-объект.
    """
    with open(path, encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _print(obj: Any) -> None:
    """Печатает объект как форматированный UTF-8 JSON без ASCII-экранирования."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def _package_from(path: str) -> dict[str, Any]:
    """Извлекает variant_package из эталонного файла или возвращает сам объект."""
    data = _load(path)
    if "variant_package" in data:
        return data["variant_package"]
    return data


def _job_id() -> str:
    """Создаёт локальный уникальный идентификатор задачи для трассировки прототипа."""
    return f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def cmd_serve(args: argparse.Namespace, settings: Settings) -> int:
    """Запускает внутренний HTTP-сервис для основного Backend Severus.

    Параметры:
        args: Аргументы ``--host`` и ``--port``.
        settings: Настройки LLM-сервиса.

    Возвращает:
        Код завершения процесса.
    """
    import uvicorn

    from .http_api import create_app

    host = args.host or settings.get("SERVICE_HOST", "127.0.0.1")
    port = args.port or int(settings.get("SERVICE_PORT", "8090"))
    log_level = (settings.get("APP_LOG_LEVEL", "INFO") or "INFO").lower()
    uvicorn.run(create_app(settings), host=host, port=port, log_level=log_level)
    return 0


def cmd_health(args: argparse.Namespace, settings: Settings) -> int:
    """Проверяет доступность выбранной модели и выводит сведения о подключении."""
    try:
        client = build_client(settings, args.model)
        _print({"status": "ok", **client.health()})
        return 0
    except LLMError as exc:
        _print({"status": "error", "code": exc.code, "message": exc.message})
        return 2


def cmd_compose(args: argparse.Namespace, settings: Settings) -> int:
    """Собирает prompt выбранного этапа в штатном режиме без вызова LLM.

    Команда предназначена для отладки блоков. Она всегда использует full-контекст
    и культурный контур, как обычная генерация через будущий HTTP API.
    """
    catalog = Catalog.load(settings)
    normalized = normalize(_load(args.request), catalog, settings, context_mode="full", cultural_context=True)
    composer = Composer(settings, catalog)
    output_vars = {
        "variant_id": "v1",
        "block_id": "block_01",
        "start_minute": "0",
        "block_minutes": "5",
    }
    stage_input = ""
    if args.stage != "variation_plan":
        stage_input = "## Вход этапа\nЗдесь будет результат предыдущего этапа."
    composed = composer.compose(args.stage, normalized, stage_input=stage_input, output_vars=output_vars)
    if args.json:
        _print({
            "messages": composed.messages,
            "manifest": composed.manifest,
            "context": composed.context_metadata,
            "manifest_hash": composed.manifest_hash,
        })
    else:
        sys.stdout.write(composed.as_markdown() + "\n\n===== MANIFEST =====\n")
        for item in composed.manifest:
            sys.stdout.write(f"{item['id']} {item['version']} {item['path']}\n")
        sys.stdout.write("\n===== CONTEXT =====\n")
        sys.stdout.write(json.dumps(composed.context_metadata, ensure_ascii=False, indent=2) + "\n")
    return 0


def _build_client_for_generation(args: argparse.Namespace, settings: Settings):
    """Создаёт реальный или fixture-клиент для команды генерации.

    Fixture-режим используется только в тестах и локальной отладке конвейера без
    запущенной LLM. Обычный режим выбирает модель через Model Router.
    """
    fixture_paths = getattr(args, "fixture", None)
    if fixture_paths:
        from .llm.fixture import FixtureLLM

        broken = {stage: 1 for stage in (getattr(args, "broken", None) or [])}
        return FixtureLLM([_load(path) for path in fixture_paths], broken=broken)
    return build_client(settings, getattr(args, "model", None))


def _run_generation(
    args: argparse.Namespace,
    settings: Settings,
    *,
    context_mode: str,
    cultural_context: bool,
    experiment_tag: str | None = None,
    experiment_pair_id: str | None = None,
) -> int:
    """Запускает полный независимый конвейер с заданными внутренними режимами.

    Параметры:
        args: Аргументы CLI с путём запроса, моделью и настройками трассы.
        settings: Конфигурация сервиса.
        context_mode: ``full`` или ``universal``. Не берётся из входного JSON.
        cultural_context: Включать ли культурный контур.
        experiment_tag: Внутренняя метка эксперимента H2/H3.
        experiment_pair_id: ID пары для слепого сравнения двух экспериментальных запусков.

    Возвращает:
        Код процесса: 0 при полном успехе, 1 при partial/failed, 2 при ошибке модели,
        3 при ошибке входного запроса.
    """
    from .generation.pipeline import Generator, StageFailed

    catalog = Catalog.load(settings)
    client = _build_client_for_generation(args, settings)
    raw_request = _load(args.request)
    job_id = _job_id()
    no_trace = bool(getattr(args, "no_trace", False))
    run_dir = None if no_trace else settings.data_dir / "runs" / job_id
    trace = RunTrace(
        run_dir,
        full_prompts=settings.flag("LOG_FULL_PROMPTS", True),
        full_responses=settings.flag("LOG_FULL_RESPONSES", True),
        secrets=settings.secret_values(),
    )
    generator = Generator(settings, catalog, client, trace=trace)
    try:
        outcome = generator.run(
            raw_request,
            job_id=job_id,
            context_mode=context_mode,
            cultural_context=cultural_context,
            experiment_tag=experiment_tag,
            experiment_pair_id=experiment_pair_id,
        )
    except RequestError as exc:
        _print(exc.to_dict())
        return 3
    except LLMError as exc:
        _print({"error": {"code": exc.code, "message": exc.message, "field": None, "retryable": exc.retryable}})
        return 2
    except StageFailed as exc:
        # Ответ модели не прошёл схему на общем этапе (до вариантов): понятная ошибка вместо трассировки Python.
        _print({"job_id": job_id, "status": "failed", "llm_calls": generator.calls, "tokens": generator.tokens.totals(),
                "error": {"code": exc.code, "stage": exc.stage, "message": str(exc), "field": None, "retryable": True},
                "trace_dir": str(run_dir) if run_dir else None})
        return 2

    if run_dir:
        from .markdown import variant_to_markdown

        for variant in outcome.project["variants"]:
            markdown = variant_to_markdown(variant, outcome.project["input"], outcome.normalized.event_title)
            trace.write_text(f"variants/{variant['variant_id']}/scenario.md", markdown)

    out_argument = getattr(args, "out", None)
    out_path = Path(out_argument) if out_argument else (run_dir / "final_result.json" if run_dir else None)
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(outcome.project, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "job_id": outcome.job_id,
        "status": outcome.project["status"],
        "requested_variants": outcome.project["requested_variants"],
        "completed_variants": outcome.project["completed_variants"],
        "llm_calls": outcome.calls,
        "duration_ms": outcome.duration_ms,
        "tokens": outcome.tokens,
        "result_file": str(out_path) if out_path else None,
        "trace_dir": outcome.run_dir,
        "context_mode": context_mode,
        "cultural_context": cultural_context,
        "experiment_tag": experiment_tag,
        "experiment_pair_id": experiment_pair_id,
        "warnings": outcome.warnings,
        "variants": [
            {
                "variant_id": variant.variant_id,
                "status": variant.status,
                "error": variant.error,
                "issues": [
                    f"{issue.severity}:{issue.code}:{issue.location}"
                    for issue in variant.issues
                    if issue.severity != "info"
                ],
            }
            for variant in outcome.variants
        ],
    }
    _print(summary)
    return 0 if outcome.project["status"] == "completed" else 1


def cmd_generate(args: argparse.Namespace, settings: Settings) -> int:
    """Запускает штатную генерацию с full-контекстом и культурным контуром."""
    return _run_generation(args, settings, context_mode="full", cultural_context=True)


def _batch_files(paths: list[str]) -> list[Path]:
    """Файлы запросов: указанные файлы и все `*.json` из указанных папок (по алфавиту)."""
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        files += sorted(path.glob("*.json")) if path.is_dir() else [path]
    return files


def cmd_batch(args: argparse.Namespace, settings: Settings) -> int:
    """Прогоняет набор запросов подряд и печатает сводную таблицу.

    Каждый запрос идёт тем же путём, что `generate` (с трассой и строкой в `runs.jsonl`).
    Сводка сохраняется в `data/runs/batch_<время>.md` и `.json`.
    Код возврата: 0 - все `completed`, 1 - есть `partial`/`failed`/ошибки.
    """
    import contextlib
    import io
    import time

    rows: list[dict[str, Any]] = []
    files = _batch_files(args.requests)
    for index, path in enumerate(files, 1):
        sys.stderr.write(f"[{index}/{len(files)}] {path.name} ...\n")
        run_args = argparse.Namespace(request=str(path), out=None, model=args.model, fixture=args.fixture,
                                      broken=None, no_trace=False)
        captured = io.StringIO()
        started = time.monotonic()
        with contextlib.redirect_stdout(captured):
            code = _run_generation(run_args, settings, context_mode="full", cultural_context=True)
        elapsed = round(time.monotonic() - started, 1)
        try:
            summary = json.loads(captured.getvalue())
        except json.JSONDecodeError:
            summary = {}
        issues = [i for v in summary.get("variants", []) for i in v.get("issues", [])]
        error = summary.get("error") or {}
        rows.append({
            "request": path.name,
            "job_id": summary.get("job_id"),
            "status": summary.get("status") or "error",
            "llm_calls": summary.get("llm_calls"),
            "duration_s": round(summary["duration_ms"] / 1000, 1) if summary.get("duration_ms") else elapsed,
            "tokens": (summary.get("tokens") or {}).get("total"),
            "critical": sorted({i.split(":")[1] for i in issues if i.startswith("critical:")}),
            "warnings": sorted({i.split(":")[1] for i in issues if i.startswith("warning:")}),
            "error": error.get("code"),
            "error_message": error.get("message"),
            "variant_errors": [f"{v.get('variant_id')}: {v.get('error')}" for v in summary.get("variants", [])
                               if v.get("status") != "completed" and v.get("error")],
            "exit_code": code,
        })
        reason = f": {error.get('code')} - {error.get('message')}" if error else ""
        if not reason and rows[-1]["variant_errors"]:
            reason = ": " + "; ".join(rows[-1]["variant_errors"])
        sys.stderr.write(f"    -> {rows[-1]['status']} ({rows[-1]['duration_s']} с){reason}\n")

    lines = ["| Запрос | Статус | Вызовов | Время, с | Токены | Критичные | Предупреждения |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        crit = ", ".join(r["critical"]) or ("ошибка " + r["error"] if r["error"] else "; ".join(r["variant_errors"]) or "-")
        lines.append(f"| {r['request']} | {r['status']} | {r['llm_calls'] or '-'} | {r['duration_s']} | {r['tokens'] or '-'} | "
                     f"{crit} | {', '.join(r['warnings']) or '-'} |")
    done = sum(r["status"] == "completed" for r in rows)
    table = "\n".join(lines) + f"\n\nИтого: completed {done} из {len(rows)}."
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = settings.data_dir / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"batch_{stamp}.md").write_text(table, encoding="utf-8")
    (out_dir / f"batch_{stamp}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stdout.write(table + f"\n\nСводка: {out_dir / f'batch_{stamp}.md'}\n")
    return 0 if rows and done == len(rows) else 1


def cmd_experiment(args: argparse.Namespace, settings: Settings) -> int:
    """Запускает внутренний эксперимент H2/H3 без изменения публичного контракта 01."""
    cultural_context = args.cultural_context == "on"
    tag = args.experiment_tag or (
        "H2" if args.context_mode == "universal" else "H3" if not cultural_context else "manual"
    )
    return _run_generation(
        args,
        settings,
        context_mode=args.context_mode,
        cultural_context=cultural_context,
        experiment_tag=tag,
        experiment_pair_id=args.experiment_pair_id,
    )


def cmd_validate(args: argparse.Namespace, settings: Settings, render_output: bool = False) -> int:
    """Проверяет готовый внутренний вариант и при необходимости рендерит контракт 02."""
    catalog = Catalog.load(settings)
    normalized = normalize(_load(args.request), catalog, settings)
    package = c03.VariantPackage.model_validate(_package_from(args.package)).model_dump()
    issues = validate_variant(package["variant"], normalized, catalog, settings.generation())
    if render_output:
        variant = render_variant(package["variant"], normalized, catalog, issues)
        if getattr(args, "markdown", False):
            from .markdown import variant_to_markdown

            sys.stdout.write(variant_to_markdown(variant, normalized.effective_input, normalized.event_title))
        else:
            _print(variant)
    else:
        _print({"status": report_status(issues), "issues": [issue.to_dict() for issue in issues]})
    return 0 if report_status(issues) != "blocked" else 1


def cmd_export_schemas(args: argparse.Namespace, settings: Settings) -> int:
    """Перегенерирует JSON Schema входного контракта и всех этапов контракта 03."""
    del args
    out_dir = settings.root / "schemas"
    out_dir.mkdir(exist_ok=True)
    targets: dict[str, type] = {"generation_request.schema.json": GenerationRequest}
    targets.update({f"{name}.schema.json": model for name, model in c03.STAGE_MODELS.items()})
    for file_name, model in targets.items():
        schema = model.model_json_schema()
        if file_name != "generation_request.schema.json":
            schema = strict_schema(schema)
        schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", **schema}
        (out_dir / file_name).write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
        sys.stdout.write(f"schemas/{file_name}\n")
    return 0


def cmd_catalog_check(args: argparse.Namespace, settings: Settings) -> int:
    """Загружает общий каталог так же, как при генерации, и печатает сводку по событиям.

    Возвращает 0, если каталог подходит генератору; при ошибках `main` печатает список проблем и возвращает 4.
    """
    catalog = Catalog.load(settings)
    verified = sum(1 for f in catalog.fragments.values() if f.get("verification_status") == "verified")
    _print({
        "status": "ok",
        "catalog_dir": str(settings.catalog_dir),
        "events": sorted(catalog.events),
        "sources": len(catalog.sources),
        "fragments": {"total": len(catalog.fragments), "verified": verified},
    })
    return 0


def cmd_sources_check(args: argparse.Namespace, settings: Settings) -> int:
    """Проверяет локальный корпус источников и выводит покрытие каталога."""
    del args
    report = check_sources(settings)
    _print(report)
    return 0 if report["status"] == "ok" else 1


def _add_generation_arguments(parser: argparse.ArgumentParser) -> None:
    """Добавляет общие параметры реальной и fixture-генерации в CLI-парсер."""
    parser.add_argument("request")
    parser.add_argument("--out")
    parser.add_argument("--model")
    parser.add_argument("--fixture", nargs="*", help="эталоны вместо модели, например examples/golden/ex1_knowledge_day.json")
    parser.add_argument("--broken", nargs="*", help="с --fixture: этапы, первый ответ которых будет намеренно повреждён")
    parser.add_argument("--no-trace", action="store_true")


def main(argv: list[str] | None = None) -> int:
    """Разбирает CLI, загружает настройки и выполняет выбранную команду."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="python -m app", description="Прототип генератора школьных мероприятий")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    serve = subparsers.add_parser("serve", help="запустить внутренний HTTP-сервис")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)

    health = subparsers.add_parser("health", help="проверить подключение к выбранной модели")
    health.add_argument("--model")

    compose = subparsers.add_parser("compose", help="собрать штатный prompt без вызова модели")
    compose.add_argument("request")
    compose.add_argument(
        "--stage",
        default="variation_plan",
        choices=["variation_plan", "scenario_plan", "scenario_blocks", "scenario_block", "materials", "quality_review"],
    )
    compose.add_argument("--json", action="store_true")

    generate = subparsers.add_parser("generate", help="запустить штатную генерацию")
    _add_generation_arguments(generate)

    batch = subparsers.add_parser("batch", help="прогнать набор запросов и вывести сводную таблицу")
    batch.add_argument("requests", nargs="+", help="файлы запросов или папки с ними, например examples/requests/matrix")
    batch.add_argument("--model")
    batch.add_argument("--fixture", nargs="*", help="эталоны вместо модели (для проверки самого прогона)")

    experiment = subparsers.add_parser("experiment", help="запустить внутренний эксперимент H2/H3")
    _add_generation_arguments(experiment)
    experiment.add_argument("--context-mode", required=True, choices=["full", "universal"])
    experiment.add_argument("--cultural-context", default="on", choices=["on", "off"])
    experiment.add_argument("--experiment-tag")
    experiment.add_argument("--experiment-pair-id")

    for name in ("validate", "render"):
        command = subparsers.add_parser(name)
        command.add_argument("package")
        command.add_argument("--request", required=True)
        if name == "render":
            command.add_argument("--markdown", action="store_true", help="читаемая версия вместо JSON")

    subparsers.add_parser("export-schemas", help="обновить JSON Schema")
    subparsers.add_parser("sources-check", help="проверить кураторский корпус источников")
    subparsers.add_parser("catalog-check", help="проверить, что общий каталог событий подходит генератору")

    args = parser.parse_args(argv)
    settings = Settings.load()
    try:
        if args.cmd == "serve":
            return cmd_serve(args, settings)
        if args.cmd == "health":
            return cmd_health(args, settings)
        if args.cmd == "compose":
            return cmd_compose(args, settings)
        if args.cmd == "generate":
            return cmd_generate(args, settings)
        if args.cmd == "batch":
            return cmd_batch(args, settings)
        if args.cmd == "experiment":
            return cmd_experiment(args, settings)
        if args.cmd == "validate":
            return cmd_validate(args, settings)
        if args.cmd == "render":
            return cmd_validate(args, settings, render_output=True)
        if args.cmd == "export-schemas":
            return cmd_export_schemas(args, settings)
        if args.cmd == "sources-check":
            return cmd_sources_check(args, settings)
        if args.cmd == "catalog-check":
            return cmd_catalog_check(args, settings)
    except RequestError as exc:
        _print(exc.to_dict())
        return 3
    except CatalogError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 4
    return 2