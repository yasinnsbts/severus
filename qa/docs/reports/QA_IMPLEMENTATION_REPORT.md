# QA Implementation Report — Итерация 1

## Что реализовано

- `qa/validators/structural_validator.py`
  - обязательные разделы `concept`, `timeline`, `roles`, `materials`, `teacher_instructions`;
  - минимум 2 блока и непустые `teacher_script`;
  - ссылочная целостность `role_id`, `material_id`, `block_id`;
  - логика родителей: запрет ролей/плана при `parents_enabled=false`, обязательный план при `parents_enabled=true`, лимит `parents_count` в блоке;
  - контроль печати по `materials[].print_required`, `dependencies` и `resources.printer`.
- `qa/validators/timing_validator.py`
  - сумма длительностей равна запрошенной;
  - первый блок начинается с 0;
  - блоки без разрывов и пересечений;
  - положительные длительности;
  - безопасная обработка блоков с некорректными типами.
- `qa/validators/age_heuristics.py`
  - `1-4`: блок длиннее 15 минут — `medium`, слова длиннее 12 букв — `low`;
  - `9-11`: все блоки ≤ 5 минут — `low`;
  - для `5-8` предупреждений нет.
- `qa/validators/__init__.py` — экспорт трёх функций без изменения публичных имён.
- Тесты переведены на корректный путь к фикстурам: `Path(__file__).parent / "fixtures"`.

Все проверки возвращают только `list[dict]`. При некорректном `variant` или входных данных возвращается issue, исключения не пробрасываются.

## Тесты

Всего **28 тестов**:

- `qa/tests/test_structural.py` — **15**:
  - happy path без issues;
  - отсутствующие обязательные коллекции;
  - пустые `concept.summary` / `concept.goal`;
  - пустой `teacher_script`;
  - один блок вместо двух;
  - orphan `role_id`, `material_id`, `block_id`;
  - родители выключены, но есть родительская роль и включённый план;
  - родители включены без плана;
  - превышение `parents_count`;
  - печать без принтера и с доступным принтером;
  - формат `school_event` без падения;
  - не-объект `variant` без исключения.
- `qa/tests/test_timing.py` — **8**:
  - happy path;
  - сумма меньше и больше запрошенной;
  - разрыв;
  - пересечение;
  - старт не с нуля;
  - неположительная длительность;
  - отсутствующий `duration_minutes` без исключения.
- `qa/tests/test_age_heuristics.py` — **5**:
  - `1-4`: длинный блок;
  - `1-4`: длинные слова;
  - `9-11`: все блоки короткие;
  - `5-8`: нормальный сценарий без предупреждений;
  - `9-11`: нормальная 90-минутная сетка без ложных срабатываний.

Каждый негативный тест проверяет конкретный `code` и/или `severity`.

## Фикстуры

`qa/tests/fixtures/outputs/` — 15 файлов:

- `happy_path_variant.json`;
- существующие: `broken_references.json`, `broken_timing.json`, `parents_violation_variant.json`;
- новые: `empty_concept.json`, `empty_teacher_script.json`, `one_block_only.json`, `timing_gap.json`, `timing_overlap.json`, `wrong_start.json`, `orphan_role_id.json`, `orphan_material_id.json`, `parents_enabled_no_plan.json`, `parents_over_count.json`, `print_required_no_printer.json`.

Используются входы `01`–`06` и `08` из `qa/tests/fixtures/inputs/`.

## Результат запуска

```text
python -m pytest qa/tests/ -v
28 passed
```

## Следующие итерации

- Культурная проверка: регион, праздник, тематика, уместность формулировок.
- LLM-as-judge для семантической оценки концепции и сценария.
- Глубокая возрастная оценка: когнитивная нагрузка, сложность языка, длина блоков и текстов.
- Валидация по JSON Schema.
- Проверка соответствия численности участников и ролей.
- Проверка фактических утверждений и источников.
- Repair loop: передача конкретных issue в повторную генерацию.
