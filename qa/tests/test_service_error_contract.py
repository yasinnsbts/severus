"""Контракт ошибок Backend ↔ LLM-сервис.

Проверяем, что Backend не теряет код и retryable при ответах сервиса.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.llm_service_client import LLMServiceClient


class FakeResponse:
    """Минимальный ответ httpx для проверки преобразования ошибок."""

    def __init__(self, status_code: int, payload: dict):
        """Сохраняет статус и JSON-тело ответа."""
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        """Возвращает JSON-тело ответа."""
        return self._payload


def test_service_busy_is_preserved():
    """503 SERVICE_BUSY сохраняет код и retryable=true."""
    response = FakeResponse(503, {"error": {
        "code": "SERVICE_BUSY",
        "message": "Сервис занят",
        "field": None,
        "retryable": True,
    }})

    with pytest.raises(HTTPException) as exc:
        LLMServiceClient._raise_service_error(response)

    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "SERVICE_BUSY"
    assert exc.value.detail["retryable"] is True


def test_event_not_found_is_preserved():
    """422 EVENT_NOT_FOUND не превращается в 503 и остаётся non-retryable."""
    response = FakeResponse(422, {"error": {
        "code": "EVENT_NOT_FOUND",
        "message": "Неизвестное мероприятие",
        "field": "event_id",
        "retryable": False,
    }})

    with pytest.raises(HTTPException) as exc:
        LLMServiceClient._raise_service_error(response)

    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "EVENT_NOT_FOUND"
    assert exc.value.detail["retryable"] is False
