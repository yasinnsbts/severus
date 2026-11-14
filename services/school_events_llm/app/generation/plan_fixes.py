"""Исправления плана, которые программа делает сама, без повторного вызова модели.

GigaChat на просьбу исправить ответ часто возвращает его байт в байт, поэтому то, что однозначно
понятно программе, исправляется сразу (замечания QA 14.11):

- BUG-14: материал назван `jury_scorecard`, а тип у него `quiz`. Этап материалов обязан сохранить тип
  из плана, и вариант с жюри падал с `JURY-SCORECARD` после двух исправлений. Если `material_id`
  совпадает с названием типа (или начинается с него), тип ставится по `material_id`.
- BUG-17: 12 родителей, роли «помощники» и «зрители», а модель делает 12 помощников и 1 зрителя (13).
  Сумма по ролям родителей приводится к числу родителей: уменьшается самая большая роль, у каждой
  роли остаётся хотя бы 1.
- BUG-09: есть помощники, а памятки для них в плане нет; есть «приз зрительских симпатий», а инструкции
  к награждению нет; есть жюри, а листа критериев нет. Программа добавляет такой материал в план
  и в блоки, где заняты эти родители; тексты пишет этап материалов в том же вызове.
"""

from __future__ import annotations

from typing import Any

# Типы материалов, которые можно узнать по `material_id`: модель называет материал по типу,
# но тип ставит другой («jury_scorecard» с типом «quiz»).
TYPES_BY_ID = ("jury_scorecard", "audience_ballot", "parent_instruction", "award_instruction")

# Материалы, без которых сценарий с этими ролями родителей неполный: (условие, тип, название, назначение).
_REQUIRED = {
    "helper": ("parent_instruction", "Памятка для родителей-помощников",
               "Что делают родители-помощники в каждом этапе, когда и как помогают"),
    "evaluator": ("jury_scorecard", "Лист оценки для жюри", "Критерии и шкала, по которым родители-жюри оценивают команды"),
}
_AWARD = ("award_instruction", "Инструкция к награждению", "Как подвести итог голосования зрителей и вручить приз")


def fix_type_by_id(items: Any, where: str, key: str, changes: list[dict[str, Any]]) -> None:
    """Тип материала по его `material_id` для типов из `TYPES_BY_ID` (меняет список на месте).

    Параметры:
        items: `planned_materials` плана или `materials` ответа этапа материалов;
        where: префикс поля для трассы; key: поле типа (`type`);
        changes: список исправлений для трассы.
    """
    if not isinstance(items, list):
        return
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("material_id"), str):
            continue
        mid = item["material_id"].lower()
        for type_name in TYPES_BY_ID:
            if (mid == type_name or mid.startswith(type_name + "_")) and item.get(key) != type_name:
                changes.append({"kind": "type_by_id", "field": f"{where}.{index}.{key}", "from": item.get(key), "to": type_name})
                item[key] = type_name
                break


def fix_parent_role_counts(roles: Any, changes: list[dict[str, Any]]) -> None:
    """Число в роли родителей меньше 1 (модель пишет 0 «остальным») - 1, иначе схема отклоняет план целиком."""
    if not isinstance(roles, list):
        return
    for index, role in enumerate(roles):
        if isinstance(role, dict) and role.get("participant_type") == "parent":
            count = role.get("count")
            if not isinstance(count, int) or count < 1:
                changes.append({"kind": "parent_count_min", "field": f"roles.{index}.count", "from": count, "to": 1})
                role["count"] = 1


def _unique_id(base: str, taken: set[str]) -> str:
    candidate, number = base, 2
    while candidate in taken:
        candidate, number = f"{base}_{number}", number + 1
    return candidate


