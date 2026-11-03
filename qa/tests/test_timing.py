from __future__ import annotations

import json
from pathlib import Path

from qa.validators import validate_timing

FIXTURES = Path(__file__).parent / "fixtures"


def _load_variant(name: str) -> dict:
    return json.loads((FIXTURES / "outputs" / name).read_text(encoding="utf-8"))


def _load_input(name: str) -> dict:
    return json.loads((FIXTURES / "inputs" / name).read_text(encoding="utf-8"))


def _codes(issues: list[dict]) -> set[str]:
    return {issue["code"] for issue in issues}


def test_happy_path_has_no_timing_issues() -> None:
    issues = validate_timing(
        _load_variant("happy_path_variant.json"),
        _load_input("01_happy_path_45min.json"),
    )

    assert issues == []


def test_total_less_than_requested_is_mismatch() -> None:
    variant = _load_variant("happy_path_variant.json")
    variant["timeline"][1]["duration_minutes"] = 15
    variant["timeline"][2]["start_minute"] = 25

    issues = validate_timing(variant, _load_input("01_happy_path_45min.json"))

    assert _codes(issues) == {"TIMING_TOTAL_MISMATCH"}
    assert "40" in issues[0]["message"]


def test_total_more_than_requested_is_mismatch() -> None:
    variant = _load_variant("happy_path_variant.json")
    variant["timeline"][2]["duration_minutes"] = 20

    issues = validate_timing(variant, _load_input("01_happy_path_45min.json"))

    assert _codes(issues) == {"TIMING_TOTAL_MISMATCH"}
    assert "50" in issues[0]["message"]


def test_gap_between_blocks_is_detected() -> None:
    issues = validate_timing(
        _load_variant("timing_gap.json"),
        _load_input("01_happy_path_45min.json"),
    )

    assert _codes(issues) == {"TIMING_GAP"}


def test_overlap_between_blocks_is_detected() -> None:
    issues = validate_timing(
        _load_variant("timing_overlap.json"),
        _load_input("01_happy_path_45min.json"),
    )

    assert _codes(issues) == {"TIMING_OVERLAP"}


def test_first_block_must_start_at_zero() -> None:
    issues = validate_timing(
        _load_variant("wrong_start.json"),
        _load_input("01_happy_path_45min.json"),
    )

    assert _codes(issues) == {"TIMING_START_NOT_ZERO"}


def test_non_positive_duration_is_detected() -> None:
    variant = _load_variant("happy_path_variant.json")
    variant["timeline"][0]["duration_minutes"] = 0
    variant["timeline"][1]["start_minute"] = 0
    variant["timeline"][1]["duration_minutes"] = 25
    variant["timeline"][2]["start_minute"] = 25
    variant["timeline"][2]["duration_minutes"] = 20

    issues = validate_timing(variant, _load_input("01_happy_path_45min.json"))

    assert _codes(issues) == {"TIMING_NON_POSITIVE"}


def test_missing_target_duration_returns_issue_instead_of_exception() -> None:
    issues = validate_timing(_load_variant("happy_path_variant.json"), {})

    assert any(
        issue["code"] == "TIMING_INVALID_INPUT" and issue["severity"] == "critical"
        for issue in issues
    )
