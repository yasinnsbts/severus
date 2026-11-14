"""Время внутри этапа: явные противоречия между текстом блока и его длительностью.

Общую сетку блоков считает программа (`generation/timing.py`), а внутри блока модель сама пишет
«у вас 10 минут» или «каждая команда выступает по 3 минуты». Здесь ловятся только явные случаи,
которые можно посчитать без понимания смысла:

1. Выступления по очереди: «каждая группа / команда / пара ... по N минут», «N минут на группу»,
   «группы по очереди ... по N минут», «время выступления - N минут», «спикеру даётся N минут»,
   «по минуте на каждую группу» рядом с выступлением, презентацией,
   защитой; число выступающих известно из деления класса.
   Если число выступающих × N больше длительности блока - противоречие.
2. Отрезки работы «у вас (есть / будет) N минут», «даётся N минут», «время на ... - N минут»:
   сумма разных отрезков больше длительности блока и следующего блока вместе.
   Запас на следующий блок нужен потому, что вводный блок часто объявляет время следующего
   («На выполнение у вас будет 15 минут» в 5-минутном блоке перед 15-минутной работой).

Параллельная работа групп («15 минут, каждая группа работает над своим») не считается выступлениями:
нужен глагол выступления в той же фразе. Если выступают не все («по желанию», «2-3 группы»),
проверка молчит. Всё неоднозначное остаётся эксперту: результат - только предупреждение.
"""

from __future__ import annotations

import re
from typing import Any

from ..generation.grouping import plural

_WORD_NUMBERS = {
    "одну": 1, "одна": 1, "одной": 1, "полторы": 1.5, "две": 2, "два": 2, "двух": 2, "три": 3, "трёх": 3, "трех": 3,
    "четыре": 4, "четырёх": 4, "пять": 5, "пяти": 5, "шесть": 6, "семь": 7, "восемь": 8, "десять": 10,
    "пятнадцать": 15, "двадцать": 20,
}
_NUM = r"(\d+(?:[.,]5)?|" + "|".join(sorted(_WORD_NUMBERS, key=len, reverse=True)) + r")"
_RANGE = _NUM + r"(?:\s*[-\u2013\u2014]\s*" + _NUM + r")?"
_MIN = r"\s*минут\w*"

_PRESENT = re.compile(r"выступ|представ|презент|защищ|защит|рассказ|расскаж|показыва|покаж|делят|поделит|отчита", re.I)
_UNIT_GROUP = re.compile(r"кажд\w*\s+(?:\w+\s+){0,2}?(команд|групп|станци)|(команд|групп)\w*[\s,]+(?:\w+[\s,]+){0,3}?по\s+" + _NUM + _MIN
                         + r"|(?:команд|групп)\w*\s+(?:\w+\s+)?по\s+очереди|по\s+очереди\s+(?:\w+\s+)?(?:команд|групп)"
                         + r"|" + _NUM + _MIN + r"\s+на\s+(?:команд|групп)"
                         + r"|спикер|выступающ|представител\w*\s+(?:от\s+)?(?:кажд\w*\s+)?(?:команд|групп)", re.I)
_UNIT_PAIR = re.compile(r"кажд\w*\s+(?:\w+\s+){0,2}?пар|" + _NUM + _MIN + r"\s+на\s+пар[уы]\b", re.I)
# Время одного выступления: «3 минуты на группу», «время выступления - 4 минуты». «Время на выступления - 8 минут»
# (с «на» и множественным числом) - общий отрезок, его считает правило 2.
_PER_UNIT = re.compile(r"(?:по\s+|кажд\w*\s+(?:\w+\s+){0,6}?|на\s+кажд\w*\s+\w+\s+)" + _RANGE + _MIN + r"|" + _RANGE + _MIN + r"\s+на\s+(?:кажд\w*|выступлени|презентаци|защит)"
                      + r"|" + _RANGE + _MIN + r"\s+на\s+(?:групп[уы]?|команд[уы]?|пар[уы]|выступающ\w*|спикер\w*)\b"
                      + r"|на\s+(?:выступлени|презентаци|защит|представлени)\w*\s+(?:\w+\s+){0,3}?" + _RANGE + _MIN
                      + r"|время\s+(?:одного\s+|каждого\s+)?(?:выступления|презентации|защиты|рассказа)\s*[-\u2013\u2014:]?\s*(?:до\s+|не\s+более\s+)?"
                      + _RANGE + _MIN
                      # Время, которое дают спикеру: «Спикеру даётся одна минута», «у выступающего две минуты».
                      + r"|(?:спикер|выступающ|докладчик|представител)\w*\s+(?:\w+\s+){0,2}?(?:даётся|дается|отводится|есть|будет)?\s*"
                      + r"(?:не\s+более\s+|до\s+|максимум\s+)?\b" + _RANGE + r"\s+минут\w*", re.I)
