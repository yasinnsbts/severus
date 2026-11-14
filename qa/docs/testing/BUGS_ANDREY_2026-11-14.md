# Андрею: что сломано и где (14.11.2026)

Сборка: `QA/Maksim`, только **PR #30** (`03c6b0c`). PR #27/#28/#29 не влиты.

## Блокирует

| # | Что видит пользователь | Где ломается | Что сделать |
|---|---|---|---|
| **BUG-14** (P1) | Сценарий с жюри (`labour_day`, 10 класс) завершается `failed` | `app/validation/checks.py:351`: проверка ищет `jury_scorecard` только в `materials[].type`, а модель ставит `material_id="jury_scorecard"`, `type="quiz"` | Принимать по `material_id` или нормализовать `type`; не выдавать `critical`, если лист критериев есть |
| **BUG-17** (P2) | Из двух вариантов остаётся один, задание `partial`; в UI одна вкладка | Планирование ролей + `checks.py:317`: при 12 родителях и ролях `helper` + `audience` модель делает 12 помощников и 1 зрителя — 13 | Делить `parents_count` между ролями: 11 + 1, а не 12 + 1 |

## Вернулось / остаётся

| # | Что видит пользователь | Где ломается | Комментарий |
|---|---|---|---|
| **BUG-16** (P2) | В тексте для педагога `teacher_fallback`, `colored_papers` | `checks.py:424`; `teacher_instructions`, `materials[].teacher_notes` | Чистить технические ID в промпте/постобработке |
| **BUG-09** (P2) | Родители-помощники есть, памятки `parent_instruction` нет | `checks.py:347`; `variants_3`, v2 и v3 | Памятка должна создаваться при `helper` всегда |
| **BUG-13** (P2) | «Знакомство с событиями 1612 года» в задачах, истории в блоках нет | `catalog/sources/unity_day.json`: в PR #30 фрагменты `draft`, проверенных цитат нет | Ждёт PR #27; сейчас `GOAL-UNCOVERED` корректно предупреждает |
| **BUG-11** (P3) | `FACT-UNREGISTERED` на 1700, 2008, 2023 | `checks.py:466`; материалы с датами | Дату регистрировать в `fact_claims` или не подавать как факт |

## Трассы

```
data/runs/job_2dfc94e57e84454f8316660c8d51f60d   BUG-14, E2E-16 labour_day
data/runs/job_3220de56ecc24792afee1786cbb14b41   BUG-17, UI 2 варианта, PARENTS-OVER
data/runs/job_62fb272022d64997b1939c994210e975   BUG-09, BUG-16, BUG-11 (variants_3, 2023)
data/runs/job_11d9be74f8bc479aacb92ae25a607ca2   BUG-11, new_year 35 учеников, 1700
data/runs/job_4372f3059b5e499695be8888589c0e03   BUG-16, BUG-11 (E2E-18, 2008)
data/runs/job_20261114_143202_0dbaf1             BUG-13, q01 без PR #27
data/runs/job_20261114_143305_7ed322             BUG-13, q02 без PR #27
```

В каждом каталоге: `calls/` (`prompt.md`, `messages.json`, `response.raw.txt`, `manifest.json`), `events.jsonl`, `variants/*/validation.json`, `variant_package.json`.

## Порядок

1. **BUG-14** — без него сценарии с жюри падают.
2. **BUG-17** — без него штатный UI-сценарий с двумя ролями родителей даёт `partial`.
3. **BUG-16 и BUG-09** — качество текста и памятка.
4. **BUG-11** — даты.
5. **BUG-13** — после слияния PR #27, затем перепрогон `q01`/`q02`.
