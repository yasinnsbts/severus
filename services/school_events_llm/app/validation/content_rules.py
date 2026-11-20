"""Содержательные проверки по тестовому сценарию аналитика 20.11 («Праздник Весны и Труда», 7 класс, 60 минут).

- `FOOD-TASK`: задание с настоящей едой - готовка, ингредиенты, нарезанные овощи, дегустация. Станция «Повара»:
  «Подготовить салат из готовых нарезанных овощей», в памятке - «места для хранения… салатов». Условий для еды
  (гигиена, аллергии, пищевые ограничения) в запросе нет, поэтому промпт просит муляжи или рецепт на карточке,
  а проверка показывает эксперту, если модель всё же дала еду.
- `PROPS-MISSING`: педагог раздаёт реквизит, которого нет ни в материалах, ни в памятке: «Достаёт небольшие
  сувениры или благодарственные открытки… Раздаёт сувениры».

Обе только предупреждают. Готовку ищем в действиях учеников, а не в рассказе о традициях («готовят угощения из
свежих продуктов» - о людях, не задание); раздачу - по глаголу раздачи в той же фразе, и не там, где дети сами
делают сувениры («сложим готовые сувениры, чтобы вручить друг другу»).
"""

from __future__ import annotations

import re
from typing import Any

_COOK = re.compile(r"(?:приготов\w+|готов(?:ят|ит|ить|им|ьте)|нарез\w+|смешива\w+)\s+(?:\w+\s+){0,3}?"
                   r"(?:блюд\w*|салат\w*|бутерброд\w*|канапе|угощени\w*|напит\w*|десерт\w*|пирог\w*|печень\w*)", re.I)
# Ингредиенты сами по себе - не задание («Карточки традиционной кухни: Ингредиенты: мука, ягоды»), только
# «приготовить … из предложенных ингредиентов».
_FOOD = re.compile(r"(?:приготов\w+|сдела\w+)\s+(?:\w+\s+){0,4}?из\s+(?:\w+\s+){0,2}?(?:ингредиент|продукт|овощ|фрукт)\w*"
                   r"|нарезанн\w+\s+(?:\w+\s+)?(?:овощ|фрукт)\w*|(?:овощ|фрукт)\w*\s+нарезанн\w*|дегустац\w*"
                   r"|попробу\w+\s+(?:\w+\s+)?(?:на\s+вкус|блюд\w*|салат\w*|угощени\w*)", re.I)
_GIVE = re.compile(r"разда[её]|раздаю|раздад|вруча|вручит|дарит|дарят|дарим|доста[её]т|получа|получит|выда[её]т|выдаю|награжда", re.I)
_PROPS = re.compile(r"сувенир\w*|открытк\w*|грамот\w*|медал(?:ь|и|ей|ям|ями|ях)\b|\bприз(?:ы|ов|ам|ами|ах)?\b|наклейк\w*"
                    r"|значк\w*|значок|диплом\w*|сертификат\w*", re.I)
# Название реквизита для сообщения: «значка» - «значки».
_PROP_NAMES = (("сувенир", "сувениры"), ("открытк", "открытки"), ("грамот", "грамоты"), ("медал", "медали"), ("приз", "призы"),
               ("наклейк", "наклейки"), ("значк", "значки"), ("значок", "значки"), ("диплом", "дипломы"), ("сертификат", "сертификаты"))
_SELF_MADE = re.compile(r"готов\w+\s+(?:\w+\s+)?(?:сувенир|открытк|значк)|сделанн|изготов|украш|своими\s+руками|друг\s+другу", re.I)
_SENTENCE = re.compile(r"[^.!?\n]+[.!?\n]?")


def food_tasks(actions: list[str], texts: list[str]) -> list[str]:
    """Фразы с настоящей едой: готовка в действиях учеников, ингредиенты и дегустация в любом тексте этапа или материала."""
    found = [m.group(0) for action in actions for m in [_COOK.search(action)] if m]
    found += [m.group(0) for text in texts for m in [_FOOD.search(text)] if m]
    return list(dict.fromkeys(f.strip() for f in found))


def missing_props(script_parts: list[str], covered: str) -> list[str]:
    """Реквизит, который педагог раздаёт в этапе, а в материалах и памятке его нет."""
    covered = covered.lower()
    found: list[str] = []
    for part in script_parts:
        for sentence in _SENTENCE.findall(part):
            if not _GIVE.search(sentence) or _SELF_MADE.search(sentence):
                continue
            for match in _PROPS.finditer(sentence):
                word = match.group(0).lower()
                name = next(plural for stem, plural in _PROP_NAMES if word.startswith(stem))
                if word[:5] not in covered and name not in found:
                    found.append(name)
    return found


def covered_text(variant: dict[str, Any], dependency_labels: dict[str, str]) -> str:
    """Всё, что педагог готовит заранее: материалы, их расходники и памятка."""
    parts: list[str] = []
    for material in variant.get("materials") or []:
        parts += [str(material.get(key) or "") for key in ("title", "content", "teacher_notes")]
        parts += [dependency_labels.get(dep, dep) for dep in material.get("dependencies") or []]
    parts += [str(item) for item in variant.get("teacher_instructions") or []]
    return " ".join(parts)