_NOT_ALL = re.compile(r"по желанию|желающ|не все|несколько (?:групп|команд|пар)|\d\s*[-\u2013]\s*\d\s+(?:групп|команд|пар)|одна-две|две-три", re.I)
_INTERVAL = re.compile(
    r"(?:у\s+вас|вам)\s+(?:есть\s+|будет\s+|даётся\s+|дается\s+|всего\s+|примерно\s+|ровно\s+){0,2}" + _RANGE + _MIN
    + r"|(?:даётся|дается|отводится|отведено)\s+(?:\w+\s+){0,2}?" + _RANGE + _MIN
    + r"|время\s+на\s+[^.!?\n]{1,40}?[-\u2013\u2014:]\s*" + _RANGE + _MIN,
    re.I,
)
_SENTENCE = re.compile(r"[^.!?\n]+[.!?\n]?")
# Переход команд между станциями: «перемещаетесь на следующую станцию», «по кругу», «маршрут».
_ROTATION = re.compile(r"(?:перемещ|переход|перейд|меня)\w*\s+(?:\w+\s+){0,3}?(?:на\s+)?следующ\w*\s+станци|по\s+кругу|по\s+маршрут|станци\w*\s+по\s+очеред", re.I)
_STATION_TIME = re.compile(r"(?:на\s+)?кажд\w*\s+станци\w*\s+(?:\w+\s+){0,4}?" + _RANGE + _MIN + r"|" + _RANGE + _MIN + r"\s+на\s+(?:кажд\w*\s+)?станци", re.I)
_STATION_ORDINAL = re.compile(r"\b(перв|втор|трет|четв[её]рт|пят|шест|седьм|восьм)(?:ая|ой|ую|ья|ей|ью)\s+станци", re.I)
_STATION_CARDINAL = re.compile(r"\b(\d+|две|двух|три|тр[её]х|четыре|четыр[её]х|пять|пяти|шесть|шести|семь|семи)\s+(?:\w+\s+)?станци", re.I)
_CARDINALS = {"две": 2, "двух": 2, "три": 3, "трех": 3, "трёх": 3, "четыре": 4, "четырех": 4, "четырёх": 4,
              "пять": 5, "пяти": 5, "шесть": 6, "шести": 6, "семь": 7, "семи": 7}
# Выступления групп в следующем блоке: «Каждая группа коротко поделится своими находками», «выступление каждой группы»,
# «Дети представляют результаты своего маршрута классу», «Первая команда, расскажите».
_NEXT_PRESENTS = re.compile(
    r"кажд\w*\s+(?:\w+\s+){0,2}?(?:групп|команд|отряд|экспедици)\w*\s+(?:\w+\s+){0,3}?(?:представ|выступ|расскаж|покаж|защит|подел)"
    r"|(?:выступлени|презентаци|защит)\w*\s+(?:\w+\s+)?кажд\w*\s+(?:групп|команд)"
    r"|(?:групп|команд|спикер)\w*\s+(?:\w+\s+){0,2}?(?:представляют|выступают|рассказывают|защищают)"
    r"|(?:дети|ученики)\s+(?:\w+\s+)?представляют\s+(?:результат|итог|свои\s+(?:находк|работ|маршрут|проект))"
    r"|(?:перв|втор)\w*\s+(?:групп|команд)\w*[,!]?\s+(?:\w+\s+){0,2}?(?:представ|выступ|расскаж|покаж|начина)",
    re.I,
)


