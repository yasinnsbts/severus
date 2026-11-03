from __future__ import annotations

from typing import Any


def _issue(
    code: str,
    severity: str,
    message: str,
    field: str | None = None,
) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, "field": field}


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _as_int(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _has_printer_dependency(material: dict) -> bool:
    dependencies = material.get("dependencies")
    if not isinstance(dependencies, list):
        return False
    return any(isinstance(dep, str) and "printer" in dep.lower() for dep in dependencies)


def validate_structure(variant: dict, input_data: dict) -> list[dict]:
    if not isinstance(variant, dict):
        return [_issue("INVALID_VARIANT", "critical", "variant отсутствует или не является объектом")]

    if not isinstance(input_data, dict):
        input_data = {}

    issues: list[dict] = []

    # --- Обязательные разделы ---
    concept = variant.get("concept")
    if not isinstance(concept, dict):
        issues.append(_issue("MISSING_FIELD", "high", "concept отсутствует или не является объектом", "concept"))
        concept = {}

    if not _is_non_empty_string(concept.get("summary")):
        issues.append(_issue("MISSING_FIELD", "high", "concept.summary отсутствует или пуст", "concept.summary"))
    if not _is_non_empty_string(concept.get("goal")):
        issues.append(_issue("MISSING_FIELD", "high", "concept.goal отсутствует или пуст", "concept.goal"))

    timeline = variant.get("timeline")
    roles = variant.get("roles")
    materials = variant.get("materials")

    for name, value in (("timeline", timeline), ("roles", roles), ("materials", materials)):
        if not isinstance(value, list):
            issues.append(_issue(
                "MISSING_COLLECTION",
                "critical",
                f"{name} отсутствует или не является списком",
                name,
            ))

    timeline = _as_list(timeline)
    roles = _as_list(roles)
    materials = _as_list(materials)

    teacher_instructions = variant.get("teacher_instructions")
    if not (_is_non_empty_string(teacher_instructions) or _is_non_empty_list(teacher_instructions)):
        issues.append(_issue(
            "MISSING_FIELD",
            "high",
            "teacher_instructions отсутствует или пуст",
            "teacher_instructions",
        ))

    # --- Минимум 2 блока ---
    if len(timeline) < 2:
        issues.append(_issue(
            "TOO_FEW_BLOCKS",
            "high",
            f"В timeline только {len(timeline)} блок(ов), минимум 2",
            "timeline",
        ))

    # --- Ссылочная целостность ---
    role_ids = {r.get("role_id") for r in roles if isinstance(r, dict) and isinstance(r.get("role_id"), str)}
    material_ids = {
        m.get("material_id") for m in materials
        if isinstance(m, dict) and isinstance(m.get("material_id"), str)
    }
    block_ids = {
        b.get("block_id") for b in timeline
        if isinstance(b, dict) and isinstance(b.get("block_id"), str)
    }

    for block in timeline:
        if not isinstance(block, dict):
            continue

        block_id = block.get("block_id", "?")
        for role_id in _as_list(block.get("role_ids")):
            if not isinstance(role_id, str) or role_id not in role_ids:
                issues.append(_issue(
                    "ORPHAN_ROLE_ID",
                    "critical",
                    f"role_id '{role_id}' в блоке '{block_id}' не найден в roles",
                    "timeline.role_ids",
                ))
        for material_id in _as_list(block.get("material_ids")):
            if not isinstance(material_id, str) or material_id not in material_ids:
                issues.append(_issue(
                    "ORPHAN_MATERIAL_ID",
                    "critical",
                    f"material_id '{material_id}' в блоке '{block_id}' не найден в materials",
                    "timeline.material_ids",
                ))
        if not _is_non_empty_string(block.get("teacher_script")):
            issues.append(_issue(
                "MISSING_FIELD",
                "high",
                f"teacher_script в блоке '{block_id}' пуст",
                "timeline.teacher_script",
            ))

    # block_ids в ролях, материалах и плане родителей
    for role in roles:
        if not isinstance(role, dict):
            continue
        for block_id in _as_list(role.get("block_ids")):
            if not isinstance(block_id, str) or block_id not in block_ids:
                issues.append(_issue(
                    "ORPHAN_BLOCK_ID",
                    "critical",
                    f"block_id '{block_id}' из roles[{role.get('role_id', '?')}] не найден в timeline",
                    "roles.block_ids",
                ))

    for material in materials:
        if not isinstance(material, dict):
            continue
        for block_id in _as_list(material.get("used_in_blocks")):
            if not isinstance(block_id, str) or block_id not in block_ids:
                issues.append(_issue(
                    "ORPHAN_BLOCK_ID",
                    "critical",
                    f"block_id '{block_id}' из materials[{material.get('material_id', '?')}] не найден в timeline",
                    "materials.used_in_blocks",
                ))

    parent_plan = variant.get("parent_participation_plan")
    parent_plan_dict = parent_plan if isinstance(parent_plan, dict) else {}
    parent_plan_enabled = parent_plan_dict.get("enabled") is True

    for block_id in _as_list(parent_plan_dict.get("block_ids")):
        if not isinstance(block_id, str) or block_id not in block_ids:
            issues.append(_issue(
                "ORPHAN_BLOCK_ID",
                "critical",
                f"block_id '{block_id}' из parent_participation_plan не найден в timeline",
                "parent_participation_plan.block_ids",
            ))

    # --- Логика родителей ---
    participants = input_data.get("participants")
    participants = participants if isinstance(participants, dict) else {}
    parents_enabled = participants.get("parents_enabled") is True
    parents_count = _as_int(participants.get("parents_count")) or 0

    if not parents_enabled:
        for role in roles:
            if isinstance(role, dict) and role.get("participant_type") == "parent":
                issues.append(_issue(
                    "PARENT_ROLE_FORBIDDEN",
                    "critical",
                    f"Роль '{role.get('role_id', '?')}' имеет participant_type='parent' при parents_enabled=false",
                    "roles",
                ))
        if parent_plan_enabled:
            issues.append(_issue(
                "PARENT_PLAN_FORBIDDEN",
                "critical",
                "parent_participation_plan.enabled=true при parents_enabled=false",
                "parent_participation_plan",
            ))
    else:
        if not parent_plan_enabled:
            issues.append(_issue(
                "PARENT_PLAN_MISSING",
                "high",
                "parent_participation_plan отсутствует или enabled=false при parents_enabled=true",
                "parent_participation_plan",
            ))

        role_by_id = {
            role.get("role_id"): role
            for role in roles
            if isinstance(role, dict) and isinstance(role.get("role_id"), str)
        }
        for block in timeline:
            if not isinstance(block, dict):
                continue
            total_parents = 0
            for role_id in _as_list(block.get("role_ids")):
                if not isinstance(role_id, str):
                    continue
                role = role_by_id.get(role_id)
                if role and role.get("participant_type") == "parent":
                    total_parents += _as_int(role.get("count")) or 0
            if total_parents > parents_count:
                issues.append(_issue(
                    "PARENTS_OVER_COUNT",
                    "critical",
                    f"В блоке '{block.get('block_id', '?')}' родителей ({total_parents}) "
                    f"больше parents_count ({parents_count})",
                    "timeline.role_ids",
                ))

    # --- Ресурсы: печать ---
    resources = input_data.get("resources")
    resources = resources if isinstance(resources, dict) else {}
    printer_available = resources.get("printer") is True

    printer_issue_added = False
    for material in materials:
        if not isinstance(material, dict) or material.get("print_required") is not True:
            continue
        if not printer_available and not _has_printer_dependency(material):
            printer_issue_added = True
            issues.append(_issue(
                "PRINTER_REQUIRED_MISSING",
                "high",
                f"Материал '{material.get('material_id', '?')}' требует печати, "
                "но в dependencies нет 'printer', а resources.printer не равен true",
                "materials",
            ))

    # Обратная совместимость: printer_required во входном запросе.
    if resources.get("printer_required") is True and not printer_available and not printer_issue_added:
        has_printer = any(_has_printer_dependency(m) for m in materials if isinstance(m, dict))
        if not has_printer:
            issues.append(_issue(
                "PRINTER_REQUIRED_MISSING",
                "high",
                "printer_required=true, но printer отсутствует в dependencies материалов "
                "и resources.printer не равен true",
                "materials",
            ))

    return issues
