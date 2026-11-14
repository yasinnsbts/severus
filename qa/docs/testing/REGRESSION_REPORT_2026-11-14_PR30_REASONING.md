# Перепрогон PR #30 с reasoning medium (14.11.2026)

## 1. Сборка

- `QA/Maksim`, merge `7af9502`, PR #30 head `d6f1321`.
- Локально применён порог `SCRIPT-SHORT` 90% (`script_length.warning_ratio = 0.9`).
- PR #27/#28/#29 не влиты.

## 2. Reasoning medium

Проверка шла с `LLM_REASONING=*=medium`.

- В манифестах всех этапов: `reasoning_effort=medium`.
- `response.reasoning.txt` создаётся, `reasoning_chars > 0`.
- `max_tokens` увеличен на `reasoning_extra_output_tokens=2000`.
- В `config/generation.json` по умолчанию `null`; medium включается через env/`.env`.

## 3. Результаты

| Проверка | Результат |
|---|---|
| Юнит-тесты LLM-сервиса | 276 passed, 874 subtests |
| QA-тесты | 30 passed |
| Backend | 60 passed |
| `qa_check_1114b` | 10/10 `completed`, критичных — 0 |
| API-регрессия | 6/7 `completed`, 1 `failed` (повтор прошёл) |
| UI-регрессия | 17/17 PASS |

## 4. Что подтвердилось

- **BUG-05 закрыт:** порог 90% убрал шум; `r08` (323/350) и `variants_2` чистые.
- **BUG-11 закрыт:** 2023 заменяется бланком, 1699 — корректное предупреждение.
- **BUG-18 закрыт:** станции считаются верно, сообщение переписано.
- **BUG-19 закрыт:** вертеп убран.
- **BUG-14, BUG-17, BUG-09** — по-прежнему закрыты.

## 5. Новые/оставшиеся дефекты

- **BUG-16 (P2):** `commitments_book_pages` в `teacher_script` (UI `job_f37a1bca82c04f2fa564b87863943ddc`, v2).
- **BUG-20 (P2):** ложный `INNER-TIMING` на параллельных парах и работе следующего блока:
  - `r02` v2: 13 пар × 4 мин = 52 при блоке 10;
  - UI v1: 15-минутная работа и 5 выступлений приписаны 5-минутному блоку.
- **BUG-21 (P2):** редкий schema-fail на 35 учениках: `block.pupil_actions`/`role_ids` отсутствуют после 3 попыток; повтор прошёл. `job_c7df9e8e284441f181f5e78d48da4a27` → `job_a186e61612704276a7fa669721be95a7`.
- **BUG-22 (P2):** 3 варианта с medium — 17,3 мин, клиентский таймаут 900 с срабатывает раньше (`job_7a0a4fdc1f3046f88e3f9dd3cbd74ff7`, 3/3 completed).
- **BUG-12, BUG-15, BUG-06** — без изменений.
- **BUG-04, BUG-07** — P3.

## 6. Предупреждения

| Прогон | Предупреждения |
|---|---|
| `r01` labour jury | — |
| `r02` knowledge 2 варианта | `INNER-TIMING` (v2, ложный) |
| `r03` knowledge helpers | — |
| `r04` new_year | — |
| `r05` sverdlovsk | — |
| `r06` christmas | `FACT-UNREGISTERED` (25 декабря) |
| `r07` unity | `GOAL-UNCOVERED` (BUG-13 отложен) |
| `r08` knowledge 2 класс | — |
| `r09` mothers helpers | — |
| `r10` middle urals | `DOC-UNSOURCED` |
| UI основной | `INNER-TIMING`, `TECH-ID-IN-TEXT` |
| API `variants_2` | — |
| API `large_class_35` | первый прогон `failed`, повтор `completed` |

## 7. Время и токены

| Группа | Запросов | Время | Токены |
|---|---:|---:|---:|
| `qa_check_1114b` | 10 | 43,8 мин | 336 861 |
| API-регрессия | 7 | 49,6 мин | 303 608 |
| UI | 2 | 12,8 мин | 77 084 |
| Повтор large_class_35 | 1 | 3,4 мин | 29 319 |
| **Итого** | **20** | **109,6 мин** | **746 872** |

Prompt — 553 357, completion — 193 515; среднее — 37 344 токена на запрос. Wall-clock около 85 минут.

## 8. Вывод

Reasoning medium работает и подтверждён в трассах. Блокирующих P1 нет, но medium замедлил генерацию: 3 варианта — 17,3 минуты. Остались BUG-16, BUG-20, BUG-21, BUG-22 и фронтенд/формат. BUG-13 отложен до PR #27.