def _presented_next(next_text: str) -> bool:
    """В следующем блоке выступают группы с тем, что сделали раньше, а не с новой работой этого блока.

    «Каждая группа коротко поделится своими находками» - да. «Вам даётся 5 минут на план. Затем каждая группа
    представит предложение» - нет: перед выступлением своя работа, выступают с ней.
    """
    match = _NEXT_PRESENTS.search(next_text)
    return bool(match) and not _INTERVAL.search(next_text[:match.start()])


def _value(token: str | None) -> float | None:
    if not token:
        return None
    token = token.lower()
    if token in _WORD_NUMBERS:
        return float(_WORD_NUMBERS[token])
    try:
        return float(token.replace(",", "."))
    except ValueError:
        return None


def _first_number(match: re.Match[str]) -> float | None:
    """Первое число совпадения; у диапазона «3-4 минуты» берётся меньшее."""
    for group in match.groups():
        value = _value(group)
        if value is not None:
            return value
    return None


def _station_count(text: str) -> int:
    """Число станций по тексту: «квест из пяти станций» - 5; «Первая станция… Четвёртая станция… И последняя станция» - 5."""
    for match in _STATION_CARDINAL.finditer(text):
        token = match.group(1).lower()
        value = int(token) if token.isdigit() else _CARDINALS.get(token, 0)
        if value > 1:
            return value
    ordinals = {m.group(1).lower().replace("ё", "е") for m in _STATION_ORDINAL.finditer(text)}
    if len(ordinals) < 2:
        return 0
    return len(ordinals) + (1 if re.search(r"последн\w*\s+станци", text, re.I) else 0)


def _intervals(text: str, duration: int, next_duration: int) -> list[str]:
    """Правило 2: сумма отрезков «у вас N минут» больше длительности блока и следующего блока."""
    values: list[float] = []
    for match in _INTERVAL.finditer(text):
        value = _first_number(match)
        if value and (not values or values[-1] != value):
            values.append(value)
    total = sum(values)
    if values and total > duration + next_duration:
        parts = " + ".join(_fmt(x) for x in values)
        limit = f"{duration} мин блока" + (f" и {next_duration} мин следующего" if next_duration else "")
        return [f"отрезки работы: {parts} = {_fmt(total)} мин, больше чем {limit}"]
    return []


def _fmt(x: float) -> str:
    return str(int(x)) if x == int(x) else str(x).replace(".", ",")


