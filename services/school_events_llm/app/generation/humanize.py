"""Технические ID в тексте для людей: замена на названия материалов, этапов, ролей и расходников.

Модель пишет сценарий блоков раньше, чем появляются названия материалов, и иногда вставляет в реплики
и инструкции внутренние ID: «(раздаёт heart_cards)», «в блоке block_03», «коробку-capsule_box»,
«materials: decoration_kit», «`card_task`». Педагог такие обозначения видеть не должен.

`humanize_variant` проходит по всем текстовым полям собранного варианта и заменяет известные ID
на названия. Поля-ссылки (`material_ids`, `used_in_blocks`, `block_ids` и т. п.) не трогаются.
Неизвестные латинские обозначения остаются как есть: их ловит проверка `TECH-ID-IN-TEXT`.
"""

from __future__ import annotations

import re
from typing import Any

from .ids import KEY_RU, _singular

# Названия типов материалов для текста, если материала с таким ID в варианте нет.
MATERIAL_TYPE_TITLES = {
    "teacher_instruction": "памятка педагогу",
    "worksheet": "рабочий лист",
    "activity_card": "карточки заданий",
    "slide_outline": "план слайдов",
    "quiz": "викторина",
    "discussion_questions": "вопросы для обсуждения",
    "handout": "раздаточный материал",
    "props_checklist": "список реквизита",
    "parent_instruction": "памятка для родителей",
    "audience_ballot": "бюллетень для голосования",
    "jury_scorecard": "оценочный лист жюри",
    "award_instruction": "инструкция к награждению",
}

# Прочие служебные значения, которые модель изредка переносит в текст.
OTHER_TITLES = {
    "pupils_group": "группы учеников",
    "pupils_all": "все ученики",
    "paper_ballot": "бумажные бюллетени",
    "audience_award": "приз зрительских симпатий",
    "small_groups": "малые группы",
    "whole_class": "весь класс",
    # Поле плана участия родителей, которое модель называет «материалом» (замечание QA 14.11).
    "teacher_fallback": "запасной план на случай, если родители не придут",
    "parent_participation_plan": "план участия родителей",
}

# Латинское обозначение: snake_case (card_task, block_03) или одно слово из известных ID.
_SNAKE = r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+"
_URL = re.compile(r"https?://\S+|www\.\S+|[\w.+-]+@[\w-]+\.[\w.]+")
_QUOTES = "`'\"«»“”"
# Слева от ID нет латиницы, цифры, «_», «/», «.», «@»; дефис допустим только после русского слова («коробку-capsule_box»).
_LEFT = r"(?<![A-Za-z0-9_/.@])(?<![A-Za-z0-9_]-)"

# Текстовые поля варианта: путь задаётся функцией обхода ниже.
_BLOCK_TEXT = ("title", "purpose", "teacher_script")
_MATERIAL_TEXT = ("title", "content", "teacher_notes")


def _clean_title(title: str) -> str:
    """Убирает внешние кавычки названия («Капсула пожеланий» -> Капсула пожеланий), внутренние оставляет."""
    title = title.strip()
    if len(title) > 1 and title[0] in _QUOTES and title[-1] in _QUOTES and title.count("«") <= 1:
        title = title[1:-1].strip()
    return title


def _quoted(title: str) -> str:
    """Название в ёлочках с заглавной буквы; если внутри уже есть ёлочки, второй слой не добавляется."""
    title = title[:1].upper() + title[1:]
    return title if "«" in title else f"«{title}»"


