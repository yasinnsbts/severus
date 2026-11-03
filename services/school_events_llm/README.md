# school_events_llm

Независимый прототип LLM-сервиса «Школьные события» по актуальному ТЗ v1.5 из `docs/tz/`.

Сервис принимает запрос в формате контракта 01, собирает контекст и prompt-блоки, генерирует от 1 до 3 вариантов через выбранную LLM, проверяет результат Python-кодом и формирует ответ по замороженному контракту 02.

Реализованы CLI-прототип и внутренний HTTP-сервис для подключения к основному Backend Severus. По умолчанию HTTP-сервис запускается на `127.0.0.1:8090`.

## Структура прототипа

| Компонент | Расположение |
|---|---|
| Системный prompt | `prompts/core/system.md`, `prompts/core/safety.md` |
| Правила этапов | `prompts/tasks/*.md` |
| Шаблон пользовательского сообщения | `prompts/templates/user_message.md` |
| Каталог событий и источники | общий каталог проекта `severus/catalog/` (сервис только читает) |
| Справочники ценностей и зависимостей | `catalog/values.json`, `catalog/dependencies.json` |
| Динамические блоки контекста | `prompts/events`, `age`, `grade`, `size`, `duration`, `formats`, `participants`, `values`, `family`, `teacher`, `school`, `resources`, `region`, `modes` |
| Форматы ответа модели | `prompts/output/*.md` |
| Сборщик prompt | `app/prompting/composer.py` |
| Контракт ответа модели | `app/contracts/llm.py`, JSON Schema в `schemas/` |
| Конвейер генерации | `app/generation/pipeline.py` |
| Тайминг и группировка | `app/generation/timing.py`, `app/generation/grouping.py` |
| Проверки результата | `app/validation/checks.py` |
| Проверка корпуса источников | `app/sources.py` |
| Клиенты моделей | `app/llm/client.py` |
| Локальная очередь и общий lock-файл | `app/llm/mutex.py` |
| Эталонные примеры | `examples/golden`, `examples/rendered`, `examples/readable` |

Подробное описание сборки prompt и контрактов находится в `docs/PROMPTS.md`.

## Требования

- Python 3.11 или новее.
- Для реального теста Qwen3.5-9B: LM Studio с локальным сервером на `127.0.0.1:1234`.
- Все служебные операции выполняются через `python -m app ...` и `python -m pytest`.
- `.bat`, `.ps1` и `.sh` не требуются.

## Установка

Команды выполняются из каталога `services/school_events_llm/`.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m pytest
```

Windows CMD:

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
copy .env.example .env
python -m pytest
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m pytest
```

## Внутренний HTTP API

Для интеграции с основным Backend сервис запускается командой:

```bash
python -m app serve
```

Основные переменные окружения:

```dotenv
SERVICE_HOST=127.0.0.1
SERVICE_PORT=8090
SERVICE_AUTH_TOKEN=
LLM_SERVICE_FIXTURE_MODE=false
LITELLM_BASE_URL=
LITELLM_API_KEY=
```

`LLM_SERVICE_FIXTURE_MODE=true` позволяет проверить полный Backend -> LLM-service -> Backend сценарий без реального провайдера модели. URL и API-ключ внешнего OpenAI-compatible шлюза задаются только через окружение или секреты хостинга.

## Первый тест Qwen3.5-9B

1. Загрузить Qwen3.5-9B в LM Studio.
2. Включить OpenAI-совместимый сервер на порту `1234`.
3. Проверить выбранную модель.
4. Запустить генерацию на одном из примеров.

```bash
python -m app health
python -m app generate examples/requests/ex1_knowledge_day.json
```

Если трассировка включена, артефакты запуска сохраняются в `data/runs/<job_id>/`. Там находятся итоговый `final_result.json`, читаемые варианты, фактические prompt, сырые ответы модели, parsed JSON, манифесты и результаты проверок.

В каждом `calls/call_XXXX/manifest.json` записаны токены вызова (`usage`: вход и выход по данным провайдера), итог за генерацию - в `metadata.json` (`tokens`, с разбивкой по этапам) и в выводе `generate`. Общий журнал всех генераций - `data/runs/runs.jsonl`: одна строка на прогон (событие, модель, статус, вызовы, время, токены, замечания, ошибка), в том числе для неудачных.

## Работа без реальной модели

Эталонные ответы позволяют прогнать конвейер без LM Studio:

```bash
python -m app generate examples/requests/ex1_knowledge_day.json --fixture examples/golden/ex1_knowledge_day.json
```

Можно намеренно повредить первый ответ указанного этапа и проверить repair:

```bash
python -m app generate examples/requests/ex1_knowledge_day.json --fixture examples/golden/ex1_knowledge_day.json --broken scenario_plan materials
```

## CLI