def inner_timing_problems(block: dict[str, Any], *, groups_count: int, pairs_count: int,
                          next_duration: int = 0, next_title: str = "", next_text: str = "") -> list[str]:
    """Явные противоречия времени внутри блока. Пустой список - противоречий не найдено.

    Параметры:
        block: блок сценария (`duration_minutes`, `teacher_script`, `pupil_actions`).
        groups_count: число групп или команд в делении класса (1, если деления нет).
        pairs_count: число пар, если класс работает парами (0, если нет).
        next_duration: длительность следующего блока (0 для последнего).
        next_title: название следующего блока: если это выступления, они не считаются частью текущего.
        next_text: реплики и действия учеников следующего блока: если в нём выступают группы
            («каждая группа поделится», «представляют результаты»), выступления тоже не считаются частью текущего,
            даже когда название об этом не говорит («Встречи с прошлым: что увидели наши исследователи?»).
    """
    duration = block["duration_minutes"]
    text = block.get("teacher_script", "") + "\n" + "\n".join(block.get("pupil_actions") or [])
    # «по минуте на каждую группу» - одна минута, хотя числа нет.
    text = re.sub(r"\bпо\s+минуте\b", "по 1 минуте", text, flags=re.I)
    problems: list[str] = []

    # 0. Станции по кругу: команды работают одновременно, но каждая проходит все станции подряд, поэтому круг
    # занимает «число станций × минуты на станцию» (замечание QA 14.11, BUG-18: сообщение говорило о выступлениях групп).
    # Если станции идут в следующих этапах («Станция первая: …»), этот этап только объявляет маршрут.
    if _ROTATION.search(text) and not re.search(r"станци", next_title, re.I):
        for match in _STATION_TIME.finditer(text):
            minutes = _first_number(match)
            stations = _station_count(text) or (groups_count if groups_count > 1 else 0)
            if minutes and stations > 1 and stations * minutes > duration:
                problems.append(f"станции по кругу: каждая команда проходит {stations} {plural(stations, 'станцию', 'станции', 'станций')} "
                                f"× {_fmt(minutes)} мин = {_fmt(stations * minutes)} мин, "
                                f"а на блок {duration} мин")
            break
        if problems or _STATION_TIME.search(text):
            return problems + _intervals(text, duration, next_duration)

    # 1. Выступления по очереди. Кто выступает и сколько минут, модель часто пишет в соседних фразах
    # («Каждая команда представит свой раздел. На выступление у вас 2 минуты»), поэтому смотрим пару фраз.
    sentences = [s for s in _SENTENCE.findall(text) if s.strip()]
    for index, current in enumerate(sentences):
        sentence = (sentences[index - 1] if index else "") + " " + current
        if not _PER_UNIT.search(current) or not _PRESENT.search(sentence) or _NOT_ALL.search(sentence):
            continue
        if re.search(r"на\s+кажд\w*\s+иде", sentence, re.I):
            continue
        per = _PER_UNIT.search(current)
        minutes = _first_number(per)
        if not minutes:
            continue
        if _UNIT_PAIR.search(sentence) and pairs_count > 1:
            units, label = pairs_count, "пар"
        elif _UNIT_GROUP.search(sentence) and groups_count > 1:
            units, label = groups_count, "групп"
        else:
            continue
        total = units * minutes
        if total > duration:
            problems.append(f"выступления: {units} {label} × {_fmt(minutes)} мин = {_fmt(total)} мин, а на блок {duration} мин")
            break

    # 3. Работа, а потом выступления всех групп без регламента: «даётся 10 минут. Затем каждая команда
    # представит коллаж» в 12-минутном этапе с 4 командами - на выступление меньше минуты на команду.
    # «Время на выступления - 8 минут» - это само время выступлений, а не работа перед ними.
    first_interval = _INTERVAL.search(text)
    if first_interval and re.search(r"выступлен|презентац|защит|представлен", first_interval.group(0), re.I):
        first_interval = None
    if (not problems and groups_count > 1 and first_interval and not _PER_UNIT.search(text)
            and not re.search(r"представлен|презентац|выступлен|защит", next_title, re.I)
            and not _presented_next(next_text)):
        work = _first_number(first_interval) or 0
        after = text[first_interval.end():]
        presents = re.search(r"кажд\w*\s+(?:\w+\s+){0,2}?(?:команд|групп)\w*\s+(?:\w+\s+){0,3}?(?:представ|выступ|расскаж|покаж|защит)", after, re.I)
        if presents and not _NOT_ALL.search(after[:presents.end() + 80]):
            left = duration - work
            if left < groups_count:
                problems.append(f"после {_fmt(work)} мин работы на выступления {groups_count} групп остаётся {_fmt(max(left, 0))} мин")

    # 2. Сумма отрезков работы.
    return problems + _intervals(text, duration, next_duration)


def grouping_counts(variant: dict[str, Any]) -> tuple[int, int]:
    """Число групп и пар для блока по делению класса варианта."""
    grouping = variant.get("pupil_grouping") or {}
    sizes = grouping.get("group_sizes") or []
    mode = grouping.get("mode")
    total = grouping.get("total_pupils") or sum(sizes) or 0
    groups = len(sizes) if mode in ("small_groups", "mixed") and len(sizes) > 1 else 1
    pairs = total // 2 if mode == "pairs" or (sizes and max(sizes) == 2) else 0
    # Деление может быть указано для других блоков, а выступают те же группы: число групп то же.
    return groups, pairs