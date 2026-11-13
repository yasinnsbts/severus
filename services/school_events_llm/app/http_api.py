"""Внутренний HTTP API LLM-сервиса для подключения к основному Backend Severus.

Frontend не обращается к этому приложению напрямую. Общий Backend передаёт сюда
тот же JSON контракта 01 и получает ответы контракта 02 без преобразования полей.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import job_status
from .catalog import Catalog
from .generation.pipeline import Generator
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


def create_app(settings: Settings | None = None, client_factory: ClientFactory | None = None) -> FastAPI:
    """Создаёт FastAPI-приложение внутреннего LLM-сервиса.

    Параметры:
        `settings`: Настройки сервиса. Если не переданы, читаются из окружения.
        `client_factory`: Фабрика LLM-клиента. Используется тестами для fixture.

    Возвращает:
        FastAPI.
    """
    runtime_settings = settings or Settings.load()
    catalog = Catalog.load(runtime_settings)
    runtime_client_factory = client_factory or (lambda: build_runtime_client(runtime_settings))

    app = FastAPI(
        title="Severus School Events LLM Service",
        description="Внутренний сервис генерации сценариев школьных мероприятий",
        version="0.2.0",
    )
    app.state.settings = runtime_settings
    app.state.catalog = catalog
    app.state.client_factory = runtime_client_factory
    app.state.jobs = {}
    app.state.projects = {}

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
    def create_generation(raw_request: dict[str, Any], background_tasks: BackgroundTasks) -> dict[str, Any]:
        """Принимает контракт 01, проверяет его и ставит генерацию в фоновую очередь."""
        try:
            normalized = normalize(raw_request, catalog, runtime_settings)
        except RequestError as exc:
            raise HTTPException(status_code=422, detail=exc.to_dict()["error"]) from exc

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
        background_tasks.add_task(finish_generation, job_id, project_id, raw_request)
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