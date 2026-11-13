"""Приведение идентификаторов и зависимостей из ответа модели к допустимому виду до проверки схемы.

Схема требует `material_id` и `role_id` вида `^[a-z][a-z0-9_]*$`, а `dependencies` - только из словаря
`catalog/dependencies.json`. Модели пишут `Card-Task`, `карточки_1`, `scissors_and_glue`, `flipchart` и т. п.
Без исправления такой ответ не проходит схему или валидацию (`DEP-UNKNOWN`), и этап повторяется
или вариант падает. Здесь всё, что можно исправить однозначно, исправляется программой.
"""

from __future__ import annotations

import re
from typing import Any

_TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
})
_ID_OK = re.compile(r"^[a-z][a-z0-9_]*$")
_BLOCK = re.compile(r"^block[_\-\s]*0*(\d{1,2})$", re.I)
MAX_ID_LEN = 48

# Синонимы зависимостей: то, что модели пишут вместо ID из словаря. Ключи - уже в виде slug.
DEPENDENCY_SYNONYMS: dict[str, str] = {
    "whiteboard": "board", "blackboard": "board", "chalk": "board", "chalkboard": "board", "doska": "board",
    "a4": "paper", "paper_a4": "paper", "a4_paper": "paper", "sheets": "paper", "sheet": "paper", "printed_paper": "paper",
    "bumaga": "paper", "colored_paper": "paper",
    "flipchart": "whatman", "poster_paper": "whatman", "poster": "whatman", "a3": "whatman", "a3_paper": "whatman",
    "vatman": "whatman", "big_paper": "whatman",
    "marker": "markers", "felt_pens": "markers", "felt_tip_pens": "markers", "flomastery": "markers",
    "pencils": "colored_pencils", "crayons": "colored_pencils", "colour_pencils": "colored_pencils",
    "karandashi": "colored_pencils",
    "pen": "pens", "ballpoint_pens": "pens", "ruchki": "pens",
    "stickers": "sticky_notes", "sticky_note": "sticky_notes", "post_it": "sticky_notes", "postit": "sticky_notes",
    "stikery": "sticky_notes",
    "scissor": "scissors", "nozhnitsy": "scissors", "glue_stick": "glue", "kley": "glue",
    "scotch": "tape", "scotch_tape": "tape", "adhesive_tape": "tape", "masking_tape": "tape", "skotch": "tape",
    "urn": "ballot_box", "ballot_urn": "ballot_box", "box": "ballot_box", "voting_box": "ballot_box",
    "stopwatch": "timer", "clock": "timer", "hourglass": "timer", "sekundomer": "timer",
    "speakers": "audio", "speaker": "audio", "music": "audio", "sound": "audio", "audio_system": "audio",
    "screen": "projector", "presentation": "projector", "slides": "projector", "multimedia": "projector",
    "wifi": "internet", "wi_fi": "internet", "online": "internet",
    "print": "printer", "printing": "printer",
}


def slug_id(value: Any, prefix: str) -> Any:
    """Приводит ID к виду `^[a-z][a-z0-9_]*$`: регистр, транслитерация, `-` и пробелы в `_`.

    Одинаковые исходные значения дают одинаковый результат, поэтому ссылки между частями ответа сохраняются.
    Параметры: value - исходный ID; prefix - приставка, если ID начинается с цифры.
    Возвращает: исправленный ID или исходное значение, если исправить нечего.
    """
    if not isinstance(value, str) or _ID_OK.match(value):
        return value
    s = value.strip().lower().translate(_TRANSLIT)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    if not s:
        return value
    if s[0].isdigit():
        s = f"{prefix}_{s}"
    return s[:MAX_ID_LEN].rstrip("_")


def block_id(value: Any) -> Any:
    """`Block_2`, `block-2`, `block 02` -> `block_02`."""
    if isinstance(value, str):
        m = _BLOCK.match(value.strip())
        if m:
            return f"block_{int(m.group(1)):02d}"
    return value


def _fix_list(values: Any, fn, where: str, changes: list[dict[str, Any]]) -> Any:
    if not isinstance(values, list):
        return values
    out: list[Any] = []
    for v in values:
        new = fn(v)
        if new != v:
            changes.append({"kind": "id_fixed", "field": where, "from": v, "to": new})
        if new not in out:
            out.append(new)
    return out


