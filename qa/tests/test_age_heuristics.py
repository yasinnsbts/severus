from __future__ import annotations

import json
from pathlib import Path

from qa.validators import check_age_heuristics

FIXTURES = Path(__file__).parent / "fixtures"


def _load_variant(name: str) -> dict:
    return json.loads((FIXTURES / "outputs" / name).read_text(encoding="utf-8"))


def _load_input(name: str) -> dict:
    return json.loads((FIXTURES / "inputs" / name).read_text(encoding="utf-8"))


def test_grade_1_4_long_block_is_medium() -> None:
    issues = check_age_heuristics(
        _load_variant("happy_path_variant.json"),
        _load_input("02_short_30min_1-4.json"),
    )

    assert any(
        issue["code"] == "AGE_LONG_BLOCK" and issue["severity"] == "medium"
        for issue in issues
    )


def test_grade_1_4_long_words_are_low() -> None:
    variant = _load_variant("happy_path_variant.json")
    for block in variant["timeline"]:
        block["duration_minutes"] = 10
        block["teacher_script"] = "Проведите занятие с классом."
    variant["timeline"][0]["teacher_script"] = "Используйте преобразовательность мышления."

    issues = check_age_heuristics(variant, _load_input("02_short_30min_1-4.json"))

    assert {issue["code"] for issue in issues} == {"AGE_LONG_WORDS"}
    assert issues[0]["severity"] == "low"


def test_grade_9_11_all_blocks_short_is_low() -> None:
    variant = _load_variant("happy_path_variant.json")
    for block in variant["timeline"]:
        block["duration_minutes"] = 5

    issues = check_age_heuristics(variant, _load_input("03_long_90min_9-11.json"))

    assert any(
        issue["code"] == "AGE_ALL_SHORT" and issue["severity"] == "low"
        for issue in issues
    )


def test_grade_5_8_normal_scenario_has_no_warnings() -> None:
    issues = check_age_heuristics(
        _load_variant("happy_path_variant.json"),
        _load_input("01_happy_path_45min.json"),
    )

    assert issues == []


def test_grade_9_11_normal_90min_grid_has_no_warnings() -> None:
    variant = _load_variant("happy_path_variant.json")
    durations = [20, 30, 40]
    start = 0
    for block, duration in zip(variant["timeline"], durations):
        block["start_minute"] = start
        block["duration_minutes"] = duration
        start += duration

    issues = check_age_heuristics(variant, _load_input("03_long_90min_9-11.json"))

    assert issues == []