```text
python -m app serve [--host HOST] [--port PORT]
python -m app health [--model KEY]
python -m app compose REQUEST.json --stage STAGE [--json]
python -m app generate REQUEST.json [--model KEY] [--out FILE]
python -m app batch REQUEST.json|ПАПКА ... [--model KEY]
python -m app experiment REQUEST.json --context-mode full|universal --cultural-context on|off [--experiment-tag TAG] [--experiment-pair-id ID]
python -m app validate PACKAGE.json --request REQUEST.json
python -m app render PACKAGE.json --request REQUEST.json [--markdown]
python -m app export-schemas
python -m app sources-check
python -m app catalog-check
```

Публичные команды `generate` и `compose` всегда используют `context_mode=full` и включенный культурный контекст. Параметры H2/H3 доступны только через `experiment`. Входной контракт 01 не содержит и не должен содержать экспериментальные флаги.

Этапы модели:

- `variation_plan`
- `scenario_plan`
- `scenario_blocks`
- `scenario_block`
- `materials`
- `quality_review`

`quality_review` вызывается только если `llm_quality_review=true` в `config/generation.json`. Основные структурные проверки в любом случае выполняются Python-кодом.

`batch` прогоняет набор запросов подряд тем же путём, что `generate`, и печатает сводную таблицу: статус, число вызовов, время, токены, критичные замечания и предупреждения. Сводка сохраняется в `data/runs/batch_<время>.md` и `.json`. Набор для проверки разных возрастов, длительностей и режимов участия родителей - `examples/requests/matrix/` (дополняет E2E-набор QA в `qa/tests/fixtures/inputs/`):

```bash
python -m app batch examples/requests/matrix
```

### Устойчивость к ошибкам модели

