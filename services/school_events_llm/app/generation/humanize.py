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

from .dates import MONTHS as _MONTHS
from .ids import _THING_RU, KEY_RU, _singular, one_edit as _one_edit

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


# Названия наших служебных полей, которые модель употребляет в тексте как слово: «Используйте fact_claims
# из справки для исторической части» (памятка к материалу, прогон 15.11), «следуя рекомендациям в teacher_notes
# каждого материала» (подготовка педагога, прогон 15.11). Пишутся без ёлочек: это не название.
TECH_TERMS = {"fact_claims": "проверенные факты", "fact_claim": "проверенный факт", "source_id": "источник",
              "fragment_id": "фрагмент источника", "teacher_notes": "заметки для педагога"}
# Эти три ищутся и нестрого («claims_fact», «fact_cliams», «id_source»); «fact_claim» - только точно: из тех же
# слов, что «fact_claims», и нестрогий поиск при двух кандидатах ничего бы не подставил.
TECH_TERMS_FUZZY = {"fact_claims", "source_id", "fragment_id"}
# Те же слова после предлога: «рекомендациям в teacher_notes» -> «в заметках для педагога», а не «в заметки для
# педагога» (финальный прогон 15.11, второй раз та же фраза). Без предлога - форма из `TECH_TERMS`.
_TERM_CASES = {
    "fact_claims": ("проверенных фактах", "проверенных фактов", "проверенным фактам"),
    "fact_claim": ("проверенном факте", "проверенного факта", "проверенному факту"),
    "source_id": ("источнике", "источника", "источнику"),
    "fragment_id": ("фрагменте источника", "фрагмента источника", "фрагменту источника"),
    "teacher_notes": ("заметках для педагога", "заметок для педагога", "заметкам для педагога"),
}
# Предлоги предложного, родительного и дательного падежа; «на» и «с» не берутся: падеж по ним не определить.
_TERM_PREPOSITIONS = (
    re.compile(r"(?:^|[\s(«\"])(?:в|во|(?P<o>о)|об|при)\s+$", re.I),
    re.compile(r"(?:^|[\s(«\"])(?:из|для|без|до|от|у|из-за|кроме|вместо)\s+$", re.I),
    re.compile(r"(?:^|[\s(«\"])(?:по|к|ко|согласно)\s+$", re.I),
)


def _term_form(key: str | None, title: str, before: str) -> tuple[str, str]:
    """Служебное поле, упомянутое как слово, - в падеже по предлогу перед ним («о» перед гласной - «об»).

    Возвращает текст перед словом и само слово; не служебное поле - без изменений.
    """
    if key not in _TERM_CASES or title != TECH_TERMS.get(key):
        return before, title
    for forms_index, preposition in enumerate(_TERM_PREPOSITIONS):
        found = preposition.search(before)
        if found:
            form = _TERM_CASES[key][forms_index]
            if found.groupdict().get("o") and form[0] in "аеёиоуыэюя":
                at = found.start("o")
                before = before[:at] + before[at] + "б" + before[at + 1:]
            return before, form
    return before, title


def build_names(variant: dict[str, Any], dependencies: dict[str, dict[str, Any]] | None = None,
                planned: list[dict[str, Any]] | None = None) -> dict[str, str]:
    """Словарь «ID -> как написать в тексте» для одного варианта.

    Порядок важен: материал варианта главнее одноимённого типа материала и запланированного материала.
    Всё пишется в кавычках-ёлочках как название: так замена читается в любом падеже предложения;
    служебные поля, упомянутые как слово (`TECH_TERMS`), - без ёлочек.
    `planned` - материалы плана (`material_id`, `type`, необязательный `title`): нужны, если материал
    упомянут в репликах, но на этапе материалов не создан.
    """
    names: dict[str, str] = dict(TECH_TERMS)
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
    # Не часть слова, пути, адреса или имени файла: слева нет буквы, цифры, «/», «.», «_»; справа нет буквы,
    # цифры, «/», «_» и расширения («task_card.pdf»).
    return re.compile(_LEFT + r"(?:" + "|".join(alternatives) + r")(?![\w/])(?!\.[A-Za-z0-9])")


def _stem(text: str) -> str:
    word = re.sub(r"[«»\"'`]", "", text).strip().split(" ")[0].lower()
    return word[:5] if len(word) >= 5 else word


def _words(key: str) -> tuple[str, ...]:
    """Слова ID без числа и порядка: «commitments_book_pages», «page_book_commitment» - одно и то же."""
    return tuple(sorted(_singular(part) for part in key.split("_") if part))


