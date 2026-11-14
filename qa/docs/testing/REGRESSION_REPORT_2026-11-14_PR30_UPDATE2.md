# Перепрогон после второго обновления PR #30 (14.11.2026)

## 1. Сборка

- `QA/Maksim`, merge `6978ad6`.
- PR #30 head `97e845a`: BUG-14, BUG-17, BUG-09, BUG-16, BUG-11.
- PR #27/#28/#29 не влиты.

## 2. Результаты

| Проверка | Результат |
|---|---|
| Юнит-тесты LLM-сервиса | 262 passed, 872 subtests |
| QA-тесты | 30 passed |
| Backend | 60 passed |
| `qa_check_1114` | 10/10 `completed`, критичных — 0 |
| API-регрессия | 7/7 `completed` |
| Targeted E2E | 4/4 `completed` |
| UI-регрессия | 17/17 PASS |

## 3. Что исправлено

- **BUG-14 закрыт.** `labour_jury` (10 класс, 60 мин, родители-оценщики) — `completed`, `quality=passed`; `jury_scorecard` получает правильный `type`.
- **BUG-17 закрыт.** UI-сценарий с 12 родителями, helper + audience и 2 вариантами — 17/17 PASS, две вкладки; `variants_3` — 3/3.
- **BUG-09 закрыт.** В `variants_3` v1–v3 есть `parent_instruction`, предупреждений `PARENT-INSTRUCTION` нет.

## 4. Предупреждения

| Прогон | Предупреждения |
|---|---|
| `q01` unity 10/45 detailed | `GOAL-UNCOVERED`, `SCRIPT-SHORT` |
| `q02` unity 9/45 standard | `GOAL-UNCOVERED` |
| `q03` christmas 7/30 detailed | `CULTURE-UNSOURCED`, `INNER-TIMING` |
| `q04` christmas 5–8/45 standard | `FACT-UNREGISTERED` |
| `q05` knowledge 2/45 detailed | `FACT-UNREGISTERED` |
| `q06` knowledge 3/30 standard | — |
| `q07` new_year 1/30 standard | — |
| `q08` sverdlovsk 6/45 standard | `SCRIPT-SHORT`, `TECH-ID-IN-TEXT` |
| `q09` mothers 5/45 standard | — |
| `q10` middle urals 10/45 detailed | — |
| API `variants_3` v1 | `INNER-TIMING` (ложное на станциях) |
| API `variants_2` v2 | `VAL-004` |
| Targeted `unity_60` | `GOAL-UNCOVERED` |
| Targeted `new_year_35` | `FACT-UNREGISTERED` (1699) |
| Targeted `labour_jury` | — |
| Targeted `sverdlovsk` | — |

## 5. Остаётся

- **BUG-16 (P2):** технические ID `fact_claims`, `frag_*`, `card_task`, `station_cards` в тексте для педагога.
- **BUG-13 (P2):** 1612 год не раскрыт, пока нет PR #27; `GOAL-UNCOVERED` работает.
- **BUG-12 / BUG-15 (P2):** фронтенд: нет `parent_audience_engagement`, по умолчанию `detailed`.
- **BUG-06 (P2):** формат issue не по ТЗ.
- **BUG-18 (P3):** ложный `INNER-TIMING` на станциях: 5 групп × 5 мин = 25 при 20, хотя группы идут параллельно.
- **BUG-11 (P3):** `FACT-UNREGISTERED` на 1699/2023.
- **BUG-05 (P3):** `SCRIPT-SHORT` на `detailed` и коротких блоках.
- **BUG-19 (P3):** вертеп снова появляется в `q03`, `CULTURE-UNSOURCED`.
- **BUG-04 / BUG-07 (P3):** fixture и демо-каталог.

P1 нет.

## 6. Время и токены

| Группа | Запросов | Время | Токены |
|---|---:|---:|---:|
| `qa_check_1114` | 10 | 25,5 мин | 226 623 |
| API-регрессия | 7 | 26,7 мин | 254 862 |
| Targeted E2E | 4 | 11,2 мин | 105 024 |
| UI | 2 | 7,9 мин | 72 781 |
| **Итого** | **23** | **71,3 мин** | **659 290** |

Prompt — 532 113, completion — 127 177; среднее — 28 665 токенов на запрос. Группы шли параллельно, wall-clock ~32 минуты.

## 7. Ограничения

- Полный E2E на 18 сценариев повторно не гонялся: покрыты 10 `qa_check`, 7 API-кейсов и 4 целевых E2E, включая все исправленные баги.
- Нагрузка 30 одновременных генераций после обновления не проверялась.
- UI-проверка не смотрит содержимое `quality_report`; предупреждения сняты отдельными прогонами.

## 8. Вывод

Блокирующих дефектов нет. Исправления PR #30 по жюри, числу родителей и памятке подтверждены. Остались P2 по техническим ID, 1612 году и фронтенду; 1612 закрывается только после PR #27.
