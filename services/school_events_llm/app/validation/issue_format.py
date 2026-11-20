"""Замечание проверки в формате ТЗ 16.2: `issue_id`, `category`, `repairable`, `suggested_action`.

QA 15.11, BUG-06: в `quality_report.issues` были только `code`, `severity`, `location`, `message`. Поля ТЗ
добавляются, прежние остаются (фронтенд читает `code`, `severity`, `message`). Категория - по коду замечания,
подсказка - по коду, где её можно дать без модели; где нечего подсказать - `null`. Поле `stage` не выводится, как и раньше.
"""

from __future__ import annotations

from typing import Any

# Категория по началу кода: первое подходящее правило.
_CATEGORIES = (
    (("RESOURCE-", "PRINT-UNAVAILABLE", "SLIDES-NO-PROJECTOR", "DEP-UNKNOWN"), "resources"),
    (("TIME-GRID", "INNER-TIMING"), "timing"),
    (("FACT-", "CULTURE-UNSOURCED", "DOC-UNSOURCED", "EVENT-MIXUP", "SOURCE-UNUSED"), "facts"),
    (("VOTING-", "BALLOT-", "AWARD-INSTRUCTION"), "voting"),
    (("PARENT", "JURY-"), "parents"),
    (("TEACHER-MISSING", "TEACHERS-OVER", "PUPILS-", "ROLE-UNUSED", "REF-ROLE", "GROUP-", "PLAN-REF-ROLE", "PLAN-TEACHER", "PLAN-PUPILS"), "roles"),
    (("MAT-UNUSED", "REF-MATERIAL", "QUIZ-KEY", "INSTRUCTIONS", "PLAN-REF-MATERIAL"), "materials"),
    (("VAL-", "GOAL-UNCOVERED"), "values"),
    (("DIV-", "CONCEPT-COUNT"), "diversity"),
    (("TECH-ID-IN-TEXT", "SCRIPT-SHORT", "PUPIL-ACTIONS-FEW"), "text"),
    (("FOOD-TASK",), "safety"),
    (("PROPS-MISSING",), "materials"),
    (("ID-DUP", "REF-BLOCK", "SCHEMA", "PLAN-", "GROUPING-NOTE"), "structure"),
    (("FRAGMENT-", "SOURCE-DUPLICATE", "SOURCE-ID-MISSING"), "sources"),
    (("LLM-",), "review"),
)

# Подсказка эксперту по коду; у остальных - null.
_ACTIONS = {
    "RESOURCE-INTERNET": "Заменить онлайн-задание на офлайн-вариант",
    "RESOURCE-UNAVAILABLE": "Заменить задание или материал на вариант без недоступного ресурса",
    "PRINT-UNAVAILABLE": "Сделать материал без печати: на доске или устно",
    "SLIDES-NO-PROJECTOR": "Перенести содержание слайдов на доску или в раздаточный материал",
    "INNER-TIMING": "Сократить работу или выступления, либо выступают не все группы",
    "SCRIPT-SHORT": "Дописать реплики педагога для этого блока",
    "FACT-UNREGISTERED": "Проверить дату по источнику или убрать её из текста",
    "CULTURE-UNSOURCED": "Убрать утверждение о традиции или заменить заданием «узнайте сами»",
    "DOC-UNSOURCED": "Проверить документ по источнику или убрать номер, дату и того, кто издал",
    "EVENT-MIXUP": "Убрать упоминание другого праздника",
    "GOAL-UNCOVERED": "Добавить в этап задание к этой воспитательной задаче",
    "TECH-ID-IN-TEXT": "Заменить латинские обозначения русскими названиями",
    "MAT-UNUSED": "Использовать материал в этапе или убрать его",
    "QUIZ-KEY": "Добавить в викторину правильные ответы",
    "VOTING-MISSING": "Добавить голосование зрителей и бюллетень",
    "BALLOT-MISSING": "Добавить бюллетень для голосования",
    "PUPIL-ACTIONS-FEW": "Добавить действия учеников в этапе",
    "PARENT-INSTRUCTION": "Добавить памятку для родителей",
    "FOOD-TASK": "Заменить настоящую еду муляжами или рецептом на карточке, либо проверить условия и пищевые ограничения",
    "PROPS-MISSING": "Добавить реквизит в материалы или памятку, либо убрать его из реплик",
}


def category(code: str) -> str:
    """Категория замечания по коду: `RESOURCE-INTERNET` -> `resources`; неизвестный код - `other`."""
    for prefixes, name in _CATEGORIES:
        if code.startswith(prefixes):
            return name
    return "other"


def issue_report(issues: list[Any]) -> list[dict[str, Any]]:
    """Замечания для `quality_report.issues`: поля ТЗ 16.2 и прежние `code`, `severity`, `location`, `message`."""
    return [{"issue_id": f"Q-{index:03d}", "code": i.code, "severity": i.severity, "category": category(i.code),
             "location": i.location, "message": i.message, "repairable": bool(i.repairable),
             "suggested_action": _ACTIONS.get(i.code)} for index, i in enumerate(issues, 1)]