# Слова, которые меняют смысл материала: «quiz_answer_cards» - ключ ответов, а не карточки викторины.
# Если лишнее слово из этого списка, ступень `extra_word` материал не подставляет.
_MEANING_WORDS = {"answer", "key", "solution", "result", "score", "scorecard", "vote", "ballot", "jury", "award",
                  "parent", "teacher", "pupil", "student", "family", "audience", "helper", "guest", "empty", "blank",
                  "instruction", "memo", "checklist"}


class IdMatcher:
    """Поиск ID в тексте по ступеням, от строгой к мягкой (QA 14.11 BUG-16 и прогон 15.11: модель пишет ID
    материала с ошибкой - «commitments_book_pages», «task_card» при «card_task»).

    1. `exact` - ID как есть.
    2. `words` - те же слова в другом числе и порядке: «task_cards» = «card_task».
    3. `extra_word` - одно слово лишнее или пропущено при двух и больше общих: «station_card» = «station_cards_set»;
       если это слово меняет смысл (`_MEANING_WORDS`: ответы, жюри, родители…), не подставляется.
    4. `typo` - в одном слове из 5 и больше букв одна буква не та или две соседние переставлены:
       «commitmnet_book_pages». «situation_cards» - не «station_cards», «route_cards» - не «vote_cards».
    5. `dictionary` - материала нет, но расходник знакомый: «colored_cardboards» - «цветной картон».

    Нестрого ищутся только материалы и расходники; роли, блоки и типы - только точно.

    На ступенях 2-4 подставляется только единственный кандидат: если подходят два ID, ничего не угадывается
    (ID остаётся, его покажет TECH-ID-IN-TEXT). Цифры должны совпадать: «block_03» - не «block_04».
    """

    def __init__(self, names: dict[str, str], fuzzy_keys: set[str] | None = None):
        """`fuzzy_keys` - ID, которые можно найти нестрого (материалы и расходники); роли и блоки - только точно:
        «parent_helper_instructions» - памятка, а не роль «parent_helpers»."""
        self.names = names
        self.compound = {key: _words(key) for key in names
                         if "_" in key and (fuzzy_keys is None or key in fuzzy_keys)}

    def _unique(self, candidates: list[str]) -> str | None:
        return candidates[0] if len(set(candidates)) == 1 else None

    @staticmethod
    def _typo(words: tuple[str, ...], other: tuple[str, ...]) -> bool:
        """Отличается ровно одно слово, оно не короче 5 букв и отличается одной правкой (`_one_edit`)."""
        if len(words) != len(other):
            return False
        mine, theirs = list(words), list(other)
        for word in words:
            if word in theirs:
                mine.remove(word)
                theirs.remove(word)
        return len(mine) == 1 and min(len(mine[0]), len(theirs[0])) >= 5 and _one_edit(mine[0], theirs[0])

    def find(self, token: str) -> tuple[str, str | None, str] | None:
        """(текст для подстановки, найденный ID или None, ступень) либо None."""
        if token in self.names:
            return self.names[token], token, "exact"
        if "_" not in token:
            return None
        words = _words(token)
        digits = re.findall(r"\d+", token)
        same_digits = {key: kw for key, kw in self.compound.items() if re.findall(r"\d+", key) == digits}
        key = self._unique([k for k, kw in same_digits.items() if kw == words])
        if key:
            return self.names[key], key, "words"
        mine = set(words)
        key = self._unique([k for k, kw in same_digits.items()
                            if len(mine & set(kw)) >= 2 and len(mine ^ set(kw)) == 1
                            and not (mine ^ set(kw)) & _MEANING_WORDS])
        if key:
            return self.names[key], key, "extra_word"
        key = self._unique([k for k, kw in same_digits.items() if self._typo(words, kw)])
        if key:
            return self.names[key], key, "typo"
        for candidate in (token, "_".join(_singular(part) for part in token.split("_"))):
            if candidate in _THING_RU:
                return _THING_RU[candidate], None, "dictionary"
        return None


