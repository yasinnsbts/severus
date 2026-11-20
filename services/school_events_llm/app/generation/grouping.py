"""Детерминированное деление учащихся на группы (ТЗ 12.3)."""

from __future__ import annotations

import math
import re


def split_even(total: int, groups: int) -> list[int]:
    """27 на 5 → [6, 6, 5, 5, 5]: размеры отличаются не больше чем на 1, крупные первыми."""
    groups = max(1, min(groups, total))
    base, rem = divmod(total, groups)
    return [base + 1] * rem + [base] * (groups - rem)


def pairs(total: int) -> list[int]:
    """Пары; при нечётном числе одна тройка: 27 → 12×2 + 1×3."""
    if total < 2:
        return [total]
    count = total // 2
    sizes = [2] * count
    if total % 2:
        sizes[-1] = 3
    return sizes


def compute_grouping(mode: str, total: int, groups_count: int, group_work: bool) -> tuple[str, list[int], list[str]]:
    """Возвращает (режим, размеры, предупреждения). При group_work=false малые группы заменяются."""
    notes: list[str] = []
    if mode in ("small_groups", "mixed") and not group_work:
        notes.append("Обязательные малые группы запрещены: режим заменён на whole_class")
        mode = "whole_class"
    if mode == "whole_class":
        return mode, [total], notes
    if mode == "pairs":
        return mode, pairs(total), notes
    if groups_count < 2:
        groups_count = max(2, round(total / 5))
        notes.append(f"Число групп не указано или меньше 2 - выбрано {groups_count}")
    return mode, split_even(total, groups_count), notes


def plural(n: int, one: str, few: str, many: str) -> str:
    """Форма слова после числа: 1 группа, 2 группы, 5 групп, 21 группа, 11 групп."""
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def describe(sizes: list[int]) -> str:
    """Преобразует рассчитанные размеры групп в понятное текстовое описание.

    Параметры:
        `sizes`.

    Возвращает:
        str.
    """
    if len(sizes) == 1:
        return f"весь класс ({sizes[0]})"
    if all(s == 2 for s in sizes[:-1]) and sizes[-1] in (2, 3) and len(sizes) > 2:
        tail = " и одна тройка" if sizes[-1] == 3 else ""
        pairs = len(sizes) - (1 if sizes[-1] == 3 else 0)
        return f"{pairs} {plural(pairs, 'пара', 'пары', 'пар')}{tail}"
    return f"{len(sizes)} {plural(len(sizes), 'группа', 'группы', 'групп')}: " + ", ".join(str(s) for s in sizes)


# Какие блоки получают строку про выступления: по названию и цели блока плана.
_PRESENT = re.compile(r"выступ|презент|представ|защит|инсцен|ярмарк|показ", re.I)
_GROUP_WORK = re.compile(r"групп|команд|\bпар(?:а|ы|ах|ами|у)?\b|в парах|станци|совместн|мастерск", re.I)
_PREPARE = re.compile(r"подготов|репетиц|оформлен", re.I)
_ORGANIZE = re.compile(r"формирован|организац|делени|распредел|выбор|знакомств|приветств|вступлен|введени|объяснени|рефлекс|итог|заверш"
                       r"|(?:создани|сбор)\w*\s+(?:команд|групп)", re.I)


def _presents(block: dict) -> bool:
    """Блок выступлений - по названию; по цели - только если название не про подготовку: у «Подготовительный этап:
    репетиции и оформление» цель «реализация идеи выступления», а выступают позже (прогон 15.11)."""
    title, purpose = str(block.get("title") or ""), str(block.get("purpose") or "")
    return bool(_PRESENT.search(title)) or (bool(_PRESENT.search(purpose)) and not _PREPARE.search(title))


# Блок, где группы по кругу проходят несколько станций: «Ярмарка профессий (работа на станциях)», «Квест по станциям».
# Один блок-станция («Станция Ремёсел») - не круг: там своя строка про выступления.
_STATION_ROUND = re.compile(r"на\s+станциях|по\s+станциям|станций|станции\s+по\s+кругу|смен\w*\s+станци|ротаци", re.I)


