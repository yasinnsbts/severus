# Контракт 01 — JSON-запрос фронтенда в LLM-бэкенд (v1.5 — без изменений относительно v1.4)

> **v1.5: контракт заморожен.** JSON этого документа (состав полей, типы, ограничения, значения по умолчанию, примеры) **идентичен v1.4**. Новые возможности v1.5 — ценностный слой, профиль школы, правила участия семьи, культурный контур, режимы экспериментов — реализуются внутри сервиса и в контракте 03 и не требуют изменений фронтенда и `backend/schemas.py`. Общий бэкенд «Северус» передаёт этот JSON в сервис `services/school_events_llm` без преобразования (ТЗ 1.3, 15.0).

**Источник:** фронтенд. **Получатель:** `POST /api/v1/generations`. Ниже один полноценный валидный пример с тремя вариантами, 27 учениками, 12 родителями, двумя разрешёнными родительскими ролями и зрительским призом. Все тексты и численные параметры примера иллюстративные. Состав полей сверен с ТЗ v1.4 и v1.5.

## 1. Полный пример JSON

```json
{
  "event_id": "knowledge_day",
  "region_id": "RU-SVE",
  "grade_group": "5-8",
  "grade": 6,
  "pupils_count": 27,
  "duration_minutes": 45,
  "format": "class_hour",
  "participants": {
    "teachers_count": 1,
    "parents_enabled": true,
    "parents_count": 12,
    "parent_roles": [
      "helper",
      "audience"
    ],
    "parent_audience_engagement": "audience_award",
    "parent_notes": "Двое родителей помогают с раздатками, остальные присутствуют как зрители и могут голосовать."
  },
  "resources": {
    "projector": true,
    "printer": true,
    "internet": false,
    "audio": false,
    "room": "classroom",
    "available_materials": [
      "paper",
      "markers"
    ],
    "extra_notes": "Нет отдельного актового зала."
  },
  "teacher_preferences": {
    "style": "interactive",
    "script_detail": "detailed",
    "difficulty": "standard",
    "interaction_level": "high",
    "group_work": true,
    "preparation_effort": "minimal",
    "notes": "Меньше монологов, больше работы в командах."
  },
  "generation": {
    "variants_count": 3,
    "language": "ru"
  }
}
```

## 2. Описание каждого поля

