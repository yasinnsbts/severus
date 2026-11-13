"""Внутренний HTTP API LLM-сервиса для подключения к основному Backend Severus.

Frontend не обращается к этому приложению напрямую. Общий Backend передаёт сюда
тот же JSON контракта 01 и получает ответы контракта 02 без преобразования полей.

Параллельная работа (`config/service.json`): генерации выполняются в собственном пуле потоков
на `max_parallel_generations` мест - столько задач идут сразу, без очереди. Следующие
`max_waiting_generations` задач ждут со статусом `queued`; если занято и это, создание задачи
отвечает 503 `SERVICE_BUSY` (retryable). Каждая задача изолирована: свой `job_id` и `project_id`,
свой генератор, клиент модели и папка трассы; общие только каталог (только чтение) и пределы.
Статусы и проекты хранятся в памяти `results_keep_hours` часов после завершения.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import job_status
from .catalog import Catalog
from .generation.pipeline import Generator
from .llm import limits
from .llm.client import LLMClient, LLMError, build_client
from .llm.fixture import FixtureLLM
from .normalize import RequestError, normalize
from .settings import Settings
from .trace import RunTrace

ClientFactory = Callable[[], LLMClient]


def _error(code: str, message: str, field: str | None = None, retryable: bool = False) -> dict[str, Any]:
    """Формирует единый внутренний формат ошибки сервиса.

    Параметры:
        `code`, `message`, `field`, `retryable`.

    Возвращает:
        dict[str, Any].
    """
    return {"error": {"code": code, "message": message, "field": field, "retryable": retryable}}


def _fixture_paths(settings: Settings) -> list[Path]:
    """Возвращает список эталонных ответов для локального fixture-режима.

    Переменная ``LLM_SERVICE_FIXTURES`` может содержать пути через запятую.
    Если она не задана, используются три эталона из ``examples/golden``.

    Параметры:
        `settings`.

    Возвращает:
        list[Path].
    """
    configured = settings.get("LLM_SERVICE_FIXTURES")
    if configured:
        paths = []
        for item in configured.split(","):
            value = Path(item.strip())
            paths.append(value if value.is_absolute() else settings.root / value)
        return paths
    return [
        settings.root / "examples" / "golden" / "ex1_knowledge_day.json",
        settings.root / "examples" / "golden" / "ex2_mothers_day.json",
        settings.root / "examples" / "golden" / "ex3_labour_day.json",
    ]


def build_runtime_client(settings: Settings) -> LLMClient:
    """Создаёт клиент модели для HTTP-сервиса.

    В DEV можно включить ``LLM_SERVICE_FIXTURE_MODE=true`` и проверить полную
    интеграцию без реальной модели. В обычном режиме используется Model Router.

    Параметры:
        `settings`.

    Возвращает:
        LLMClient.
    """
    if settings.flag("LLM_SERVICE_FIXTURE_MODE", False):
        goldens = [json.loads(path.read_text(encoding="utf-8")) for path in _fixture_paths(settings)]
        return FixtureLLM(goldens, model_key="fixture_http")
    return build_client(settings)


def create_app(settings: Settings | None = None, client_factory: ClientFactory | None = None,
               service_config: dict[str, Any] | None = None) -> FastAPI:
    """Создаёт FastAPI-приложение внутреннего LLM-сервиса.

    Параметры:
        `settings`: Настройки сервиса. Если не переданы, читаются из окружения.
        `client_factory`: Фабрика LLM-клиента. Используется тестами для fixture.
        `service_config`: Поверх `config/service.json` (для тестов).

    Возвращает:
        FastAPI.
    """
    runtime_settings = settings or Settings.load()
    catalog = Catalog.load(runtime_settings)
    runtime_client_factory = client_factory or (lambda: build_runtime_client(runtime_settings))
    service_cfg = {**runtime_settings.service(), **(service_config or {})}
    limits.configure(service_cfg)
    max_parallel = int(service_cfg["max_parallel_generations"])
    max_waiting = int(service_cfg["max_waiting_generations"])
    keep_seconds = float(service_cfg["results_keep_hours"]) * 3600
    # Свой пул потоков: длинные генерации не занимают потоки, которые отвечают на запросы статуса.
    executor = ThreadPoolExecutor(max_workers=max_parallel, thread_name_prefix="generation")
    load_lock = threading.Lock()
    load = {"running": 0, "waiting": 0}
    finished_at: dict[str, float] = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(
        title="Severus School Events LLM Service",
        description="Внутренний сервис генерации сценариев школьных мероприятий",
        version="0.3.0",
        lifespan=lifespan,
    )
    app.state.settings = runtime_settings
    app.state.catalog = catalog
    app.state.client_factory = runtime_client_factory
    app.state.jobs = {}
    app.state.projects = {}
    app.state.service_config = service_cfg
    app.state.executor = executor

    @app.middleware("http")
    async def echo_request_id(request: Request, call_next):
        """Возвращает ``X-Request-Id`` основному Backend для сквозной корреляции логов."""
        response = await call_next(request)
        request_id = request.headers.get("X-Request-Id")
        if request_id:
            response.headers["X-Request-Id"] = request_id
        return response

    def require_service_token(x_service_token: str | None = Header(default=None)) -> None:
        """Проверяет межсервисный токен, если он настроен.

        Параметры:
            `x_service_token`: Значение заголовка ``X-Service-Token``.

        Исключения:
            HTTPException: Если настроенный токен не совпадает.
        """
        expected = runtime_settings.get("SERVICE_AUTH_TOKEN")
        if expected and x_service_token != expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_error("SERVICE_UNAUTHORIZED", "Неверный межсервисный токен")["error"],
            )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Преобразует ошибки FastAPI/Pydantic в стабильный контракт ошибки."""
        del request
        first = exc.errors()[0] if exc.errors() else {}
        location = [str(part) for part in first.get("loc", []) if part not in ("body", "query", "path")]
        field = ".".join(location) or None
        return JSONResponse(status_code=422, content=_error("VALIDATION_ERROR", "Некорректные параметры запроса", field))

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        """Сохраняет стабильный формат ошибок для ручных HTTPException."""
        del request
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            payload = _error(
                detail["code"],
                detail.get("message", "Ошибка запроса"),
                detail.get("field"),
                bool(detail.get("retryable", False)),
            )
        else:
            payload = _error("HTTP_ERROR", str(detail))
        return JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)

    def finish_generation(job_id: str, project_id: str, raw_request: dict[str, Any]) -> None:
        """Выполняет генерацию в фоне и обновляет состояние задачи.

        Параметры:
            `job_id`, `project_id`, `raw_request`.
        """
        job = app.state.jobs[job_id]
        job["status"] = "running"
        try:
            client = app.state.client_factory()
            trace = RunTrace(
                runtime_settings.data_dir / "runs" / job_id,
                full_prompts=runtime_settings.flag("LOG_FULL_PROMPTS", True),
                full_responses=runtime_settings.flag("LOG_FULL_RESPONSES", True),
                secrets=runtime_settings.secret_values(),
            )
            outcome = Generator(runtime_settings, catalog, client, trace=trace).run(
                raw_request,
                job_id=job_id,
                project_id=project_id,
            )
            app.state.projects[project_id] = outcome.project
            job["completed_variants"] = outcome.project["completed_variants"]
            job["status"] = outcome.project["status"]
            job["warnings"] = outcome.warnings
            job["variants"] = job_status.variant_statuses(outcome, job["requested_variants"])
            # Причины, по которым варианты не готовы, в формате ошибок контракта 02.
            job["errors"] = job_status.variant_errors(outcome)
        except RequestError as exc:
            job["status"] = "failed"
            job["errors"] = [exc.to_dict()["error"]]
        except Exception as exc:  # ошибка модели, этап не прошёл схему или сбой сервиса
            job["status"] = "failed"
            job["errors"] = [job_status.exception_error(exc)]

    def run_job(job_id: str, project_id: str, raw_request: dict[str, Any]) -> None:
        """Задача пула: учёт нагрузки вокруг генерации."""
        with load_lock:
            load["waiting"] -= 1
            load["running"] += 1
        try:
            finish_generation(job_id, project_id, raw_request)
        finally:
            with load_lock:
                load["running"] -= 1
                finished_at[job_id] = time.monotonic()

    def purge_finished() -> None:
        """Убирает из памяти статусы и проекты, завершённые раньше `results_keep_hours`."""
        now = time.monotonic()
        with load_lock:
            old = [job_id for job_id, ended in finished_at.items() if now - ended > keep_seconds]
            for job_id in old:
                finished_at.pop(job_id, None)
                job = app.state.jobs.pop(job_id, None)
                if job:
                    app.state.projects.pop(job["project_id"], None)

    @app.get("/api/v1/load", dependencies=[Depends(require_service_token)])
    def service_load() -> dict[str, Any]:
        """Текущая нагрузка: сколько генераций идёт, сколько ждёт, сколько обращений к модели сейчас."""
        with load_lock:
            current = dict(load)
        return {
            "running_generations": current["running"],
            "waiting_generations": current["waiting"],
            "max_parallel_generations": max_parallel,
            "max_waiting_generations": max_waiting,
            **limits.load(),
        }

    @app.get("/api/v1/health", dependencies=[Depends(require_service_token)])
    def health() -> dict[str, str]:
        """Возвращает базовый статус процесса LLM-сервиса."""
        return {"status": "ok", "service": "school-events-llm"}

    @app.get("/api/v1/health/llm", dependencies=[Depends(require_service_token)])
    def health_llm() -> dict[str, Any]:
        """Проверяет доступность настроенной модели или fixture-провайдера."""
        try:
            return {"status": "ok", **app.state.client_factory().health()}
        except LLMError as exc:
            raise HTTPException(
                status_code=503,
                detail=_error(exc.code, exc.message, retryable=exc.retryable)["error"],
            ) from exc

    @app.get("/api/v1/catalog/events", dependencies=[Depends(require_service_token)])
    def list_events() -> list[dict[str, Any]]:
        """Возвращает публичную проекцию синхронизированного каталога мероприятий."""
        keys = ("id", "title", "category", "aliases", "supported_age_groups", "supported_formats", "catalog_version")
        return [{key: event.get(key) for key in keys} for event in catalog.active_events().values()]

    @app.post(
        "/api/v1/generations",
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_service_token)],
    )
    def create_generation(raw_request: dict[str, Any]) -> dict[str, Any]:
        """Принимает контракт 01, проверяет его и запускает генерацию: сразу, если есть свободное место, иначе в очередь."""
        try:
            normalized = normalize(raw_request, catalog, runtime_settings)
        except RequestError as exc:
            raise HTTPException(status_code=422, detail=exc.to_dict()["error"]) from exc

        purge_finished()
        with load_lock:
            if load["running"] + load["waiting"] >= max_parallel + max_waiting:
                raise HTTPException(status_code=503, detail=_error(
                    "SERVICE_BUSY",
                    f"Сервис занят: идут {load['running']} генераций и ещё {load['waiting']} ждут. Повторите через минуту.",
                    retryable=True)["error"])
            load["waiting"] += 1

        job_id = f"job_{uuid4().hex}"
        project_id = f"evt_{uuid4().hex}"
        app.state.jobs[job_id] = {
            "job_id": job_id,
            "project_id": project_id,
            "status": "queued",
            "requested_variants": normalized.variants_count,
            "completed_variants": 0,
            "warnings": [warning.__dict__ for warning in normalized.warnings],
            "errors": [],
        }
        try:
            executor.submit(run_job, job_id, project_id, raw_request)
        except RuntimeError as exc:  # пул остановлен: сервис завершает работу
            with load_lock:
                load["waiting"] -= 1
            app.state.jobs.pop(job_id, None)
            raise HTTPException(status_code=503, detail=_error("SERVICE_BUSY", "Сервис останавливается", retryable=True)["error"]) from exc
        return {
            "job_id": job_id,
            "project_id": project_id,
            "status": "queued",
            "requested_variants": normalized.variants_count,
            "completed_variants": 0,
            "status_url": f"/api/v1/generations/{job_id}",
            "project_url": f"/api/v1/projects/{project_id}",
        }

    @app.get("/api/v1/generations/{job_id}", dependencies=[Depends(require_service_token)])
    def get_generation(job_id: str) -> dict[str, Any]:
        """Возвращает текущее состояние задачи генерации."""
        job = app.state.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=_error("RESOURCE_NOT_FOUND", "Задание не найдено")["error"])
        return {
            **job,
            "phase": job["status"],
            "variants": job.get("variants", [
                {
                    "variant_id": f"v{i}",
                    "status": job["status"],
                    "revision": 1,
                }
                for i in range(1, job["requested_variants"] + 1)
            ]),
        }

    @app.get("/api/v1/projects/{project_id}", dependencies=[Depends(require_service_token)])
    def get_project(project_id: str) -> dict[str, Any]:
        """Возвращает готовый проект по контракту 02."""
        project = app.state.projects.get(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail=_error("RESOURCE_NOT_FOUND", "Готовый проект не найден")["error"])
        return project

    @app.get("/api/v1/projects/{project_id}/variants/{variant_id}", dependencies=[Depends(require_service_token)])
    def get_variant(project_id: str, variant_id: str) -> dict[str, Any]:
        """Возвращает один готовый вариант проекта."""
        project = app.state.projects.get(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail=_error("RESOURCE_NOT_FOUND", "Готовый проект не найден")["error"])
        variant = next((item for item in project.get("variants", []) if item.get("variant_id") == variant_id), None)
        if variant is None:
            raise HTTPException(status_code=404, detail=_error("RESOURCE_NOT_FOUND", "Вариант не найден")["error"])
        return variant

    return app


app = create_app()