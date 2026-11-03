"""Статус задачи генерации для HTTP API: статусы вариантов и ошибки в формате контракта 02.

Вынесено из `http_api.py`, чтобы логику можно было проверять без FastAPI.

Формат ошибки (контракт 02, раздел 5): `code`, `message` (текст для пользователя),
`field` (поле входного запроса или None), `retryable` (можно ли повторить запрос без изменений).
"""

from __future__ import annotations

from typing import Any

MAX_ERRORS_PER_VARIANT = 5


def error(code: str, message: str, field: str | None = None, retryable: bool = False) -> dict[str, Any]:
    """Одна ошибка в формате контракта 02."""
    return {"code": code, "message": message, "field": field, "retryable": retryable}


def variant_statuses(outcome: Any, requested: int) -> list[dict[str, Any]]:
    """Статус каждого слота варианта по его ID, а не по порядку готовности."""
    by_id = {v.variant_id: v.status for v in outcome.variants}
    return [{"variant_id": f"v{i}", "status": by_id.get(f"v{i}", "failed"), "revision": 1}
            for i in range(1, requested + 1)]


def variant_errors(outcome: Any) -> list[dict[str, Any]]:
    """Причины, по которым варианты не готовы.

    - Критические замечания проверки: код замечания и его текст, не больше `MAX_ERRORS_PER_VARIANT` на вариант.
      `field=None`: место замечания (`timeline.block_02`) - не поле входного запроса.
    - Если замечаний нет (этап не прошёл схему, ошибка модели) - текст из `variant.error`.
    - `retryable=True`: модель отвечает каждый раз по-разному, повтор с теми же параметрами может пройти.
    """
    errors: list[dict[str, Any]] = []
    for variant in outcome.variants:
        if variant.status == "completed":
            continue
        critical = [issue for issue in variant.issues if issue.severity == "critical"]
        for issue in critical[:MAX_ERRORS_PER_VARIANT]:
            errors.append(error(issue.code, f"Вариант {variant.variant_id}: {issue.message}", retryable=True))
        if not critical:
            reason = variant.error or "сценарий не удалось сформировать"
            errors.append(error("VARIANT_GENERATION_FAILED", f"Вариант {variant.variant_id}: {reason}", retryable=True))
    return errors


def exception_error(exc: Exception) -> dict[str, Any]:
    """Ошибка задачи, если генерация упала целиком (до готовых вариантов).

    - Ошибка модели (`LLMError`): её код и признак повтора.
    - Ответ модели не прошёл схему на общем этапе (`StageFailed`): `OUTPUT_SCHEMA_INVALID`, повтор возможен.
    - Прочее: `INTERNAL_ERROR` без технических подробностей в тексте для пользователя.
    """
    from .generation.pipeline import StageFailed
    from .llm.client import LLMError

    if isinstance(exc, LLMError):
        return error(exc.code, exc.message, retryable=exc.retryable)
    if isinstance(exc, StageFailed):
        return error(exc.code, f"Модель не смогла выполнить этап {exc.stage}. Повторите генерацию.", retryable=True)
    return error("INTERNAL_ERROR", "Внутренняя ошибка сервиса генерации. Подробности - в журнале прогона.", retryable=False)