def fix_plan_for_request(plan: dict[str, Any], parents_enabled: bool, parents_count: int,
                         audience_engagement: str | None) -> list[dict[str, Any]]:
    """Приводит план к запросу: число родителей по ролям и обязательные материалы для их ролей (меняет план на месте).

    Параметры:
        plan: план варианта (словарь `scenario_plan` после `complete_block_roles`);
        parents_enabled, parents_count, audience_engagement: из нормализованного запроса.

    Возвращает:
        Список исправлений для трассы.
    """
    changes: list[dict[str, Any]] = []
    if not parents_enabled:
        return changes
    parent_roles = [r for r in plan.get("roles", []) if r.get("participant_type") == "parent"]

    # BUG-17: сумма по ролям родителей не больше числа родителей.
    total = sum(r["count"] for r in parent_roles)
    if parents_count >= len(parent_roles) and total > parents_count:
        before = {r["role_id"]: r["count"] for r in parent_roles}
        while total > parents_count:
            largest = max(parent_roles, key=lambda r: r["count"])
            if largest["count"] <= 1:
                break
            largest["count"] -= 1
            total -= 1
        changes.append({"kind": "parent_counts_balanced", "parents_count": parents_count,
                        "from": before, "to": {r["role_id"]: r["count"] for r in parent_roles}})

    # BUG-09: материалы, без которых роль родителей неполная.
    planned = plan.setdefault("planned_materials", [])
    types = {m.get("type") for m in planned}
    taken = {m.get("material_id") for m in planned}
    blocks = plan.get("blocks", [])
    needed: list[tuple[tuple[str, str, str], list[str]]] = []
    for mode, spec in _REQUIRED.items():
        role_ids = {r["role_id"] for r in parent_roles if r.get("role_mode") == mode}
        if role_ids and spec[0] not in types:
            needed.append((spec, [b["block_id"] for b in blocks if role_ids & set(b.get("role_ids", []))]))
    if audience_engagement == "audience_award" and _AWARD[0] not in types:
        audience = {r["role_id"] for r in parent_roles if r.get("role_mode") == "audience"}
        with_audience = [b["block_id"] for b in blocks if audience & set(b.get("role_ids", []))]
        needed.append((_AWARD, with_audience[-1:] or [b["block_id"] for b in blocks[-1:]]))
    for (type_name, title, purpose), block_ids in needed:
        block_ids = block_ids or [b["block_id"] for b in blocks[:1]]
        material_id = _unique_id(type_name, taken)
        taken.add(material_id)
        planned.append({"material_id": material_id, "type": type_name, "title": title, "purpose": purpose})
        for block in blocks:
            if block["block_id"] in block_ids and material_id not in block.setdefault("planned_material_ids", []):
                block["planned_material_ids"].append(material_id)
        changes.append({"kind": "required_material_added", "material_id": material_id, "type": type_name, "block_ids": block_ids})
    return changes


def fallback_material(type_name: str, material_id: str, title: str, plan: dict[str, Any],
                      timeline: list[dict[str, Any]]) -> dict[str, Any]:
    """Простая версия обязательного материала, если этап материалов его не написал.

    Материал добавила в план программа (`fix_plan_for_request`); если модель его всё же пропустила,
    вариант не должен падать с `REF-MATERIAL`. Памятка помощникам собирается из этапов, где они заняты.

    Возвращает:
        Словарь материала контракта 03.
    """
    roles = {r["role_id"]: r for r in plan.get("roles", [])}
    mode = {"parent_instruction": "helper", "jury_scorecard": "evaluator"}.get(type_name)
    role_ids = {rid for rid, r in roles.items() if r.get("participant_type") == "parent" and (mode is None or r.get("role_mode") == mode)}
    blocks = [b for b in timeline if role_ids & set(b.get("role_ids", []))] or timeline[:1]
    if type_name == "parent_instruction":
        lines = ["Спасибо, что помогаете на мероприятии! Что вы делаете на каждом этапе:", ""]
        for b in blocks:
            end = b["start_minute"] + b["duration_minutes"]
            purpose = b.get("purpose", "").rstrip(".")
            lines.append(f"- «{b['title']}» ({b['start_minute']}-{end} мин): помогаете педагогу и детям. Задача этапа: {purpose[:1].lower() + purpose[1:]}.")
        lines += ["", "Помогайте, но не делайте задание за детей. Если что-то непонятно, спросите педагога до начала этапа."]
        notes = "Раздайте родителям-помощникам до начала мероприятия и коротко объясните их задачи."
    elif type_name == "jury_scorecard":
        lines = ["Лист оценки команд. Оценка по каждому критерию: 0 - нет, 1 - частично, 2 - полностью.", "",
                 "Команда | Идея и польза | Работа в команде | Выступление | Сумма",
                 "1 | | | |", "2 | | | |", "3 | | | |", "4 | | | |", "5 | | | |", "",
                 "Не оценивайте команду, в которой работает ваш ребёнок: поставьте прочерк."]
        notes = "Раздайте членам жюри перед выступлениями, объявите критерии вслух всему классу."
    else:
        lines = ["1. Соберите бюллетени и вместе с помощником посчитайте голоса.",
                 "2. Объявите результат: назовите команду, набравшую больше всего голосов.",
                 "3. Вручите приз зрительских симпатий и поблагодарите все команды за работу.",
                 "4. При равенстве голосов отметьте все команды, набравшие одинаковое число голосов."]
        notes = "Используйте после голосования зрителей."
    return {"material_id": material_id, "type": type_name, "title": title, "used_in_blocks": [b["block_id"] for b in blocks],
            "audience": "parent" if type_name in ("parent_instruction", "jury_scorecard") else "teacher",
            "content": "\n".join(lines), "teacher_notes": notes, "print_required": False, "dependencies": [],
            "estimated_preparation_minutes": 5, "family_task": False}