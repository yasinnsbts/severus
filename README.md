# Каталог школьных событий Свердловской области v1.1 (черновая доработка)

Структура поставки: `catalog/events/` — отдельные карточки; `catalog/events_catalog_RU-SVE.json` — агрегированный каталог; `catalog/catalog_index.csv` — сводная таблица; `catalog/catalog_schema.json` — схема; `catalog/sources/` — источники по событиям; `catalog/regions/RU-SVE/` — метаданные и реестр источников; `prompts/events/` — черновые prompt-файлы.

**Статус:** подготовлена структура и выполнены технические сверки. Поставка НЕ готова к окончательной приёмке: источники не покрывают минимум 3 на каждое событие и 10 на День Победы; экспертная проверка не выполнена. Подробности — в `ACCEPTANCE_REPORT.md`.


## Revision v1.2
Prompt-файлы отредактированы под конкретные события; см. `acceptance/`. Источники не считаются подтверждёнными до заполнения матрицы проверки. Полная приёмка не завершена.


## Audit revision v1.3 (2026-10-20)
Added `ACCEPTANCE_REPORT_v1.3.docx` and `.md`, updated source inventory and fact-check matrix, and appended pending source candidates for seven events. This is a partial audit only; source-count thresholds and expert review remain incomplete. See the v1.3 report for closed/open items.


## Audit v1.4
This is a partial content-audit package. See ACCEPTANCE_REPORT_v1.4.md. `pending` and `rejected` sources are not approved for generation.


## v1.5 partial final audit
See `ACCEPTANCE_REPORT_v1.5.md`, `acceptance/url_open_audit.csv`, and `acceptance/automated_validation.json`. Full acceptance remains open.


## v1.6 audit addendum
See `ACCEPTANCE_REPORT_v1.6.md`, `acceptance/internal_age_review_checklist.csv`, and updated source inventory. This package is an audit report/release candidate, not accepted final data: source minimums remain unverified.


## v1.7 audit update (2026-10-20)

See `ACCEPTANCE_REPORT_v1.7.md`, `acceptance/supplementary_source_verification_v1.7.csv`, `acceptance/internal_age_review_by_event_v1.7.csv`, and `acceptance/automated_validation_v1.7.json`. Status remains NOT_ACCEPTED because the independence/source minimums and complete direct URL/content verification are not met.


## v1.8 audit update

See `ACCEPTANCE_REPORT_v1.8.md`, `acceptance/full_prompt_age_content_review_v1.8.csv`, and `acceptance/automated_validation_v1.8.json`. Disputed UDTK first-battle date references were removed from this revision. Source minimums remain unconfirmed.


## Source audit status v1.9

The source threshold is not yet met. See `ACCEPTANCE_REPORT_v1.9.md`, `acceptance/source_audit_v1.9.csv`, and `acceptance/source_thresholds_v1.9.csv`. Only sources with a relevant excerpt and successful direct URL opening in this revision count as accepted.


## Source audit status v1.9

The source threshold is not yet met. See `ACCEPTANCE_REPORT_v1.9.md`, `acceptance/source_audit_v1.9.csv`, and `acceptance/source_thresholds_v1.9.csv`. Only sources with a relevant excerpt and successful direct URL opening in this revision count as accepted.


## Source follow-up v2.2
See `ACCEPTANCE_FOLLOWUP_v2.2.md`, `acceptance/source_audit_v2.2_additions.csv`, and `acceptance/source_thresholds_v2.2_addendum.json`. Acceptance remains incomplete.


## v2.3 follow-up

See `ACCEPTANCE_FOLLOWUP_v2.3.md` and `acceptance/source_audit_v2.3_additions.csv`. School-specific graduation order is no longer required; regional, school-year-specific sources are acceptable. Unopened URLs remain uncounted.


## Итоговая поставка v2.5 (2026-10-21)
Добавлены две региональные карточки-кандидаты (День образования Свердловской области и День народов Среднего Урала), обновлены агрегированный JSON и CSV-индекс, добавлен отчёт для защиты `ОТЧЕТ_ДЛЯ_ЗАЩИТЫ_RU-SVE_v2.5.docx`. Техническая синхронизация не означает полной содержательной приёмки: большинство карточек сохраняют incomplete, а дата Дня народов Среднего Урала требует ежегодной сверки по официальному анонсу.