- **Ошибки провайдера.** Временные ошибки (429, 5xx, таймаут, нет сети) повторяются с паузой: `provider_retry_attempts` и `provider_retry_backoff_seconds` в `config/generation.json`. Ошибки авторизации и настройки не повторяются. Каждый повтор пишется в трассу (`llm_call_retry`).
- **Ответ не по схеме.** Этап повторяется с текстом ошибки (`max_repair_attempts_per_stage`).
- **Исправления до проверки схемы** (`stage_output_fixed` в трассе): `material_id` и `role_id` приводятся к виду `^[a-z][a-z0-9_]*$` одинаково во всех ссылках, ID блоков - к `block_NN`; зависимости материалов - только из `catalog/dependencies.json` (синонимы заменяются, остальное переносится в `teacher_notes`); значения перечислений и адресаты материалов - к допустимым; расходники не становятся материалами и убираются из ссылок блоков; `family_task` снимается с памятки родителям, бюллетеня и других материалов для взрослых.
- **Голосование без зрителей.** Если выбрано голосование, а модель сделала всех родителей помощниками, голосующими считаются родители из блока голосования. Инструкция к награждению разрешена и по итогам работы жюри.
- **Разбор JSON ответа**: допускаются переносы строк внутри строк, комментарии `// …` убираются, неэкранированная кавычка внутри текста («…дружно!" (Через 10 минут…») экранируется. `content` материала списком или словарём превращается в текст, пустой `used_in_blocks` - в блоки, которые ссылаются на материал по плану, пустой чек-лист реквизита собирается из названия и заметок, без `groups_count` число групп считает программа.
- **Ссылки на материалы.** Блоки ссылаются только на материалы плана; `used_in_blocks` и голосование - только на существующие блоки и материалы (`material_refs_fixed` в трассе).
- **Ошибки задачи в HTTP API** - в формате контракта 02: `field=null` для замечаний проверки, `retryable=true` для отказов по качеству и временных ошибок модели, не больше 5 причин на вариант. Если генерация упала до вариантов - `OUTPUT_SCHEMA_INVALID` или код ошибки модели, без технических подробностей в тексте.

## Режимы full и universal

Состав prompt-блоков задается в `config/experiment_modes.json`.

`full` использует точный класс, предпочтения педагога, профиль школы, реальные ресурсы, региональный и проверенный культурный контекст.

`universal` предназначен только для эксперимента. В этом режиме не подключаются `GRADE`, `TEACHER`, `SCHOOL`, `REGION`, а реальные ресурсы заменяются нейтральным ресурсным профилем. Предпочтения педагога сбрасываются к дефолтам, кроме полей из `keep_teacher_fields` (по умолчанию `script_detail`, чтобы универсальная версия не была короче по полноте). В prompt добавляется блок `MODE`.

Раздел «Справочные данные» подключается во всех режимах. В `universal` фрагменты в него не передаются, поэтому он прямо запрещает фактические утверждения. При `--cultural-context off` отключаются региональные и культурные темы, а фрагменты о самом событии остаются.

Изменение состава экспериментального режима не требует изменения Python-кода генератора.

## Модели и reasoning_mode

Модель выбирается через `ACTIVE_MODEL` в `.env` либо `default_model` в `config/models.json`. Генератор не должен изменяться при смене модели.

Для локального Qwen используется OpenAI-совместимый API LM Studio. `model_id: auto_loaded` разрешает автоматически выбрать единственную загруженную модель. Если LM Studio сообщает несколько загруженных моделей, нужно явно задать `model_id`.

`reasoning_mode` и `disable_thinking_method` управляют обработкой рассуждений модели. Независимо от способа отключения reasoning, служебные блоки `<think>` и `<analysis>` не должны попадать в parsed JSON.

## Очередь и межпроцессная блокировка

Вызовы к локальной LLM внутри одного процесса сервиса всегда сериализуются и выполняются по одному.

Если LM Studio одновременно используют другие процессы, можно включить общий lock-файл:

```dotenv
LOCAL_LLM_MUTEX_ENABLED=true
LOCAL_LLM_MUTEX_PATH=data/locks/lm_studio.lock
```

По умолчанию `LOCAL_LLM_MUTEX_ENABLED=false`. Все процессы, которые должны координировать доступ к одной локальной модели, обязаны использовать один и тот же путь lock-файла.

## Каталог событий

Карточки событий и источники сервис читает из общего каталога проекта `severus/catalog/` (путь задаётся `CATALOG_DIR`, по умолчанию `../../catalog`). Своей копии каталога в сервисе нет: в `services/school_events_llm/catalog/` лежат только справочники ценностей и зависимостей материалов.

Из карточки генератор берёт `title`, `category`, `supported_age_groups`, `supported_formats`, `educational_goals`, `values`, `date_rule`, `age_appropriateness_notes`, `facts_to_verify`, `regional_topics`. Смысл события для сценария (акценты, идеи активностей) описан в `prompts/events/<event_id>.md`.

Генератор принимает все события каталога: это тот же список, который бэкенд отдаёт фронтенду (`GET /api/v1/catalog/events`). Отдельных статусов у событий нет: карточка в `catalog/events/` - событие доступно.

При загрузке сервис проверяет каталог и сообщает **все** найденные проблемы сразу: нет обязательного поля, неизвестная ценность, нет совета для поддерживаемой возрастной группы, нет блока `prompts/events/<event_id>.md` и т. п. Проверить каталог без генерации:

```bash
python -m app catalog-check
```

Код выхода 4 означает, что каталог не подходит генератору; список проблем печатается в stderr.

## Источники и факты

Источники и фрагменты-цитаты хранятся в общем каталоге: `catalog/sources/<event_id>.json`, поля `sources` и `fragments`.

Проверка структуры и покрытия:

```bash
python -m app sources-check
```

`sources-check` проверяет уникальность идентификаторов, статусы, пустые цитаты, разных составителя и проверяющего, ссылки на события и темы, а также то, что у каждого фрагмента указан `source_id` из списка источников корпуса.

В генерацию попадают только фрагменты со статусом `verified`. Фактологические утверждения фиксируются в `fact_claims`. Если утверждение не подтверждено проверенным фрагментом, оно должно быть удалено, заменено либо явно отмечено `needs_teacher_check=true` в разрешенных ТЗ случаях.

Сейчас в каталоге есть только черновые фрагменты (`draft`), поэтому в генерацию цитаты не попадают и модель работает без фактических утверждений. Культурное и историческое покрытие до продуктового использования должно быть проверено куратором.

## Конфигурация и воспроизводимость

`config/generation.json` содержит параметры этапов, включая `max_repair_attempts_per_stage` и `temperature_hint`. Если у этапа задан `max_output_tokens_per_variant`, лимит ответа равен этому значению, умноженному на число вариантов, но не больше `max_output_tokens`. Так настроен `variation_plan`: 1300 токенов на концепцию, потолок 3900, чтобы ответ с тремя концепциями не обрезался.

`config/experiment_modes.json` определяет состав контекста экспериментов.

`config/school_profile.json` содержит серверный профиль школы.

Манифест каждого LLM-вызова сохраняет фактически использованные prompt-блоки, версии, SHA-256, использованные переменные, режим контекста и контрольные суммы конфигураций и источников. Это позволяет разбирать конкретную генерацию после изменения prompt или конфигурации.

## Что проверяется автоматически

Тесты покрывают входной контракт и серверные дефолты, сборку prompt, режимы full/universal, точный тайминг, группировку школьников, родителей, ресурсы, ценности, семейное задание, фактологические ссылки, рендер контракта 02, repair, трассировку, Model Router, reasoning stripping, общий lock-файл, проверку общего каталога событий и корпуса источников.

Актуальное количество успешно выполненных тестов следует смотреть в выводе `python -m pytest`. README намеренно не фиксирует число тестов, чтобы оно не устаревало после добавления новых проверок.

## Что еще не проверено в этой среде

Реальная Qwen3.5-9B в LM Studio здесь не запускалась. Поэтому до первого коммита, который заявляет качество генерации, необходимо отдельно проверить на целевой машине:

- корректность подключения к LM Studio;
- качество каждого этапа Qwen3.5-9B;
- скорость и потребление контекста;
- реальное поведение `reasoning_mode`;
- устойчивость structured output;
- достаточность repair на реальных ошибках модели.

Внутренний HTTP API на `127.0.0.1:8090` уже реализован и используется интеграционным контуром Backend -> LLM-service. Текущая очередь задач и хранилище проектов находятся в памяти процесса и подходят для прототипа. Постоянное хранилище, распределённая очередь, CSV-аналитика и полный Replay остаются последующими этапами.