def build_names(variant: dict[str, Any], dependencies: dict[str, dict[str, Any]] | None = None,
                planned: list[dict[str, Any]] | None = None) -> dict[str, str]:
    """Словарь «ID -> как написать в тексте» для одного варианта.

    Порядок важен: материал варианта главнее одноимённого типа материала и запланированного материала.
    Всё пишется в кавычках-ёлочках как название: так замена читается в любом падеже предложения.
    `planned` - материалы плана (`material_id`, `type`, необязательный `title`): нужны, если материал
    упомянут в репликах, но на этапе материалов не создан.
    """
    names: dict[str, str] = {}
    for key, title in {**OTHER_TITLES, **MATERIAL_TYPE_TITLES}.items():
        names[key] = _quoted(title)
    for dep_id, item in (dependencies or {}).items():
        label = _clean_title(str(item.get("label") or ""))
        if label:
            names[dep_id] = _quoted(label)
    for item in planned or []:
        title = _clean_title(str(item.get("title") or "")) or MATERIAL_TYPE_TITLES.get(str(item.get("type")), "")
        if item.get("material_id") and title:
            names[item["material_id"]] = _quoted(title)
    for role in variant.get("roles") or []:
        title = _clean_title(str(role.get("title") or ""))
        if role.get("role_id") and title:
            names[role["role_id"]] = _quoted(title)
    for block in variant.get("timeline") or []:
        title = _clean_title(str(block.get("title") or ""))
        if block.get("block_id") and title:
            names[block["block_id"]] = _quoted(title)
    for material in variant.get("materials") or []:
        title = _clean_title(str(material.get("title") or ""))
        if material.get("material_id") and title:
            names[material["material_id"]] = _quoted(title)
    return names


def _token_pattern(names: dict[str, str]) -> re.Pattern[str]:
    singles = sorted((k for k in names if "_" not in k), key=len, reverse=True)
    alternatives = [_SNAKE] + [re.escape(s) for s in singles]
    # Не часть слова, пути или адреса: слева нет буквы, цифры, «/», «.», «_»; справа нет буквы, цифры, «/», «_».
    return re.compile(_LEFT + r"(?:" + "|".join(alternatives) + r")(?![\w/])")


def _stem(text: str) -> str:
    word = re.sub(r"[«»\"'`]", "", text).strip().split(" ")[0].lower()
    return word[:5] if len(word) >= 5 else word


def _shape(key: str) -> str:
    """ID без различий в числе частей: «commitments_book_pages» и «commitment_book_page» дают одно и то же."""
    return "_".join(_singular(part) for part in key.split("_"))


def _by_shape(names: dict[str, str]) -> dict[str, str]:
    """`_shape(ID) -> ID` для составных ID; если под одну форму подходят два ID, форма не используется."""
    found: dict[str, str | None] = {}
    for key in names:
        if "_" in key:
            shape = _shape(key)
            found[shape] = key if shape not in found else None
    return {shape: key for shape, key in found.items() if key}


def humanize_text(text: str, names: dict[str, str]) -> tuple[str, list[str]]:
    """Заменяет известные ID в одном тексте. Возвращает новый текст и список заменённых ID.

    ID, который отличается от известного только числом частей («commitments_book_pages» при материале
    «commitment_book_pages», замечание QA 14.11, BUG-16), заменяется названием этого материала.
    """
    if not text or not names:
        return text, []
    pattern = _token_pattern(names)
    shapes = _by_shape(names)
    urls = [m.span() for m in _URL.finditer(text)]
    replaced: list[str] = []
    out: list[str] = []
    pos = 0
    for m in pattern.finditer(text):
        token = m.group(0)
        key = token if token in names else shapes.get(_shape(token)) if "_" in token else None
        if not key or any(a <= m.start() < b for a, b in urls):
            continue
        start, end = m.start(), m.end()
        title = names[key]
        # Кавычки и обратные апострофы вокруг ID: `card_task`, "card_task", «card_task».
        if start > 0 and end < len(text) and text[start - 1] in _QUOTES and text[end] in _QUOTES:
            start, end = start - 1, end + 1
        before = text[pos:start]
        # «materials: id», «material id», «материалы: id» - служебная приставка перед ID.
        prefix = re.search(r"(?:\bmaterials?|\bматериал(?:ы|а)?)\s*:?\s*$", before, re.I)
        if prefix and prefix.group(0).strip().lower().startswith("material"):
            before = before[:prefix.start()]
        # «коробку-capsule_box», «карточки-heart_cards»: дефис превращается в пробел.
        if before.endswith("-") and len(before) > 1 and before[-2].isalpha():
            before = before[:-1] + " "
        # Скобка только с ID (и, может быть, одним-двумя русскими словами): «бюллетени (audience_ballot)».
        open_paren = re.search(r"\(\s*((?:[а-яё]+\s+){0,2})$", before, re.I)
        close_paren = re.match(r"\s*\)", text[end:])
        if open_paren and close_paren:
            stem = _stem(title)
            context = before[:open_paren.start()][-80:].lower()
            if stem and stem in context:
                # Название уже есть рядом: скобка с ID не нужна вовсе.
                out.append(before[:open_paren.start()].rstrip())
                pos = end + close_paren.end()
                replaced.append(token)
                continue
            words = open_paren.group(1).split()
            same = next((i for i, word in enumerate(words) if stem and stem in word.lower()), None)
            if same is not None:
                # «(карточки card_task)» -> «(«Карточки заданий»)»: слово из скобки повторяет название.
                # Слова перед ним остаются: «(раздаёт странички commitment_book_pages)» -> «(раздаёт «Странички…»)».
                before = before[:open_paren.start()] + "(" + "".join(word + " " for word in words[:same])
        out.append(before)
        out.append(title)
        pos = end
        replaced.append(token)
    if not replaced:
        return text, []
    out.append(text[pos:])
    result = "".join(out)
    # После замен могли остаться двойные пробелы и пробел перед знаком препинания.
    result = re.sub(r"[ \t]{2,}", " ", result)
    result = re.sub(r" +([,.;:!?)])", r"\1", result)
    return result, replaced