def _fix_key(obj: Any, key: str, fn, where: str, changes: list[dict[str, Any]]) -> None:
    if isinstance(obj, dict) and key in obj:
        new = fn(obj[key])
        if new != obj[key]:
            changes.append({"kind": "id_fixed", "field": where, "from": obj[key], "to": new})
            obj[key] = new


def normalize_ids(stage: str, data: dict, changes: list[dict[str, Any]]) -> None:
    """Исправляет `material_id`, `role_id`, ссылки на них и ID блоков в ответе этапа (на месте).

    Повторяющиеся материалы плана с одинаковым ID после исправления схлопываются в один.
    """
    mat = lambda v: slug_id(v, "mat")  # noqa: E731
    role = lambda v: slug_id(v, "role")  # noqa: E731

    def block_refs(b: dict, i: int, roles_key: str, mats_key: str) -> None:
        _fix_key(b, "block_id", block_id, f"blocks.{i}.block_id", changes)
        if roles_key in b:
            b[roles_key] = _fix_list(b[roles_key], role, f"blocks.{i}.{roles_key}", changes)
        if mats_key in b:
            b[mats_key] = _fix_list(b[mats_key], mat, f"blocks.{i}.{mats_key}", changes)

    if stage == "scenario_plan":
        for j, r in enumerate(data.get("roles") or []):
            _fix_key(r, "role_id", role, f"roles.{j}.role_id", changes)
        seen: set[Any] = set()
        planned = []
        for j, m in enumerate(data.get("planned_materials") or []):
            _fix_key(m, "material_id", mat, f"planned_materials.{j}.material_id", changes)
            mid = m.get("material_id") if isinstance(m, dict) else None
            if mid in seen:
                changes.append({"kind": "duplicate_material_dropped", "material_id": mid})
                continue
            seen.add(mid)
            planned.append(m)
        if isinstance(data.get("planned_materials"), list):
            data["planned_materials"] = planned
        for i, b in enumerate(data.get("blocks") or []):
            if isinstance(b, dict):
                block_refs(b, i, "role_ids", "planned_material_ids")
        grouping = data.get("grouping_request")
        if isinstance(grouping, dict) and "block_ids" in grouping:
            grouping["block_ids"] = _fix_list(grouping["block_ids"], block_id, "grouping_request.block_ids", changes)
        for j, v in enumerate((data.get("concept") or {}).get("values_to_mechanics") or []):
            if isinstance(v, dict) and "block_ids" in v:
                v["block_ids"] = _fix_list(v["block_ids"], block_id, f"concept.values_to_mechanics.{j}.block_ids", changes)
    elif stage == "scenario_blocks":
        for i, b in enumerate(data.get("blocks") or []):
            if isinstance(b, dict):
                block_refs(b, i, "role_ids", "material_ids")
    elif stage == "scenario_block":
        if isinstance(data.get("block"), dict):
            block_refs(data["block"], 0, "role_ids", "material_ids")
    elif stage == "materials":
        for j, m in enumerate(data.get("materials") or []):
            _fix_key(m, "material_id", mat, f"materials.{j}.material_id", changes)
            if isinstance(m, dict) and "used_in_blocks" in m:
                m["used_in_blocks"] = _fix_list(m["used_in_blocks"], block_id, f"materials.{j}.used_in_blocks", changes)
        voting = data.get("voting")
        if isinstance(voting, dict):
            if "material_ids" in voting:
                voting["material_ids"] = _fix_list(voting["material_ids"], mat, "voting.material_ids", changes)
            _fix_key(voting, "block_id", block_id, "voting.block_id", changes)


def normalize_dependencies(data: dict, dependency_ids: set[str], changes: list[dict[str, Any]]) -> None:
    """Оставляет в `materials[].dependencies` только ID из словаря зависимостей.

    Синонимы (`flipchart`, `scotch`, `stopwatch`…) заменяются на ID словаря. То, что сопоставить нельзя,
    убирается из `dependencies` и дописывается в `teacher_notes` («Также понадобится: …»), чтобы педагог
    не потерял эту информацию, а проверка не падала с `DEP-UNKNOWN`.
    """
    for j, m in enumerate(data.get("materials") or []):
        if not isinstance(m, dict) or not isinstance(m.get("dependencies"), list):
            continue
        kept: list[str] = []
        unknown: list[str] = []
        for raw in m["dependencies"]:
            if not isinstance(raw, str) or not raw.strip():
                continue
            key = slug_id(raw, "dep")
            key = key if key in dependency_ids else DEPENDENCY_SYNONYMS.get(key, key)
            if key in dependency_ids:
                if key != raw:
                    changes.append({"kind": "dependency_fixed", "material_id": m.get("material_id"), "from": raw, "to": key})
                if key not in kept:
                    kept.append(key)
            else:
                unknown.append(raw.strip())
        m["dependencies"] = kept
        if unknown:
            changes.append({"kind": "dependency_moved_to_notes", "material_id": m.get("material_id"), "values": unknown})
            note = "Также понадобится: " + ", ".join(unknown) + "."
            notes = m.get("teacher_notes")
            m["teacher_notes"] = f"{notes.rstrip()} {note}" if isinstance(notes, str) and notes.strip() else note


