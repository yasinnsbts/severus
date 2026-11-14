"""Нужный объём реплик педагога в блоке: зависит от детализации, длительности блока и возраста класса."""

from __future__ import annotations

from typing import Any


def script_min_chars(gen_cfg: dict[str, Any], detail: str, minutes: int, age_group: str | None = None) -> int:
    """Минимальный объём `teacher_script` для блока.

    Объём = базовая часть (вступление, инструкция, переход) + часть на каждую минуту блока.
    Короткий переход на 2 минуты не обязан быть таким же длинным, как работа в командах на 20 минут.
    Для младших классов объём умножается на `age_factor` из конфига: с ними говорят короче.

    Параметры:
        gen_cfg: `config/generation.json`; detail: `brief` | `standard` | `detailed`; minutes: длительность блока;
        age_group: возрастная группа класса (`1-4`, `5-8`, `9-11`), если известна.

    Возвращает:
        Число символов.
    """
    cfg = gen_cfg["script_length"]
    factor = float((cfg.get("age_factor") or {}).get(age_group or "", 1.0))
    return int((cfg["base_chars"][detail] + cfg["chars_per_minute"][detail] * max(int(minutes), 1)) * factor)


def script_target_chars(gen_cfg: dict[str, Any], detail: str, minutes: int, age_group: str | None = None) -> int:
    """Объём, к которому модель просим стремиться: в полтора раза больше минимума.

    Модели обычно пишут впритык к названному числу, поэтому в промпте называем и минимум, и желаемый объём,
    а предупреждение `SCRIPT-SHORT` даём только ниже минимума.
    """
    return int(round(script_min_chars(gen_cfg, detail, minutes, age_group) * 1.5, -1))


def script_size_text(gen_cfg: dict[str, Any], detail: str, minutes: int, age_group: str | None = None) -> str:
    """Например «от 600, лучше около 900 символов»."""
    return (f"от {script_min_chars(gen_cfg, detail, minutes, age_group)}, "
            f"лучше около {script_target_chars(gen_cfg, detail, minutes, age_group)} символов")


def script_length_rule(gen_cfg: dict[str, Any], detail: str, age_group: str | None = None) -> str:
    """Правило объёма словами с примерами для промпта: «5 мин - от 500, лучше около 750 символов; …»."""
    examples = "; ".join(f"{m} мин - {script_size_text(gen_cfg, detail, m, age_group)}" for m in (3, 5, 10, 20))
    return f"по длительности блока: {examples}"