# Андрею: итог второго обновления PR #30 (14.11.2026)

Сборка: `QA/Maksim`, merge `6978ad6`, PR #30 head `97e845a`.

## Что закрыто и подтверждено

| Баг | Проверка | Результат |
|---|---|---|
| **BUG-14** (`JURY-SCORECARD`) | E2E `labour_jury`, 10 класс, 60 мин, родители-оценщики | `completed`, `quality=passed`; материал `jury_scorecard` с правильным `type` |
| **BUG-17** (`PARENTS-OVER`) | UI: 12 родителей, helper + audience, 2 варианта | 17/17 PASS, 2 вкладки; API `variants_3` — 3/3 |
| **BUG-09** (памятка помощникам) | `variants_3` v1–v3 | `parent_instruction` есть во всех вариантах, предупреждений нет |

## Что осталось

| Баг | Что видит пользователь | Где ломается | Подтверждение |
|---|---|---|---|
| **BUG-16** (P2) | `fact_claims`, `frag_...`, `card_task`, `station_cards` в тексте | `checks.py:424`; `teacher_instructions` и `materials[].teacher_notes/content` | `job_20261114_160425_65d1ea`, `job_657d4b90889a4184856245c1a518d9ac`, `job_2de3a2393b674424a24836b9cbc56bd4` |
| **BUG-13** (P2) | 1612 год в задачах, истории нет | `unity_day`; фрагменты PR #30 — `draft`, нужен PR #27 | `q01`/`q02` — `GOAL-UNCOVERED` |
| **BUG-18** (P3) | Ложное предупреждение о тайминге станций | `inner_timing.py` | `variants_3` v1: «5 групп × 5 мин = 25» при 20, хотя группы идут по станциям параллельно |
| **BUG-11** (P3) | `FACT-UNREGISTERED` на 1699/2023 | `checks.py:466` | `job_3e6ea29c79184bf1a25e9e10d47ebda3` (1699), `job_20261114_155725_0edddd` (2023) |
| **BUG-05** (P3) | `SCRIPT-SHORT` на `detailed` и коротких блоках | `script_length.py`, `checks.py` | `q01`, `q03`, `q08`; `q05/q06/q10` чисто |

**Приоритет для тебя:** BUG-16 → BUG-18 → BUG-11/BUG-05. BUG-13 — после PR #27.

## Время и токены (только эта сборка)

| Группа | Запросов | Время генераций | Токены | Среднее на запрос |
|---|---:|---:|---:|---:|
| `qa_check_1114` | 10 | 25,5 мин | 226 623 | 22 662 |
| API-регрессия | 7 | 26,7 мин | 254 862 | 36 409 |
| Targeted E2E (unity, new_year, labour, sverdlovsk) | 4 | 11,2 мин | 105 024 | 26 256 |
| UI (2 варианта + F5) | 2 | 7,9 мин | 72 781 | 36 390 |
| **Итого** | **23** | **71,3 мин** | **659 290** | **28 665** |

Группы шли параллельно, фактическое wall-clock ~32 минуты. Prompt — 532 113, completion — 127 177.

## Трассы

```
data/runs/job_82d4c68ece134a399630e910af46df51   BUG-14, labour_jury — passed
data/runs/job_973ee39c07e14b85b6fab80860ca3411   UI, 2 варианта, BUG-17 — passed
data/runs/job_20261114_160425_65d1ea             BUG-16, sverdlovsk, TECH-ID
data/runs/job_657d4b90889a4184856245c1a518d9ac   BUG-16, new_year 35, TECH-ID
data/runs/job_b55c1df6d37b4985af1582981000b131   BUG-18, variants_3 v1, INNER-TIMING
data/runs/job_3e6ea29c79184bf1a25e9e10d47ebda3   BUG-11, new_year 35, 1699
```

В каждом каталоге: `calls/`, `events.jsonl`, `variants/*/validation.json`, `variant_package.json`.