def station_budget(mode: str, sizes: list[int], block: dict, minutes: int) -> str:
    """Строка для блока станций по кругу: станций столько же, сколько групп, и минуты на станцию.

    Тестовый сценарий аналитика 20.11: 4 группы на 3 станции по 6-7 минут в блоке на 20 минут - одна группа ждёт
    целую смену, и круг не помещается. Число групп программа знает до этапа блоков, поэтому числа даёт она.
    """
    if mode == "whole_class" or len(sizes) < 2 or minutes < 4:
        return ""
    title = str(block.get("title") or "")
    # Объяснение правил и знакомство со станциями («Объяснение условий квеста», «Представление станций») - не сам круг.
    if _ORGANIZE.search(title) or re.search(r"представлени\w*\s+станци", title, re.I):
        return ""
    if not _STATION_ROUND.search(f"{title} {block.get('purpose') or ''}"):
        return ""
    units = len(sizes)
    per = math.floor((minutes - 1) / units * 2) / 2
    per_txt = str(int(per)) if per == int(per) else str(per).replace(".", ",")
    who = f"{units} {plural(units, 'пара', 'пары', 'пар') if mode == 'pairs' else plural(units, 'группа', 'группы', 'групп')}"
    if per < 2:
        teams = max(2, (minutes - 1) // 3)
        return (f"станции по кругу: {who} - станций столько же, но на каждую выйдет меньше 2 мин; "
                f"лучше {teams} {plural(teams, 'станция', 'станции', 'станций')} и столько же групп")
    return f"станции по кругу: {who} - {units} {plural(units, 'станция', 'станции', 'станций')}, не больше {per_txt} мин на станцию с переходом"


def presentation_budget(mode: str, sizes: list[int], block: dict, minutes: int, grouping_block_ids: list[str],
                        later_blocks: list[dict] | None = None) -> str:
    """Минуты на выступление каждой группы или пары для строки блока в промпте; не тот блок - пустая строка.

    Четыре финальных прогона и два прогона с правкой промптов 15.11: настоящие INNER-TIMING - все «12 пар по
    3 минуты в блоке на 20 минут», «6 минут работы и выступления 4 групп в 8 минутах». Общее правило «число
    выступающих × минуты не больше длительности» модель сама не считает, поэтому числа даёт программа.
    Только числа, без готовых решений («по желанию»): образец с одним значением модель копирует.

    Строку получают блоки выступлений («Представление проектов») и блоки работы групп или пар, после которых
    нет блока выступлений (`later_blocks` - все следующие блоки: «Исследование» → «Подготовка доклада» →
    «Представление докладов»). Не получают: организационные блоки (формирование команд, приветствие, итоги),
    блоки короче 4 минут и работа групп перед блоком выступлений - чтобы модель не добавляла туда выступления.
    """
    if mode == "whole_class" or len(sizes) < 2 or minutes < 4:
        return ""
    title = str(block.get("title") or "")
    if _ORGANIZE.search(title):
        return ""
    presents_later = any(_presents(later) for later in later_blocks or [])
    group_work = block.get("block_id") in grouping_block_ids or bool(_GROUP_WORK.search(f"{title} {block.get('purpose') or ''}"))
    if not _presents(block) and not (group_work and not presents_later):
        return ""
    units = len(sizes)
    who = f"всех {units} {plural(units, 'пары', 'пар', 'пар') if mode == 'pairs' else plural(units, 'группы', 'групп', 'групп')}"
    per = math.floor((minutes - 1) / units * 2) / 2
    # Меньше 2 минут на каждую - это одна-две фразы. Если нужен рассказ, класс делится на меньшее число команд
    # по 2 минуты (Андрей, 15.11: «если большое - на меньшее число команд, если достаточно одной-двух фраз -
    # можно коротко»). Модель выбирает по смыслу блока; прогон с минутами в промпте: на «меньше 1 мин - не успеют»
    # она всё равно слушала все 12-17 пар.
    # Объединять есть смысл, только если команд выходит хотя бы вдвое меньше (6 групп - в 3, а не 4 - в 3).
    teams = min((minutes - 1) // 2, units // 2)
    merge = (f"; для рассказа объедините {'пары' if mode == 'pairs' else 'группы'} в {teams} "
             f"{plural(teams, 'команду', 'команды', 'команд')} по 2 мин") if teams >= 2 and units >= 6 else ""
    if per < 1:
        seconds = math.floor((minutes - 1) * 60 / units / 5) * 5
        if seconds >= 30:
            return f"выступления {who}: около {seconds} сек на каждую - хватит на одну-две фразы{merge}"
        return f"выступления {who}: меньше 30 сек на каждую - не успеть даже по фразе{merge}"
    per_txt = str(int(per)) if per == int(per) else str(per).replace(".", ",")
    if per < 2 and merge:
        return f"выступления {who}: не больше {per_txt} мин на каждую - хватит на одну-две фразы{merge}"
    return f"выступления {who}: не больше {per_txt} мин на каждую; работа до них тоже входит в {minutes} мин"