| Поле | Тип | Обязательность / смысл | По умолчанию на сервере (V1) |
|---|---|---|---|
| `event_id` | `string, обязательно` | ID события из каталога. Например `knowledge_day`, `victory_day`; не произвольное название. | Нет — обязательно |
| `region_id` | `string, обязательно` | Код региона. Для пилота строго `RU-SVE` (Свердловская область). | Нет — обязательно (`RU-SVE` в пилоте) |
| `grade_group` | `enum, обязательно*` | Одна из групп: `1-4`, `5-8`, `9-11`. Если отсутствует, сервер вычисляет группу по `grade`; если переданы оба значения, они обязаны совпадать. | Вычисляется по `grade`, если группа не передана; иначе обязательна |
| `grade` | `integer или null, рекомендуется` | Точный класс: целое от 1 до 11. Более точная возрастная адаптация; должен входить в `grade_group`. | `null` — если точный класс не указан |
| `pupils_count` | `integer, обязательно` | Точное число учащихся. Для пилота 1–35. Категория размера определяется бэкендом; число не округляем. | Нет — обязательно |
| `duration_minutes` | `enum integer, обязательно` | Только `30`, `45`, `60`, `90`; полная длительность вместе с переходами и подведением итогов. | Нет — обязательно |
| `format` | `enum string, обязательно` | `class_hour` — классный час; `school_event` — общешкольное мероприятие; `interactive_lesson` — интерактивное занятие. | Нет — обязательно |
| `participants` | `object, необязательно` | Сведения об участниках. Можно прислать частично; сервер дополняет документированными значениями по умолчанию. | Объект `participants` из серверного конфига |
| `participants.teachers_count` | `integer ≥1, по умолчанию 1` | Точное число педагогов, реально доступных для проведения. | `1` |
| `participants.parents_enabled` | `boolean, по умолчанию false` | Можно ли задействовать родителей. При false мероприятие выполняется силами педагога и учеников. | `false` (`0`) |
| `participants.parents_count` | `integer, условно обязательно` | Точное количество: при `parents_enabled=true` должно быть ≥1, при false — 0 (либо поле отсутствует). Доступные группы вычисляются бэкендом: `1-2`, `3-5`, `6-10`, `11_plus`. | `0`, если родители не включены; при `true` обязательно передать ≥1 |
| `participants.parent_roles` | `array<enum>, условно обязательно` | Разрешённые способы привлечения: `helper`, `active_participant`, `audience`, `evaluator`. Комбинации допустимы; если родители включены и роли не указаны — `["audience"]` (см. ниже). | `[]`, если родители отключены; `["audience"]`, если включены, но поле пропущено |
| `participants.parent_roles[]` | `enum string` | `helper` — помощник; `active_participant` — активный участник; `audience` — зритель; `evaluator` — жюри/оценщик. Список разрешений, а не назначение каждого родителя. | Не применяется: элемент задаётся явно |
| `participants.parent_audience_engagement` | `enum, по умолчанию none` | `none` — только смотреть; `feedback` — обратная связь; `vote` — голосование; `audience_award` — приз зрительских симпатий. Отличное от `none` требует `audience` в `parent_roles`. | `"none"` |
| `participants.parent_notes` | `string/null, необязательно` | Дополнительные пожелания о задействовании родителей. Не рассматриваются как системные инструкции. | `null` |
| `resources` | `object, необязательно` | Доступная инфраструктура школы; при неполном заполнении неизвестное не означает автоматически доступное. | Объект `resources` из серверного конфига |
| `resources.projector` | `boolean/null, необязательно` | Наличие проектора: true — есть; false — нет; null/отсутствие — неизвестно. | `null` — неизвестно |
| `resources.printer` | `boolean/null, необязательно` | Наличие принтера. | `null` — неизвестно |
| `resources.internet` | `boolean/null, необязательно` | Есть ли интернет во время мероприятия. | `null` — неизвестно |
| `resources.audio` | `boolean/null, необязательно` | Есть ли устройство воспроизведения звука. | `null` — неизвестно |
| `resources.room` | `string/enum, необязательно` | Тип помещения, например `classroom`, `assembly_hall`, `gym`, `other`. | `null` — помещение не указано |
| `resources.available_materials` | `array<string>, необязательно` | Доступный реквизит/расходники, например `paper`, `markers`. Список конкретных доступных материалов. | `[]` — нет подтверждённых материалов |
| `resources.available_materials[]` | `string` | Идентификатор доступного материала/оборудования из справочника либо согласованное значение. | Не применяется: элемент задаётся явно |
| `resources.extra_notes` | `string/null, необязательно` | Ограничения пространства/оборудования в свободной форме. | `null` |
| `teacher_preferences` | `object, необязательно` | Пожелания педагога; влияют на сценарную механику, а не только стиль текста. | Объект `teacher_preferences` из серверного конфига |
| `teacher_preferences.style` | `enum, необязательно` | `classic`, `interactive`, `creative`, `research` — предпочитаемый стиль. Значение не тождественно `format`. | `"classic"` — классический стиль |
| `teacher_preferences.script_detail` | `enum, необязательно` | `brief`, `standard`, `detailed` — детализация реплик и инструкций. | `"standard"` — стандартная детализация |
| `teacher_preferences.difficulty` | `enum, необязательно` | `basic`, `standard`, `advanced` — сложность заданий с учётом возраста. | `"standard"` — стандартная сложность с поправкой на возраст |
| `teacher_preferences.interaction_level` | `enum, необязательно` | `low`, `medium`, `high` — интенсивность участия школьников. | `"low"` — минимальная интенсивность |
| `teacher_preferences.group_work` | `boolean, необязательно` | Нужно ли ориентироваться на работу в малых группах. | `false` (`0`) — работа в малых группах не требуется |
| `teacher_preferences.preparation_effort` | `enum, необязательно` | `minimal`, `standard`, `extended` — допустимые усилия педагога при подготовке. | `"minimal"` — минимальная подготовка |
| `teacher_preferences.notes` | `string/null, необязательно` | Свободное пожелание по методике и проведению. | `null` |
| `generation` | `object, необязательно` | Параметры генерации, передаваемые фронтендом. Не содержит внутренней конфигурации модели. | Объект `generation` из серверного конфига |
| `generation.variants_count` | `integer 1–3, по умолчанию 1` | Сколько полноценных различающихся сценариев необходимо получить. | `1` |
| `generation.language` | `string enum, по умолчанию ru` | Язык содержательной генерации, для пилота `ru`. | `"ru"` |


## 3. Валидация, значения по умолчанию и исключения

### 3.1. Серверный профиль значений по умолчанию V1

Если необязательное поле **отсутствует** в запросе, сервер подставляет значение из `config/request_defaults.json` **до сборки промпта**. Это настройки сервера, фронтенду отправлять их необязательно. Вложенные объекты дополняются **по каждому полю отдельно**: наличие `teacher_preferences` не отключает остальные дефолты. Если поле явно передано, его допустимое значение имеет приоритет над дефолтом.

```json
{
  "participants": {
    "teachers_count": 1,
    "parents_enabled": false,
    "parents_count": 0,
    "parent_roles": [],
    "parent_audience_engagement": "none",
    "parent_notes": null
  },
  "resources": {
    "projector": null,
    "printer": null,
    "internet": null,
    "audio": null,
    "room": null,
    "available_materials": [],
    "extra_notes": null
  },
  "teacher_preferences": {
    "style": "classic",
    "script_detail": "standard",
    "difficulty": "standard",
    "interaction_level": "low",
    "group_work": false,
    "preparation_effort": "minimal",
    "notes": null
  },
  "generation": {
    "variants_count": 1,
    "language": "ru"
  }
}
```

Для `parents_enabled=true` действует отдельное правило: точное `parents_count` обязательно, а пропущенные `parent_roles` становятся `["audience"]`. Число родителей нельзя автоматически подменять нулём в этом случае. Для `parents_enabled=false` эффективные значения: `parents_count=0`, `parent_roles=[]`, `parent_audience_engagement="none"`.

