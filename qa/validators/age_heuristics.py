from __future__ import annotations

import re
from typing import Any


def _issue(code: str, severity: str, message: str, field: str | None = None) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, "field": field}


def _as_int(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def check_age_heuristics(variant: dict, input_data: dict) -> list[dict]:
    if not isinstance(variant, dict) or not isinstance(input_data, dict):
        return []

    grade_group = input_data.get("grade_group")
    timeline = variant.get("timeline")
    blocks = [b for b in timeline if isinstance(b, dict)] if isinstance(timeline, list) else []

    if grade_group == "1-4":
        issues: list[dict] = []

        for block in blocks:
            duration = _as_int(block.get("duration_minutes"))
            if duration is not None and duration > 15:
                issues.append(_issue(
                    "AGE_LONG_BLOCK",
                    "medium",
                    f"Блок '{block.get('block_id', '?')}' длиннее 15 минут для группы 1-4",
                    "timeline",
                ))

        scripts = [b.get("teacher_script") for b in blocks]
        all_text = " ".join(s for s in scripts if isinstance(s, str))
        long_words = re.findall(r"[a-zA-Zа-яА-ЯёЁ]{13,}", all_text)
        if long_words:
            issues.append(_issue(
                "AGE_LONG_WORDS",
                "low",
                f"В teacher_script есть слова длиннее 12 букв (например, '{long_words[0]}')",
                "timeline.teacher_script",
            ))

        return issues

    if grade_group == "9-11":
        durations = [_as_int(b.get("duration_minutes")) for b in blocks]
        if blocks and all(d is not None and d <= 5 for d in durations):
            return [_issue(
                "AGE_ALL_SHORT",
                "low",
                "Все блоки ≤ 5 минут для группы 9-11 — возможно, слишком коротко",
                "timeline",
            )]

    return []
