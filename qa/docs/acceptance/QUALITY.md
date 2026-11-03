# Критерии качества — Итерация 1

Валидаторы проверяют один вариант (`variant`) вместе с исходным запросом (`input_data`) и возвращают список issue. Исключения наружу не пробрасываются: при некорректных типах возвращается issue с `critical`.

Четырёхуровневая шкала ниже — внутренняя шкала QA-модуля. Для ТЗ 16.2–16.3 она маппится так: `critical` → `critical` / `blocked`, `high` и `medium` → `warning` / `warning`, `low` → `info` / `passed` (если других проблем нет). Сервис `services/school_events_llm` использует шкалу ТЗ напрямую.

Формат issue:

```python
{
    "code": str,
    "severity": "critical" | "high" | "medium" | "low",
    "message": str,
    "field": str | None,
}
```

## Проверки

### Структура и ссылки

| Код | Severity | Что проверяет |
|---|---|---|
| `INVALID_VARIANT` | critical | `variant` отсутствует или не является объектом |
| `MISSING_COLLECTION` | critical | `timeline`, `roles` или `materials` отсутствует / не список |
| `MISSING_FIELD` | high | Пустые `concept.summary`, `concept.goal`, `teacher_instructions`, `teacher_script` блока |
| `TOO_FEW_BLOCKS` | high | В `timeline` меньше 2 блоков |
| `ORPHAN_ROLE_ID` | critical | `role_id` из `timeline[].role_ids` не существует в `roles` |
| `ORPHAN_MATERIAL_ID` | critical | `material_id` из `timeline[].material_ids` не существует в `materials` |
| `ORPHAN_BLOCK_ID` | critical | `block_id` из `parent_participation_plan`, `roles[].block_ids` или `materials[].used_in_blocks` не существует в `timeline` |

### Родители

| Код | Severity | Что проверяет |
|---|---|---|
| `PARENT_ROLE_FORBIDDEN` | critical | Есть роль `participant_type="parent"` при `parents_enabled=false` |
| `PARENT_PLAN_FORBIDDEN` | critical | `parent_participation_plan.enabled=true` при `parents_enabled=false` |
| `PARENT_PLAN_MISSING` | high | `parents_enabled=true`, но план отсутствует или `enabled=false` |
| `PARENTS_OVER_COUNT` | critical | Суммарный `count` родительских ролей в одном блоке больше `parents_count` |

### Ресурсы

| Код | Severity | Что проверяет |
|---|---|---|
| `PRINTER_REQUIRED_MISSING` | high | У материала `print_required=true`, но нет `"printer"` в `dependencies` и `input.resources.printer != true`; также поддержан legacy-флаг `input.resources.printer_required` |

### Тайминг

| Код | Severity | Что проверяет |
|---|---|---|
| `TIMING_INVALID_INPUT` | critical | Нет `timeline`-списка или `duration_minutes` во входных данных |
| `TIMING_INVALID_BLOCK` | critical | Блок не объект или `start_minute` / `duration_minutes` не число |
| `TIMING_TOTAL_MISMATCH` | critical | Сумма `duration_minutes` не равна `input.duration_minutes` |
| `TIMING_START_NOT_ZERO` | critical | Первый блок начинается не с 0-й минуты |
| `TIMING_NON_POSITIVE` | critical | `duration_minutes <= 0` |
| `TIMING_GAP` | critical | Между блоками есть разрыв |
| `TIMING_OVERLAP` | critical | Блоки пересекаются по времени |

### Возрастные эвристики

| Код | Severity | Что проверяет |
|---|---|---|
| `AGE_LONG_BLOCK` | medium | Для группы `1-4` блок длиннее 15 минут |
| `AGE_LONG_WORDS` | low | Для группы `1-4` в `teacher_script` есть слова длиннее 12 букв |
| `AGE_ALL_SHORT` | low | Для группы `9-11` все блоки ≤ 5 минут |

## Политика severities

- `critical` — вариант нельзя отдавать пользователю, нужен repair/повторная генерация.
- `high` — обязательное замечание, желательно исправить до выдачи.
- `medium` / `low` — предупреждения, не блокируют выдачу.

## В scope первой итерации

- Структура сценария и обязательные разделы.
- Минимум блоков и непустые ключевые тексты.
- Тайминг: сумма, старт, разрывы, пересечения, положительные длительности.
- Базовая возрастная уместность для групп `1-4` и `9-11`.
- Логика родителей: роли, план, лимит `parents_count`.
- Ссылочная целостность ролей, материалов и блоков.
- Простой контроль печати (`printer`).

## Отложено на следующие итерации

Это зона QA-модуля `qa/validators/`. Часть проверок уже есть в сервисе `services/school_events_llm` и в общем Backend; здесь они появятся позже, чтобы не дублировать логику.

- Культурный контент: регион, праздники, тематика.
- LLM-as-judge и семантическая оценка текстов.
- Глубокая возрастная оценка: когнитивная нагрузка, сложность языка, объём текста.
- Валидация по JSON Schema.
- Проверка соответствия `pupils_count` количеству ролей.
- Проверка источников и фактических утверждений.

## Запуск тестов

```bash
python -m pytest qa/tests/ -v
```

## Пример вызова в пайплайне

```python
from qa.validators import validate_structure, validate_timing, check_age_heuristics

issues = [
    *validate_structure(variant, input_data),
    *validate_timing(variant, input_data),
    *check_age_heuristics(variant, input_data),
]

critical = [issue for issue in issues if issue["severity"] == "critical"]
quality = {
    "passed": not critical,
    "issues": issues,
    "blocking_issues": critical,
}
```

Если `quality["passed"]` равен `false`, вариант отправляется в repair или генерируется заново. Предупреждения `medium` / `low` можно сохранить в отчёте и показать редактору.