`false` — **логический тип JSON**; цифра `0` здесь только поясняет выключенное состояние, но не является допустимым JSON-значением для boolean. Аналогично `true` — включено. Явное `null` разрешено только у полей, тип которых включает `null` (например, оборудование/примечания/точный класс). Для других полей `null` не заменяет отсутствие поля и отклоняется валидатором.

При `resources.projector/printer/internet/audio=null` сервер считает наличие техники **неподтверждённым** и не требует её обязательно в сценарии. Пустой `available_materials=[]` означает отсутствие заявленного списка, а не доказанное отсутствие всех материалов.

При `teacher_preferences.interaction_level="low"` приоритет — объяснение, обсуждение и короткие индивидуальные действия. `group_work=false` означает, что система **не должна планировать обязательную работу в малых группах**: допустимы фронтальная работа, индивидуальные ответы и необязательные парные задания. Если явно пришло `group_work=true` или другой `interaction_level`, действуют переданные значения. Дефолты `style="classic"`, `script_detail="standard"`, `difficulty="standard"` и `preparation_effort="minimal"` — **предлагаемые базовые настройки первой версии**, их можно корректировать централизованно в конфиге.

Для воспроизводимости логов сохранять и **исходный** JSON, и **нормализованный** JSON с применёнными дефолтами, а также версию/хеш файла конфигурации. В ответе API поле `input` содержит эффективные значения.

### 3.2. Правила проверки

- `event_id` берётся из `GET /api/v1/catalog/events`, остальные допустимые перечисления — из `GET /api/v1/catalog/options`.
- При отсутствии `participants` используется `teachers_count=1`, `parents_enabled=false`, `parents_count=0`, `parent_roles=[]`, `parent_audience_engagement="none"`.
- Если родители включены, `parents_count` обязателен и положителен; без `parent_roles` используется `["audience"]`.
- Если родители отключены, запрещены ненулевое число родителей, ненулевые роли и зрительское вовлечение.
- Если выбрано `feedback`, `vote` или `audience_award`, в `parent_roles` должна присутствовать роль `audience`.
- Точное число родителей **не** заменяется диапазоном: диапазон добавляет только сам бэкенд для выбора шаблонов.
- Родительские роли — **разрешённые режимы**. Например, `["helper", "audience"]` не означает, что каждый из 12 одновременно помощник и зритель; точное распределение создаётся далее в сценарии.
- Поля не должны содержать имена, контакты и информацию о здоровье конкретных детей: для адаптации достаточно обезличенных условий класса.
- `ACTIVE_MODEL`, API-ключи, адрес сервера модели, temperature, системные промпты и версии промптов **не отправляются фронтендом**; это конфигурация LLM-бэкенда.

## 4. Что возвращает сервер сразу после POST

`POST /api/v1/generations` работает асинхронно и обычно возвращает **HTTP 202 Accepted**, а не готовые сценарии:

```json
{
  "job_id": "job_20261017_a001",
  "project_id": "evt_20261017_0001",
  "status": "queued",
  "requested_variants": 3,
  "completed_variants": 0,
  "status_url": "/api/v1/generations/job_20261017_a001",
  "project_url": "/api/v1/projects/evt_20261017_0001"
}
```

| Поле | Значение |
|---|---|
| `job_id` | Идентификатор фоновой задачи генерации. |
| `project_id` | Идентификатор проекта мероприятия, который потом получит варианты. |
| `status` | `queued`: задача поставлена в очередь. |
| `requested_variants` | Сколько вариантов запросил пользователь. |
| `completed_variants` | Сколько вариантов уже готовы; при постановке в очередь `0`. |
| `status_url` | Относительный маршрут для опроса статуса. |
| `project_url` | Относительный маршрут для получения самого проекта. |

## 5. Пример запроса без родителей

```json
{
  "event_id": "knowledge_day",
  "region_id": "RU-SVE",
  "grade_group": "1-4",
  "grade": 3,
  "pupils_count": 18,
  "duration_minutes": 30,
  "format": "class_hour",
  "participants": {
    "teachers_count": 1,
    "parents_enabled": false,
    "parents_count": 0,
    "parent_roles": [],
    "parent_audience_engagement": "none"
  },
  "generation": {"variants_count": 1, "language": "ru"}
}
```

Этот запрос тоже полноценный: остальные необязательные поля добираются из согласованных настроек сервера.

## 6. Минимальный запрос: сервер самостоятельно применяет V1-дефолты

```json
{
  "event_id": "knowledge_day",
  "region_id": "RU-SVE",
  "grade_group": "5-8",
  "pupils_count": 25,
  "duration_minutes": 45,
  "format": "class_hour"
}
```

Эффективные предпочтения педагога: `style="classic"`, `script_detail="standard"`, `difficulty="standard"`, `interaction_level="low"`, `group_work=false`, `preparation_effort="minimal"`, `notes=null`. Участники: один педагог, без родителей. Генерация: один вариант на русском. Неизвестные ресурсы остаются `null`, не превращаются в `true`.
