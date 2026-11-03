from __future__ import annotations

from typing import Any


def _issue(code: str, severity: str, message: str, field: str | None = None) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, "field": field}


def _as_int(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def validate_timing(variant: dict, input_data: dict) -> list[dict]:
    if not isinstance(variant, dict):
        return [_issue("INVALID_VARIANT", "critical", "variant отсутствует или не является объектом")]

    if not isinstance(input_data, dict):
        input_data = {}

    timeline = variant.get("timeline")
    if not isinstance(timeline, list):
        return [_issue(
            "TIMING_INVALID_INPUT",
            "critical",
            "timeline отсутствует или не является списком",
            "timeline",
        )]

    target = _as_int(input_data.get("duration_minutes"))
    if target is None:
        return [_issue(
            "TIMING_INVALID_INPUT",
            "critical",
            "duration_minutes отсутствует во входных данных",
            "duration_minutes",
        )]

    issues: list[dict] = []
    parsed: list[tuple[dict, int | float, int | float]] = []

    for block in timeline:
        if not isinstance(block, dict):
            issues.append(_issue(
                "TIMING_INVALID_BLOCK",
                "critical",
                "Блок timeline не является объектом",
                "timeline",
            ))
            continue

        start = _as_int(block.get("start_minute"))
        duration = _as_int(block.get("duration_minutes"))
        if start is None or duration is None:
            issues.append(_issue(
                "TIMING_INVALID_BLOCK",
                "critical",
                f"В блоке '{block.get('block_id', '?')}' отсутствует или не число start_minute/duration_minutes",
                "timeline",
            ))
            continue

        parsed.append((block, start, duration))

    total = sum(duration for _, _, duration in parsed)
    if total != target:
        issues.append(_issue(
            "TIMING_TOTAL_MISMATCH",
            "critical",
            f"Сумма duration_minutes ({total}) не равна {target}",
            "timeline",
        ))

    if parsed and parsed[0][1] != 0:
        issues.append(_issue(
            "TIMING_START_NOT_ZERO",
            "critical",
            f"Первый блок начинается с {parsed[0][1]} минуты, а не с 0",
            "timeline",
        ))

    for block, _, duration in parsed:
        if duration <= 0:
            issues.append(_issue(
                "TIMING_NON_POSITIVE",
                "critical",
                f"duration_minutes <= 0 в блоке '{block.get('block_id', '?')}'",
                "timeline",
            ))

    for (prev_block, prev_start, prev_duration), (block, start, _) in zip(parsed, parsed[1:]):
        expected = prev_start + prev_duration
        if start > expected:
            issues.append(_issue(
                "TIMING_GAP",
                "critical",
                f"Разрыв {start - expected} мин: блок '{block.get('block_id', '?')}' начинается "
                f"в {start}, ожидалось {expected}",
                "timeline",
            ))
        elif start < expected:
            issues.append(_issue(
                "TIMING_OVERLAP",
                "critical",
                f"Пересечение {expected - start} мин: блок '{block.get('block_id', '?')}' начинается "
                f"в {start}, а предыдущий '{prev_block.get('block_id', '?')}' заканчивается в {expected}",
                "timeline",
            ))

    return issues
