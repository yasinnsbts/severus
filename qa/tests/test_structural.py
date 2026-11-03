from __future__ import annotations

import json
from pathlib import Path

from qa.validators import validate_structure

FIXTURES = Path(__file__).parent / "fixtures"


def _load_variant(name: str) -> dict:
    return json.loads((FIXTURES / "outputs" / name).read_text(encoding="utf-8"))


def _load_input(name: str) -> dict:
    return json.loads((FIXTURES / "inputs" / name).read_text(encoding="utf-8"))


def _codes(issues: list[dict]) -> set[str]:
    return {issue["code"] for issue in issues}


def test_happy_path_has_no_issues() -> None:
    issues = validate_structure(
        _load_variant("happy_path_variant.json"),
        _load_input("01_happy_path_45min.json"),
    )

    assert issues == []


def test_missing_required_collections_are_critical() -> None:
    variant = _load_variant("happy_path_variant.json")
    for field in ("timeline", "roles", "materials"):
        variant.pop(field)

    issues = validate_structure(variant, _load_input("01_happy_path_45min.json"))

    missing = {
        issue["field"]
        for issue in issues
        if issue["code"] == "MISSING_COLLECTION" and issue["severity"] == "critical"
    }
    assert missing == {"timeline", "roles", "materials"}


def test_empty_concept_fields_are_high() -> None:
    issues = validate_structure(
        _load_variant("empty_concept.json"),
        _load_input("01_happy_path_45min.json"),
    )

    fields = {
        issue["field"]
        for issue in issues
        if issue["code"] == "MISSING_FIELD" and issue["severity"] == "high"
    }
    assert "concept.summary" in fields
    assert "concept.goal" in fields


def test_empty_teacher_script_is_high() -> None:
    issues = validate_structure(
        _load_variant("empty_teacher_script.json"),
        _load_input("01_happy_path_45min.json"),
    )

    assert any(
        issue["code"] == "MISSING_FIELD"
        and issue["severity"] == "high"
        and issue["field"] == "timeline.teacher_script"
        for issue in issues
    )


def test_one_block_only_is_too_few_blocks() -> None:
    issues = validate_structure(
        _load_variant("one_block_only.json"),
        _load_input("01_happy_path_45min.json"),
    )

    assert any(
        issue["code"] == "TOO_FEW_BLOCKS" and issue["severity"] == "high"
        for issue in issues
    )


def test_orphan_role_id_is_critical() -> None:
    issues = validate_structure(
        _load_variant("orphan_role_id.json"),
        _load_input("01_happy_path_45min.json"),
    )

    assert any(
        issue["code"] == "ORPHAN_ROLE_ID"
        and issue["severity"] == "critical"
        and "ghost_role" in issue["message"]
        for issue in issues
    )


def test_orphan_material_id_is_critical() -> None:
    issues = validate_structure(
        _load_variant("orphan_material_id.json"),
        _load_input("01_happy_path_45min.json"),
    )

    assert any(
        issue["code"] == "ORPHAN_MATERIAL_ID"
        and issue["severity"] == "critical"
        and "ghost_material" in issue["message"]
        for issue in issues
    )


def test_orphan_block_id_in_parent_plan_is_critical() -> None:
    issues = validate_structure(
        _load_variant("broken_references.json"),
        _load_input("05_no_parents.json"),
    )

    assert any(
        issue["code"] == "ORPHAN_BLOCK_ID"
        and issue["severity"] == "critical"
        and issue["field"] == "parent_participation_plan.block_ids"
        for issue in issues
    )


def test_parents_disabled_forbids_parent_role_and_enabled_plan() -> None:
    issues = validate_structure(
        _load_variant("parents_violation_variant.json"),
        _load_input("05_no_parents.json"),
    )

    assert any(
        issue["code"] == "PARENT_ROLE_FORBIDDEN" and issue["severity"] == "critical"
        for issue in issues
    )
    assert any(
        issue["code"] == "PARENT_PLAN_FORBIDDEN" and issue["severity"] == "critical"
        for issue in issues
    )


def test_parents_enabled_requires_enabled_plan() -> None:
    issues = validate_structure(
        _load_variant("parents_enabled_no_plan.json"),
        _load_input("04_parents_enabled.json"),
    )

    assert any(
        issue["code"] == "PARENT_PLAN_MISSING" and issue["severity"] == "high"
        for issue in issues
    )


def test_parents_over_count_is_critical() -> None:
    issues = validate_structure(
        _load_variant("parents_over_count.json"),
        _load_input("01_happy_path_45min.json"),
    )

    assert any(
        issue["code"] == "PARENTS_OVER_COUNT" and issue["severity"] == "critical"
        for issue in issues
    )


def test_print_required_without_printer_is_high() -> None:
    issues = validate_structure(
        _load_variant("print_required_no_printer.json"),
        _load_input("08_minimal_resources.json"),
    )

    assert any(
        issue["code"] == "PRINTER_REQUIRED_MISSING" and issue["severity"] == "high"
        for issue in issues
    )


def test_print_required_with_printer_available_is_ok() -> None:
    input_data = _load_input("08_minimal_resources.json")
    input_data["resources"]["printer"] = True

    issues = validate_structure(
        _load_variant("print_required_no_printer.json"),
        input_data,
    )

    assert "PRINTER_REQUIRED_MISSING" not in _codes(issues)


def test_school_event_format_does_not_crash() -> None:
    issues = validate_structure(
        _load_variant("happy_path_variant.json"),
        _load_input("06_school_event.json"),
    )

    assert isinstance(issues, list)
    assert not [issue for issue in issues if issue["severity"] == "critical"]


def test_non_dict_variant_returns_issue_instead_of_exception() -> None:
    issues = validate_structure(None, {})

    assert isinstance(issues, list)
    assert any(issue["code"] == "INVALID_VARIANT" for issue in issues)