UNASSIGNED_BLOCK = "__unassigned__"
NOT_FAMILY_TASK_TYPES = {"parent_instruction", "audience_ballot", "jury_scorecard", "award_instruction",
                         "teacher_instruction", "props_checklist", "slide_outline"}


# Английские ключи, которые модели пишут внутри содержания материала, - по-русски для педагога.
_KEY_RU = {"question": "Вопрос", "answer": "Ответ", "answers": "Ответы", "correct_answer": "Правильный ответ",
           "options": "Варианты", "title": "Название", "name": "Название", "description": "Описание",
           "task": "Задание", "hint": "Подсказка", "example": "Пример", "text": "Текст", "role": "Роль"}


def content_to_text(value: Any) -> Any:
    """Текст материала, если модель вернула его списком или словарём, а не строкой.

    - Список строк -> нумерованный список (вопросы, пункты чек-листа).
    - Список словарей -> нумерованные пункты «ключ: значение; …» (карточки станций, вопросы с ответами).
    - Словарь -> строки «ключ: значение».
    Строка возвращается без изменений.
    """
    def item(v: Any) -> str:
        if isinstance(v, dict):
            return "; ".join(f"{_KEY_RU.get(str(k).lower(), k)}: {item(x)}" for k, x in v.items() if x not in (None, "", []))
        if isinstance(v, list):
            return ", ".join(item(x) for x in v)
        return str(v).strip()

    if isinstance(value, list):
        lines = [item(v) for v in value if v not in (None, "", [], {})]
        return "\n".join(f"{i}. {line}" for i, line in enumerate(lines, 1))
    if isinstance(value, dict):
        return "\n".join(f"{_KEY_RU.get(str(k).lower(), k)}: {item(v)}" for k, v in value.items() if v not in (None, "", []))
    return value


def normalize_material_fields(data: dict, changes: list[dict[str, Any]]) -> None:
    """Поля материалов, которые модели заполняют не по схеме, но смысл понятен.

    - `content` списком или словарём -> текст (`content_to_text`).
    - Пустой `used_in_blocks` -> временная метка; после сборки сценария `fix_material_refs` поставит
      блоки, которые ссылаются на материал по плану (так бывает с заданием семье «до мероприятия»).
    - `family_task` у памятки родителям, бюллетеня и других материалов для взрослых снимается:
      это не задание семье, и проверка `VAL-005` не должна превращать их в раздаточный материал.
    """
    for j, m in enumerate(data.get("materials") or []):
        if not isinstance(m, dict):
            continue
        if m.get("family_task") and m.get("type") in NOT_FAMILY_TASK_TYPES:
            # Памятка родителям, бюллетень и т. п. - не задание семье, хотя модель иногда так их помечает.
            m["family_task"] = False
            changes.append({"kind": "family_task_cleared", "material_id": m.get("material_id"), "type": m.get("type")})
        if isinstance(m.get("content"), (list, dict)):
            m["content"] = content_to_text(m["content"])
            changes.append({"kind": "content_to_text", "material_id": m.get("material_id")})
        content = m.get("content")
        if m.get("type") == "props_checklist" and isinstance(content, str) and len(content.strip()) < 20 and m.get("title"):
            # Чек-лист реквизита без текста: собираем из названия и заметок, чтобы не повторять весь этап.
            notes = (m.get("teacher_notes") or "").strip()
            m["content"] = f"Подготовить: {m['title']}." + (f" {notes}" if notes else "")
            changes.append({"kind": "props_content_filled", "material_id": m.get("material_id")})
        if isinstance(m.get("used_in_blocks"), list) and not m["used_in_blocks"]:
            m["used_in_blocks"] = [UNASSIGNED_BLOCK]
            changes.append({"kind": "used_in_blocks_unassigned", "material_id": m.get("material_id")})