def humanize_text(text: str, names: dict[str, str], matched: dict[str, str] | None = None,
                  fuzzy_keys: set[str] | None = None) -> tuple[str, list[str]]:
    """Заменяет известные ID в одном тексте. Возвращает новый текст и список заменённых ID.

    ID ищется по ступеням `IdMatcher`: кроме точного совпадения - те же слова в другом числе и порядке,
    одно лишнее слово, опечатка, знакомый расходник. Нестрогие замены записываются в `matched`
    («task_card» -> «card_task (words)»), чтобы их было видно в трассе.
    """
    if not text or not names:
        return text, []
    pattern = _token_pattern(names)
    matcher = IdMatcher(names, fuzzy_keys)
    urls = [m.span() for m in _URL.finditer(text)]
    replaced: list[str] = []
    out: list[str] = []
    pos = 0
    for m in pattern.finditer(text):
        token = m.group(0)
        found = matcher.find(token)
        if not found or any(a <= m.start() < b for a, b in urls):
            continue
        title, key, method = found
        if method != "exact" and matched is not None:
            matched[token] = f"{key} ({method})" if key else f"{title} ({method})"
        start, end = m.start(), m.end()
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
        before, title = _term_form(key, title, before)
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
    fuzzy = ({m.get("material_id") for m in variant.get("materials") or []} | {p.get("material_id") for p in planned or []}
             | set(dependencies or {}) | set(MATERIAL_TYPE_TITLES) | TECH_TERMS_FUZZY)
    changes: list[dict[str, Any]] = []

    def record(where: str, ids: list[str], matched: dict[str, str]) -> None:
        change: dict[str, Any] = {"field": where, "ids": ids}
        if matched:
            change["matched"] = matched  # нестрогие замены: что было и на что заменено
        changes.append(change)

    def fix(container: dict[str, Any], key: str, where: str) -> None:
        value = container.get(key)
        if isinstance(value, str):
            matched: dict[str, str] = {}
            new, ids = humanize_text(value, names, matched, fuzzy)
            if ids:
                container[key] = new
                record(where, ids, matched)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, str):
                    matched = {}
                    new, ids = humanize_text(item, names, matched, fuzzy)
                    if ids:
                        value[index] = new
                        record(f"{where}[{index}]", ids, matched)

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


# Ремарка о переходе между частями сценария: «(Переходит к подготовке следующего блока.)» - «блок» и «этап» - наши
# внутренние слова, педагогу эта ремарка не нужна (тестовый сценарий аналитика 20.11).
_STAGE_DIRECTION = re.compile(r"\s*\(\s*(?:переходит|переход|переходим)\s+к\s+(?:подготовке\s+)?следующ\w+\s+(?:блок|этап)\w*\s*\.?\s*\)", re.I)


def _drop_meta(text: str) -> tuple[str, list[str]]:
    removed: list[str] = []
    kept: list[str] = []
    text = _FIELD_LABEL.sub(lambda m: _relabel(m, removed), text)
    for match in _STAGE_DIRECTION.finditer(text):
        removed.append(match.group(0).strip())
    text = _STAGE_DIRECTION.sub("", text)
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
_DATE_LINE = re.compile(
    r"^(?P<label>[ \t]*(?:дата|число)?[ \t]*:?[ \t]*)(?:«?\d{1,2}»?[ \t]+" + _MONTHS + r"|\d{1,2}\.\d{1,2}\.|(?:«_+»[ \t]*)?_{3,})"
    r"[ \t]*(?:19|20)\d{2}[ \t]*(?:г\.?|года?)?[ \t]*(?P<close>[\"»”]?)[ \t]*$",
    re.I | re.M,
)
DATE_BLANK = "«___» __________ 20__ г."
# Год в подписи шаблона в кавычках: «внизу подпись: "Класс 9-а, 2023 год"» (шаблон стены памяти, второй финальный
# прогон 15.11). Модель ставит прошлый год; это место для года, а не факт. Только подпись класса, школы или выпуска:
# «надпись: "Победа, 1945 год"» на плакате - исторический факт, его не трогаем.
_CAPTION_YEAR = re.compile(
    r"(?P<pre>(?:подпис|надпис)\w*[^\"«\n]{0,30}?[\"«](?=[^\"»\n]*(?:класс|школ|выпуск))[^\"»\n]{0,80}?)"
    r"(?P<year>(?:19|20)\d{2})(?P<post>[ \t]*(?:год|г\.)[ \t]*[\"»])",
    re.I,
)
YEAR_BLANK = "20__"


def blank_template_dates(variant: dict[str, Any]) -> list[dict[str, Any]]:
    """Заменяет дату-строку в материалах (подпись письма, бланк) на пустое место для даты, год в подписи
    шаблона («Класс 9-а, 2023 год») - на «20__».

    Возвращает:
        Список изменений для трассы: материал и заменённые строки.
    """
    changes: list[dict[str, Any]] = []
    for material in variant.get("materials") or []:
        content = material.get("content")
        if not isinstance(content, str):
            continue
        found = [m.group(0).strip() for m in _DATE_LINE.finditer(content)]
        found += [m.group("year") + m.group("post").rstrip("\"»").rstrip() for m in _CAPTION_YEAR.finditer(content)]
        if found:
            content = _DATE_LINE.sub(lambda m: m.group("label") + DATE_BLANK + m.group("close"), content)
            material["content"] = _CAPTION_YEAR.sub(lambda m: m.group("pre") + YEAR_BLANK + m.group("post"), content)
            changes.append({"field": f"materials.{material.get('material_id')}.content", "dates": found})
    return changes