def humanize_variant(variant: dict[str, Any], dependencies: dict[str, dict[str, Any]] | None = None,
                     planned: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Заменяет технические ID во всех текстовых полях варианта (на месте). Возвращает список замен для трассы."""
    names = build_names(variant, dependencies, planned)
    changes: list[dict[str, Any]] = []

    def fix(container: dict[str, Any], key: str, where: str) -> None:
        value = container.get(key)
        if isinstance(value, str):
            new, ids = humanize_text(value, names)
            if ids:
                container[key] = new
                changes.append({"field": where, "ids": ids})
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, str):
                    new, ids = humanize_text(item, names)
                    if ids:
                        value[index] = new
                        changes.append({"field": f"{where}[{index}]", "ids": ids})

    concept = variant.get("concept") or {}
    for key in ("summary", "goal", "tasks", "expected_outcomes"):
        fix(concept, key, f"concept.{key}")
    for block in variant.get("timeline") or []:
        for key in _BLOCK_TEXT + ("pupil_actions",):
            fix(block, key, f"timeline.{block.get('block_id')}.{key}")
    for material in variant.get("materials") or []:
        for key in _MATERIAL_TEXT:
            fix(material, key, f"materials.{material.get('material_id')}.{key}")
    fix(variant, "teacher_instructions", "teacher_instructions")
    plan = variant.get("parent_participation_plan") or {}
    fix(plan, "teacher_fallback", "parent_participation_plan.teacher_fallback")
    voting = plan.get("voting") or {}
    for key in ("criterion", "tie_rule", "award_title"):
        fix(voting, key, f"parent_participation_plan.voting.{key}")
    return changes


def leftover_ids(text: str) -> list[str]:
    """Латинские snake_case-обозначения, оставшиеся в тексте (без адресов). Для проверки TECH-ID-IN-TEXT."""
    if not text:
        return []
    clean = _URL.sub(" ", text)
    return re.findall(_LEFT + r"(?:block_\d+|" + _SNAKE + r")(?![\w/])", clean)


# Фраза о самом сценарии, которую модель переносит из требований промпта в реплику:
# «Объём текста сценария для педагога составляет около 780 символов.» (прогон 14.11, Рождество 7 кл).
# Нужны и число символов (знаков), и слово о тексте: «символы области» и «герб - символ» не трогаются.
_META_SENTENCE = re.compile(r"[^.!?\n]*[.!?]?")
_META_SIZE = re.compile(r"\b\d{2,5}\s*(?:символ|знак)\w*", re.I)
# Английская подпись поля перед текстом пункта: «1. side_a: Грязно в классе», «station_name: Школа будущего;
# Задание: …» (прогоны 14.11). Знакомая подпись - по-русски (словарь `ids.KEY_RU`, общий с содержанием
# материалов), незнакомая snake_case - убирается, пометка стороны
# карточки - убирается. Одно незнакомое английское слово с двоеточием не трогается: это может быть название.
_FIELD_LABEL_RU = KEY_RU
_FIELD_LABEL = re.compile(
    r"(?P<pre>^[ \t]*(?:\d{1,2}[.)][ \t]*|[-\u2022*][ \t]*)?|[;.?!][ \t]+)(?P<label>[A-Za-z]+(?:_[A-Za-z0-9]+)*)[ \t]*:(?!//)[ \t]*",
    re.M,
)


def _relabel(match: re.Match[str], removed: list[str]) -> str:
    label = match.group("label")
    key = label.lower()
    if key in _FIELD_LABEL_RU:
        removed.append(label + ":")
        title = _FIELD_LABEL_RU[key]
        return match.group("pre") + (f"{title}: " if title else "")
    if "_" in key:
        removed.append(label + ":")
        return match.group("pre")
    return match.group(0)
_META_WORD = re.compile(r"объ[её]м|длин\w*\s+(?:текст|реплик|сценари)|текст\w*\s+(?:сценари|реплик)|реплик\w*\s+педагог", re.I)


def _drop_meta(text: str) -> tuple[str, list[str]]:
    removed: list[str] = []
    kept: list[str] = []
    text = _FIELD_LABEL.sub(lambda m: _relabel(m, removed), text)
    for line in text.split("\n"):
        parts = []
        for sentence in _META_SENTENCE.findall(line):
            if sentence.strip() and _META_SIZE.search(sentence) and _META_WORD.search(sentence):
                removed.append(sentence.strip())
            else:
                parts.append(sentence)
        new_line = "".join(parts).rstrip()
        if new_line.strip() or not line.strip():
            kept.append(new_line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip(), removed


def drop_meta_notes(variant: dict[str, Any]) -> list[dict[str, Any]]:
    """Убирает из текстов для педагога фразы о самом сценарии («объём текста… около 780 символов»)
    и английские подписи полей перед текстом пункта («side_a:», «station_name:»).

    Возвращает:
        Список изменений для трассы: поле и убранные фразы.
    """
    changes: list[dict[str, Any]] = []

    def fix(obj: Any, key: str, where: str) -> None:
        if isinstance(obj, dict) and isinstance(obj.get(key), str):
            new, removed = _drop_meta(obj[key])
            if removed:
                obj[key] = new
                changes.append({"field": where, "removed": removed})

    for block in variant.get("timeline") or []:
        fix(block, "teacher_script", f"timeline.{block.get('block_id')}.teacher_script")
        actions = block.get("pupil_actions") or []
        for index in range(len(actions)):
            holder = {"text": actions[index]}
            fix(holder, "text", f"timeline.{block.get('block_id')}.pupil_actions.{index}")
            actions[index] = holder["text"]
    for material in variant.get("materials") or []:
        for key in ("content", "teacher_notes"):
            fix(material, key, f"materials.{material.get('material_id')}.{key}")
    instructions = variant.get("teacher_instructions") or []
    for index in range(len(instructions)):
        holder = {"text": instructions[index]}
        fix(holder, "text", f"teacher_instructions.{index}")
        instructions[index] = holder["text"]
    return changes


# Дата подписи в шаблоне письма или бланка отдельной строкой: «1 сентября 2023 г.», «Дата: 01.09.2023»,
# «___________ 2023 г.» в сертификате (прогон QA 14.11).
# Это не факт, а место для даты, и год модель ставит неверный (прогон QA 14.11: 2023 вместо текущего года).
_MONTHS = r"(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)"
_DATE_LINE = re.compile(
    r"^(?P<label>[ \t]*(?:дата|число)?[ \t]*:?[ \t]*)(?:«?\d{1,2}»?[ \t]+" + _MONTHS + r"|\d{1,2}\.\d{1,2}\.|(?:«_+»[ \t]*)?_{3,})"
    r"[ \t]*(?:19|20)\d{2}[ \t]*(?:г\.?|года?)?[ \t]*(?P<close>[\"»”]?)[ \t]*$",
    re.I | re.M,
)
DATE_BLANK = "«___» __________ 20__ г."


def blank_template_dates(variant: dict[str, Any]) -> list[dict[str, Any]]:
    """Заменяет дату-строку в материалах (подпись письма, бланк) на пустое место для даты.

    Возвращает:
        Список изменений для трассы: материал и заменённые строки.
    """
    changes: list[dict[str, Any]] = []
    for material in variant.get("materials") or []:
        content = material.get("content")
        if not isinstance(content, str):
            continue
        found = [m.group(0).strip() for m in _DATE_LINE.finditer(content)]
        if found:
            material["content"] = _DATE_LINE.sub(lambda m: m.group("label") + DATE_BLANK + m.group("close"), content)
            changes.append({"field": f"materials.{material.get('material_id')}.content", "dates": found})
    return changes