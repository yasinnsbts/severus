"""Детерминированное деление учащихся на группы (ТЗ 12.3)."""

from __future__ import annotations


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