"""Интеграционные тесты основного Backend и независимого LLM-сервиса."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app as backend_app
from backend.schemas import GenerationRequest as BackendGenerationRequest


REPO_ROOT = Path(__file__).resolve().parent.parent
LLM_ROOT = REPO_ROOT / "services" / "school_events_llm"
if str(LLM_ROOT) not in sys.path:
    sys.path.insert(0, str(LLM_ROOT))

from app.catalog import Catalog  # noqa: E402
from app.contracts.request import GenerationRequest as LLMGenerationRequest, apply_defaults  # noqa: E402
from app.http_api import create_app  # noqa: E402
from app.llm.fixture import FixtureLLM  # noqa: E402
from app.settings import Settings  # noqa: E402


class ServiceClientBridge:
    """Адаптирует FastAPI TestClient LLM-сервиса к интерфейсу backend-клиента.

    Генерация в сервисе идёт в фоновом пуле, поэтому мост дожидается завершения задачи
    перед чтением статуса и проекта: тесты проверяют итог, а не момент гонки.
    """

    def __init__(self, client: TestClient):
        """Сохраняет тестовый HTTP-клиент внутреннего сервиса."""
        self.client = client
        self.job_by_project = {}

    def _wait(self, job_id, headers, timeout=15.0):
        """Ждёт, пока задача выйдет из статусов queued и running."""
        deadline = time.monotonic() + timeout
        while True:
            response = self.client.get(f"/api/v1/generations/{job_id}", headers=headers)
            if response.status_code >= 400 or response.json().get("status") not in ("queued", "running"):
                return response
            if time.monotonic() > deadline:
                raise AssertionError(f"Задача {job_id} не завершилась за {timeout} с")
            time.sleep(0.02)

    @staticmethod
    def _json(response):
        """Проверяет успешный HTTP-ответ и возвращает JSON."""
        if response.status_code >= 400:
            raise AssertionError(f"LLM service error {response.status_code}: {response.text}")
        return response.json()

    def create_generation(self, payload, *, request_id=None, idempotency_key=None):
        """Передаёт контракт 01 в тестовый LLM-сервис."""
        headers = {}
        if request_id:
            headers["X-Request-Id"] = request_id
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        accepted = self._json(self.client.post("/api/v1/generations", json=payload, headers=headers))
        self.job_by_project[accepted["project_id"]] = accepted["job_id"]
        return accepted

    def get_generation(self, job_id, *, request_id=None):
        """Получает итоговый статус задачи из тестового LLM-сервиса."""
        headers = {"X-Request-Id": request_id} if request_id else {}
        return self._json(self._wait(job_id, headers))

    def get_project(self, project_id, *, request_id=None):
        """Получает проект из тестового LLM-сервиса после завершения его задачи."""
        headers = {"X-Request-Id": request_id} if request_id else {}
        if project_id in self.job_by_project:
            self._wait(self.job_by_project[project_id], headers)
        return self._json(self.client.get(f"/api/v1/projects/{project_id}", headers=headers))

    def health(self):
        """Получает состояние fixture-модели."""
        return self._json(self.client.get("/api/v1/health/llm"))


def _request_payload() -> dict:
    """Возвращает тестовый запрос полного Backend -> LLM -> Backend сценария."""
    return {
        "event_id": "knowledge_day",
        "region_id": "RU-SVE",
        "grade": 6,
        "pupils_count": 25,
        "duration_minutes": 45,
        "format": "class_hour",
        "generation": {"variants_count": 1, "language": "ru"},
    }


def test_backend_and_llm_request_contracts_match_effective_json():
    """Проверяет, что Backend и LLM получают одинаковый эффективный контракт 01."""
    payload = _request_payload()
    backend_json = BackendGenerationRequest.model_validate(payload).model_dump(mode="json")
    settings = Settings(root=LLM_ROOT, env={})
    llm_json = LLMGenerationRequest.model_validate(
        apply_defaults(payload, settings.request_defaults())
    ).model_dump(mode="json")
    assert backend_json == llm_json


def test_backend_and_llm_contracts_accept_same_edge_values():
    """Проверяет отсутствие скрытых лимитов LLM поверх уже принятого Backend контракта."""
    payload = _request_payload()
    payload["participants"] = {
        "teachers_count": 11,
        "parents_enabled": True,
        "parents_count": 201,
        "parent_roles": ["audience"],
        "parent_audience_engagement": "feedback",
        "parent_notes": "x" * 600,
    }
    payload["resources"] = {
        "projector": None,
        "printer": None,
        "internet": None,
        "audio": None,
        "room": None,
        "available_materials": [f"item_{i}" for i in range(51)],
        "extra_notes": "y" * 600,
    }
    payload["teacher_preferences"] = {
        "style": "classic",
        "script_detail": "standard",
        "difficulty": "standard",
        "interaction_level": "low",
        "group_work": False,
        "preparation_effort": "minimal",
        "notes": "z" * 600,
    }
    backend_json = BackendGenerationRequest.model_validate(payload).model_dump(mode="json")
    settings = Settings(root=LLM_ROOT, env={})
    llm_json = LLMGenerationRequest.model_validate(
        apply_defaults(payload, settings.request_defaults())
    ).model_dump(mode="json")
    assert backend_json == llm_json


def test_llm_catalog_matches_main_catalog_exactly():
    """Проверяет синхронизацию всех 14 ID основного каталога и LLM-профилей."""
    from backend.catalog import list_events

    main_ids = {event.id for event in list_events()}
    llm_ids = set(Catalog.load(Settings(root=LLM_ROOT, env={})).active_events())
    assert len(main_ids) == 14
    assert llm_ids == main_ids
    assert "sverdlovsk_oblast_day" in llm_ids
    assert "middle_urals_peoples_day" in llm_ids
    assert "ural_culture" not in llm_ids


def test_every_catalog_event_has_llm_prompt_block():
    """Проверяет наличие event-prompt для каждой из 14 карточек общего каталога."""
    catalog = Catalog.load(Settings(root=LLM_ROOT, env={}))
    for event_id, event in catalog.active_events().items():
        prompt_path = LLM_ROOT / "prompts" / "events" / f"{event_id}.md"
        assert prompt_path.is_file(), f"Нет LLM prompt для {event_id}: {prompt_path}"
        first_line = prompt_path.read_text(encoding="utf-8").splitlines()[0]
        assert f"id: events.{event_id}" in first_line


def test_full_backend_to_llm_fixture_flow(monkeypatch, tmp_path):
    """Проверяет полный проход Backend -> HTTP API LLM -> fixture pipeline -> Backend."""
    golden = json.loads(
        (LLM_ROOT / "examples" / "golden" / "ex1_knowledge_day.json").read_text(encoding="utf-8")
    )
    settings = Settings(
        root=LLM_ROOT,
        env={
            "DATA_DIR": str(tmp_path / "llm_data"),
            "LOG_FULL_PROMPTS": "false",
            "LOG_FULL_RESPONSES": "false",
        },
    )
    service_app = create_app(
        settings,
        client_factory=lambda: FixtureLLM([golden], model_key="fixture_integration"),
    )
    bridge = ServiceClientBridge(TestClient(service_app))

    import backend.generations as generations

    monkeypatch.setenv("GENERATOR_MODE", "llm_service")
    monkeypatch.setattr(generations, "get_llm_service_client", lambda: bridge)

    client = TestClient(backend_app)
    full_payload = json.loads(
        (LLM_ROOT / "examples" / "requests" / "ex1_knowledge_day.json").read_text(encoding="utf-8")
    )
    accepted_response = client.post("/api/v1/generations", json=full_payload)
    assert accepted_response.status_code == 202
    accepted = accepted_response.json()

    status_response = client.get(accepted["status_url"])
    project_response = client.get(accepted["project_url"])
    assert status_response.status_code == 200
    assert project_response.status_code == 200

    job = status_response.json()
    project = project_response.json()
    assert job["status"] == "completed"
    assert job["completed_variants"] == 1
    assert project["status"] == "completed"
    assert project["completed_variants"] == 1
    assert project["job_id"] == accepted["job_id"]
    assert project["project_id"] == accepted["project_id"]
    assert project["generation_meta"]["model_key"] == "fixture_integration"
    assert project["input"] == BackendGenerationRequest.model_validate(full_payload).model_dump(mode="json")
    assert sum(block["duration_minutes"] for block in project["variants"][0]["timeline"]) == 45


def test_failed_fixture_exposes_validation_errors(monkeypatch, tmp_path):
    """Причины отказа валидатора доступны через Backend API."""
    golden = json.loads(
        (LLM_ROOT / "examples" / "golden" / "ex1_knowledge_day.json")
        .read_text(encoding="utf-8")
    )

    settings = Settings(
        root=LLM_ROOT,
        env={
            "DATA_DIR": str(tmp_path / "llm_data"),
            "LOG_FULL_PROMPTS": "false",
            "LOG_FULL_RESPONSES": "false",
        },
    )

    service_app = create_app(
        settings,
        client_factory=lambda: FixtureLLM(
            [golden],
            model_key="fixture_integration",
        ),
    )

    bridge = ServiceClientBridge(TestClient(service_app))

    import backend.generations as generations

    monkeypatch.setenv("GENERATOR_MODE", "llm_service")
    monkeypatch.setattr(
        generations,
        "get_llm_service_client",
        lambda: bridge,
    )

    client = TestClient(backend_app)

    payload = json.loads(
        (LLM_ROOT / "examples" / "requests" / "ex1_knowledge_day.json")
        .read_text(encoding="utf-8")
    )

    payload["pupils_count"] = 25
    payload["participants"] = {
        "teachers_count": 1,
        "parents_enabled": False,
        "parents_count": 0,
        "parent_roles": [],
    }

    response = client.post("/api/v1/generations", json=payload)
    assert response.status_code == 202

    accepted = response.json()
    status_response = client.get(accepted["status_url"])
    assert status_response.status_code == 200

    job = status_response.json()

    assert job["status"] == "failed"
    assert job["completed_variants"] == 0
    assert job["errors"], "API не передал причины отказа"

    codes = {error["code"] for error in job["errors"]}

    assert "PLAN-PUPILS" in codes
    assert "PARENTS-DISABLED" in codes

    assert all(
        error.get("message")
        for error in job["errors"]
    )


def test_partial_generation_preserves_variant_statuses(monkeypatch, tmp_path):
    """При partial статусы привязаны к ID вариантов, а не к их порядку."""
    from types import SimpleNamespace

    from app.generation.pipeline import Generator

    golden = json.loads(
        (LLM_ROOT / "examples" / "golden" / "ex1_knowledge_day.json")
        .read_text(encoding="utf-8")
    )

    settings = Settings(
        root=LLM_ROOT,
        env={
            "DATA_DIR": str(tmp_path / "llm_data"),
            "LOG_FULL_PROMPTS": "false",
            "LOG_FULL_RESPONSES": "false",
        },
    )

    def fake_run(self, raw_request, *, job_id, project_id):
        return SimpleNamespace(
            project={
                "job_id": job_id,
                "project_id": project_id,
                "status": "partial",
                "requested_variants": 2,
                "completed_variants": 1,
                "variants": [
                    {"variant_id": "v2", "status": "completed"}
                ],
            },
            variants=[
                SimpleNamespace(
                    variant_id="v1",
                    status="failed",
                    issues=[],
                    error="Проверка не пройдена",
                ),
                SimpleNamespace(
                    variant_id="v2",
                    status="completed",
                    issues=[],
                    error=None,
                ),
            ],
            warnings=[],
        )

    monkeypatch.setattr(Generator, "run", fake_run)

    service_app = create_app(
        settings,
        client_factory=lambda: FixtureLLM([golden]),
    )
    bridge = ServiceClientBridge(TestClient(service_app))

    import backend.generations as generations

    monkeypatch.setenv("GENERATOR_MODE", "llm_service")
    monkeypatch.setattr(
        generations,
        "get_llm_service_client",
        lambda: bridge,
    )

    client = TestClient(backend_app)

    payload = json.loads(
        (LLM_ROOT / "examples" / "requests" / "ex1_knowledge_day.json")
        .read_text(encoding="utf-8")
    )
    payload["generation"]["variants_count"] = 2

    response = client.post("/api/v1/generations", json=payload)
    assert response.status_code == 202

    accepted = response.json()
    status_response = client.get(accepted["status_url"])
    assert status_response.status_code == 200

    job = status_response.json()

    assert job["status"] == "partial"
    assert job["completed_variants"] == 1
    assert job["requested_variants"] == 2

    statuses = {
        item["variant_id"]: item["status"]
        for item in job["variants"]
    }

    assert statuses == {
        "v1": "failed",
        "v2": "completed",
    }

    assert any(
        error["code"] == "VARIANT_GENERATION_FAILED"
        for error in job["errors"]
    )

    project_response = client.get(accepted["project_url"])
    assert project_response.status_code == 200
    assert [
        variant["variant_id"]
        for variant in project_response.json()["variants"]
    ] == ["v2"]
