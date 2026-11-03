# Контракт 03 — JSON-ответ модели LLM (v1.5, `schema_version` 1.2)

**Источник:** выбранная модель через Model Router (локальная Qwen3.5-9B, другая Qwen, GigaChat или GPT-6 Luna). **Получатель:** внутренний генерационный конвейер сервиса `services/school_events_llm`, **не** фронтенд и **не** общий бэкенд. Первый JSON — логически объединённый результат одного варианта (`variant_package`); фактические вызовы модели разделяются на этапы и показаны ниже.

> **Изменения v1.5 (только этот внутренний контракт; контракты 01/02 с фронтендом не менялись):**
> - `schema_version` 1.1 → **1.2**;
> - `concept.values_to_mechanics` — реализация ценностей события (ТЗ 2.5, 16.6);
> - `pupil_grouping` — структурное деление учащихся (ТЗ 12.3);
> - `fact_claims` — реестр фактических утверждений с привязкой к проверенным фрагментам (ТЗ 17.6);
> - `materials[].family_task` — флаг необязательного задания семье (ТЗ 2.7);
> - расширенная схема `variation_plan` (ТЗ 9.3) с закрытым перечнем `activity_type`;
> - добавлены примеры этапов `scenario_plan` и `quality_review`.
>
> Все новые поля — **внутренние**: при сборке ответа фронтенду (контракт 02) они удаляются или выводятся в существующие поля по шаблону ТЗ 14.6.

## 1. Полный пример JSON

```json
{
  "schema_version": "1.2",
  "task": "variant_package",
  "variant": {
    "variant_id": "v1",
    "title": "Наш класс: новые цели",
    "concept": {
      "summary": "Класс формулирует общие цели нового учебного года и конкретные первые шаги.",
      "goal": "Согласовать цели и правила сотрудничества на учебный год.",
      "tasks": [
        "Определить общие приоритеты",
        "Научиться аргументировать предложения"
      ],
      "expected_outcomes": [
        "Плакат с согласованными целями класса"
      ],
      "values_to_mechanics": [
        {
          "value_id": "mutual_aid",
          "mechanic_type": "team_task",
          "mechanic": "Группы вместе формулируют цели: каждый участник отвечает за свою часть предложения, команда собирает общий результат.",
          "block_ids": ["block_03"]
        },
        {
          "value_id": "citizenship",
          "mechanic_type": "real_problem_solving",
          "mechanic": "Класс выбирает реальные цели жизни класса и первый шаг, который выполнит сам в течение месяца.",
          "block_ids": ["block_02", "block_04"]
        }
      ]
    },
    "pupil_grouping": {
      "total_pupils": 27,
      "mode": "small_groups",
      "group_sizes": [6, 6, 5, 5, 5],
      "block_ids": ["block_03"]
    },
    "roles": [
      {
        "role_id": "teacher_1",
        "participant_type": "teacher",
        "title": "Ведущий педагог",
        "count": 1,
        "block_ids": [
          "block_01",
          "block_02",
          "block_03",
          "block_04"
        ]
      },
      {
        "role_id": "pupils_all",
        "participant_type": "pupils_group",
        "title": "Учащиеся (5 групп: 6, 6, 5, 5, 5)",
        "count": 27,
        "block_ids": [
          "block_01",
          "block_02",
          "block_03",
          "block_04"
        ]
      },
      {
        "role_id": "parent_helpers",
        "participant_type": "parent",
        "role_mode": "helper",
        "title": "Помощники с карточками",
        "count": 2,
        "block_ids": [
          "block_03"
        ]
      },
      {
        "role_id": "parent_audience",
        "participant_type": "parent",
        "role_mode": "audience",
        "title": "Зрители и голосующие",
        "count": 10,
        "block_ids": [
          "block_01",
          "block_02",
          "block_03",
          "block_04"
        ]
      }
    ],
    "timeline": [
      {
        "block_id": "block_01",
        "start_minute": 0,
        "duration_minutes": 5,
        "title": "Открытие и настрой",
        "purpose": "Обозначить смысл встречи",
        "teacher_script": "Поприветствуйте класс, объясните цель встречи и задайте вопрос: чего мы хотим добиться вместе?",
        "pupil_actions": [
          "Высказывают ожидания по желанию."
        ],
        "role_ids": [
          "teacher_1",
          "pupils_all",
          "parent_audience"
        ],
        "material_ids": []
      },
      {
        "block_id": "block_02",
        "start_minute": 5,
        "duration_minutes": 10,
        "title": "Круг идей",
        "purpose": "Собрать идеи класса",
        "teacher_script": "Предложите назвать две идеи для улучшения жизни класса и запишите их на доске.",
        "pupil_actions": [
          "Предлагают и группируют идеи."
        ],
        "role_ids": [
          "teacher_1",
          "pupils_all",
          "parent_audience"
        ],
        "material_ids": []
      },
      {
        "block_id": "block_03",
        "start_minute": 15,
        "duration_minutes": 20,
        "title": "Командная мастерская",
        "purpose": "Подготовить реалистичные предложения",
        "teacher_script": "Разделите 27 учеников на 5 групп (6, 6, 5, 5, 5). Раздайте карточки. Попросите записать две цели и по одному первому шагу.",
        "pupil_actions": [
          "Обсуждают цели в группах и готовят краткие представления."
        ],
        "role_ids": [
          "teacher_1",
          "pupils_all",
          "parent_audience",
          "parent_helpers"
        ],
        "material_ids": [
          "card_goals",
          "parent_instruction_01"
        ]
      },
      {
        "block_id": "block_04",
        "start_minute": 35,
        "duration_minutes": 10,
        "title": "Выступления и выбор зрителей",
        "purpose": "Обобщить решения и завершить работу",
        "teacher_script": "Дайте командам кратко представить результаты. Предложите зрителям проголосовать по критерию понятности предложения. Объявите символическую награду и общий итог.",
        "pupil_actions": [
          "Представляют планы и фиксируют общее решение."
        ],
        "role_ids": [
          "teacher_1",
          "pupils_all",
          "parent_audience"
        ],
        "material_ids": [
          "audience_ballot_01"
        ]
      }
    ],
    "materials": [
      {
        "material_id": "card_goals",
        "type": "activity_card",
        "title": "Цели на год",
        "used_in_blocks": [
          "block_03"
        ],
        "audience": "pupils_group",
        "content": "Сформулируйте две достижимые цели класса. Для каждой предложите один первый шаг.",
        "teacher_notes": "Для 27 учеников подготовьте 5 комплектов, по одному каждой группе.",
        "print_required": true,
        "dependencies": [
          "paper",
          "markers",
          "printer"
        ],
        "estimated_preparation_minutes": 5
      },
      {
        "material_id": "parent_instruction_01",
        "type": "parent_instruction",
        "title": "Памятка родителям-помощникам",
        "used_in_blocks": [
          "block_03"
        ],
        "audience": "parent",
        "content": "Помогите выдать пять комплектов карточек. Не выполняйте задания за школьников.",
        "teacher_notes": "Заранее расскажите двум добровольным помощникам их задачи.",
        "print_required": false,
        "dependencies": [],
        "estimated_preparation_minutes": 2
      },
      {
        "material_id": "audience_ballot_01",
        "type": "audience_ballot",
        "title": "Бюллетень зрительских симпатий",
        "used_in_blocks": [
          "block_04"
        ],
        "audience": "parent",
        "content": "Отметьте одну команду по критерию: Понятность сформулированного командного плана. Один голос на одного зрителя.",
        "teacher_notes": "Запланировано 10 зрителей; считать только фактически поданные голоса, при ничьей отметить обе команды.",
        "print_required": true,
        "dependencies": [
          "paper",
          "printer"
        ],
        "estimated_preparation_minutes": 3
      }
    ],
    "parent_participation_plan": {
      "enabled": true,
      "parents_count": 12,
      "parent_size_group": "11_plus",
      "selected_roles": [
        "helper",
        "audience"
      ],
      "audience_engagement": "audience_award",
      "assignments": [
        {
          "role_id": "parent_helpers",
          "participant_type": "parent",
          "role_mode": "helper",
          "count": 2,
          "block_ids": [
            "block_03"
          ]
        },
        {
          "role_id": "parent_audience",
          "participant_type": "parent",
          "role_mode": "audience",
          "count": 10,
          "block_ids": [
            "block_01",
            "block_02",
            "block_03",
            "block_04"
          ]
        }
      ],
      "voting": {
        "enabled": true,
        "award_title": "Приз зрительских симпатий",
        "voters_count_planned": 10,
        "criterion": "Понятность сформулированного командного плана",
        "method": "paper_ballot",
        "votes_per_person": 1,
        "tie_rule": "В случае равенства голосов отмечаются обе команды",
        "block_id": "block_04",
        "material_ids": [
          "audience_ballot_01"
        ]
      },
      "teacher_fallback": "Если родители не пришли, педагог проводит те же задания с учениками, а зрительский приз заменяется общей рефлексией без голосования."
    },
    "teacher_instructions": [
      "Заранее распечатать карточки и бланки голосования.",
      "Подготовить пять рабочих групп численностью 6, 6, 5, 5, 5.",
      "Объяснить добровольный характер участия родителей и критерии зрительского голосования.",
      "При отсутствии родителей применить запасной план без голосования."
    ],
    "fact_claims": [],
    "sources": []
  }
}
```

В примере `group_work=true` (вход как в `01_FRONTEND_REQUEST`), поэтому `pupil_grouping.mode="small_groups"` допустим. Размеры `group_sizes` рассчитывает Python (`role_service`), модель их не пересчитывает. Ценности `mutual_aid` и `citizenship` пришли из каталога события `knowledge_day`, модель их не выбирает. `fact_claims` пуст: сценарий не содержит исторических или культурных фактов.

## 2. Описание каждого поля

| Поле | Тип | Обязательность / смысл |
|---|---|---|
| `schema_version` | `string` | Версия **контракта структурированных данных LLM**, отдельная от API-версии фронтенда. |
| `task` | `enum string` | Название операции. `variant_package` — логическое представление полностью сформированного одного варианта. В реальном конвейере отдельные вызовы выполняют `variation_plan`, `scenario_plan`, `scenario_block`, `materials`. |
| `variant` | `object` | Только содержательная часть **одного** сценария. Нет `job_id`, `status`, `quality_report`, `tokens`, `model_key` и HTTP-метаданных. |
| `variant.variant_id` | `string` | Уникальный ID варианта в проекте, например `v1`. |
| `variant.title` | `string` | Человеко-читаемое название сценария. |
| `variant.concept` | `object` | Педагогическая концепция сценария. |
| `variant.concept.summary` | `string` | Краткое описание основной сценарной идеи. |
| `variant.concept.goal` | `string` | Основная педагогическая цель. |
| `variant.concept.tasks` | `array<string>` | Действия/задачи, которые ведут к достижению цели. |
| `variant.concept.tasks[]` | `string` | Одна задача. |
| `variant.concept.expected_outcomes` | `array<string>` | Конкретные ожидаемые результаты мероприятия. |
| `variant.concept.expected_outcomes[]` | `string` | Один ожидаемый результат. |
| `variant.concept.values_to_mechanics` | `array<object>`, **v1.5, обязательно** | По записи на каждую ценность из нормализованного запроса (ценности события из каталога). Не выводится во фронтенд как есть: рендерится в `concept.tasks` ответа 02. |
| `variant.concept.values_to_mechanics[].value_id` | `enum` | `family`, `mutual_aid`, `historical_memory`, `labour_creation`, `cultural_diversity`, `citizenship` — только ценности, переданные в промпте. |
| `variant.concept.values_to_mechanics[].mechanic_type` | `enum` | `family_research`, `team_task`, `source_work`, `joint_product`, `culture_comparison`, `real_problem_solving`, `class_collective_task`, `pair_task`, `discussion` — тип механики; используется в проверке разнообразия. |
| `variant.concept.values_to_mechanics[].mechanic` | `string` | Как именно ценность реализуется действием участников (1–2 предложения), не лозунг. |
| `variant.concept.values_to_mechanics[].block_ids` | `array<string>` | Существующие `timeline[].block_id`, где механика реализуется; минимум один. |
| `variant.pupil_grouping` | `object`, **v1.5, обязательно** | Организация учащихся. Во фронтенд выводится текстом в `roles[].title`, `teacher_script`, `teacher_instructions`. |
| `variant.pupil_grouping.total_pupils` | `integer` | Равно `pupils_count` запроса. |
| `variant.pupil_grouping.mode` | `enum` | `whole_class`, `pairs`, `small_groups`, `mixed`. `small_groups` как обязательная форма недопустим при `group_work=false`. |
| `variant.pupil_grouping.group_sizes` | `array<integer>` | Размеры групп; сумма равна `total_pupils`. Для `whole_class` — `[pupils_count]`. Значения рассчитывает Python. |
| `variant.pupil_grouping.block_ids` | `array<string>` | Блоки, где действует деление. |
| `variant.fact_claims` | `array<object>`, **v1.5, обязательно (может быть пустым)** | Каждое фактическое утверждение сценария и материалов (даты, события, имена, цитаты, сведения о культуре). |
| `variant.fact_claims[].claim_id` | `string` | Уникальный ID в пределах варианта. |
| `variant.fact_claims[].text` | `string` | Утверждение так, как оно сформулировано в сценарии. |
| `variant.fact_claims[].location` | `string` | Где находится: `timeline.<block_id>.teacher_script`, `materials.<material_id>.content` и т. п. |
| `variant.fact_claims[].source_id` | `string/null` | `source_id` из переданного фрагмента; `null` допускается только вместе с `needs_teacher_check=true`. |
| `variant.fact_claims[].fragment_id` | `string/null` | `fragment_id` переданного фрагмента. |
| `variant.fact_claims[].needs_teacher_check` | `boolean`, по умолчанию `false` | `true`, если модель не смогла привязать утверждение к фрагменту; такой вариант не может получить `passed`. |
| `variant.materials[].family_task` | `boolean`, **v1.5, необязательно** | `true` — необязательное задание семье до события (только при ценности `family`). Тип материала — `handout`. В ответ 02 не передаётся. |
| `variant.roles` | `array<object>` | Список участников-исполнителей и их функций в сценарии. |
| `variant.roles[].role_id` | `string` | Уникальный ID роли, на него ссылаются тайминг и план родителей. |
| `variant.roles[].participant_type` | `enum` | Тип: `teacher`, `pupil`, `pupils_group`, `parent`, `guest`. |
| `variant.roles[].role_mode` | `enum, условное` | Режим родительской роли (`helper`/`active_participant`/`audience`/`evaluator`). Для педагогов и детей отсутствует. |
| `variant.roles[].title` | `string` | Понятное название роли. |
| `variant.roles[].count` | `integer ≥1` | Число людей, выполняющих роль (нельзя превышать доступную численность в один момент). |
| `variant.roles[].block_ids` | `array<string>` | Какие блоки связываются с ролью. |
| `variant.roles[].block_ids[]` | `string` | ID блока из `timeline[].block_id`. |
| `variant.timeline` | `array<object>` | Временная сетка мероприятия, сумма длительностей строго равна заявленным минутам. |
| `variant.timeline[].block_id` | `string` | Уникальный ID блока в пределах варианта. |
| `variant.timeline[].start_minute` | `integer ≥0` | Минута начала относительно старта мероприятия. Первый блок начинается с 0. |
| `variant.timeline[].duration_minutes` | `integer >0` | Длительность блока; блоки не пересекаются и не создают пробелов. |
| `variant.timeline[].title` | `string` | Название блока. |
| `variant.timeline[].purpose` | `string` | Для чего нужен блок. |
| `variant.timeline[].teacher_script` | `string` | Текст ведущего и исполнимые инструкции педагогу (в финальном результате — подробный, не условная заглушка). |
| `variant.timeline[].pupil_actions` | `array<string>` | Что непосредственно делают школьники. |
| `variant.timeline[].pupil_actions[]` | `string` | Одно действие учащихся. |
| `variant.timeline[].role_ids` | `array<string>` | Роли, задействованные в блоке. |
| `variant.timeline[].role_ids[]` | `string` | Существующий `roles[].role_id`. |
| `variant.timeline[].material_ids` | `array<string>` | Материалы, используемые в блоке. |
| `variant.timeline[].material_ids[]` | `string` | Существующий `materials[].material_id`. |
| `variant.materials` | `array<object>` | Все материалы, необходимые для выполнения сценария. |
| `variant.materials[].material_id` | `string` | Уникальный ID материала в пределах варианта. |
| `variant.materials[].type` | `enum` | `teacher_instruction`, `worksheet`, `activity_card`, `slide_outline`, `quiz`, `discussion_questions`, `handout`, `props_checklist`, `parent_instruction`, `audience_ballot`, `jury_scorecard`, `award_instruction`. |
| `variant.materials[].title` | `string` | Название материала. |
| `variant.materials[].used_in_blocks` | `array<string>` | В каких блоках применяется. |
| `variant.materials[].used_in_blocks[]` | `string` | Существующий `timeline[].block_id`. |
| `variant.materials[].audience` | `string/enum` | Для кого материал предназначен: педагог, ученик, группа, родитель и др. |
| `variant.materials[].content` | `string` | Полный текст материала или структурированное содержимое по типу материала. |
| `variant.materials[].teacher_notes` | `string` | Пояснения педагогу по использованию материала. |
| `variant.materials[].print_required` | `boolean` | Обязательна ли печать (если true — доступный принтер должен быть предусмотрен либо дана альтернатива). |
| `variant.materials[].dependencies` | `array<string>` | Необходимый реквизит/оборудование. |
| `variant.materials[].dependencies[]` | `string` | Название зависимости, должно согласовываться с `resources`. |
| `variant.materials[].estimated_preparation_minutes` | `integer ≥0, предложено` | Ориентировочное время подготовки материала. Не часть продолжительности самого события. |
| `variant.parent_participation_plan` | `object, условное` | Обязателен у готового варианта с родителями; при их отсутствии — можно опустить либо вернуть `enabled=false` без назначений. |
| `variant.parent_participation_plan.enabled` | `boolean` | Включено ли участие родителей. |
| `variant.parent_participation_plan.parents_count` | `integer` | Точное исходное число родителей. |
| `variant.parent_participation_plan.parent_size_group` | `enum` | Вычисленная категория `none`, `1-2`, `3-5`, `6-10`, `11_plus`. |
| `variant.parent_participation_plan.selected_roles` | `array<enum>` | Роли, разрешённые пользователем и применяемые в плане. |
| `variant.parent_participation_plan.selected_roles[]` | `string` | Одна родительская роль. |
| `variant.parent_participation_plan.audience_engagement` | `enum` | Режим вовлечения зрителей из входа. |
| `variant.parent_participation_plan.assignments` | `array<object>` | Назначения по блокам; нельзя назначить 12 помощников плюс 12 зрителей одновременно при наличии 12 родителей. |
| `variant.parent_participation_plan.assignments[].role_id` | `string` | Ссылка на существующую родительскую роль. |
| `variant.parent_participation_plan.assignments[].participant_type` | `enum` | Здесь `parent`. |
| `variant.parent_participation_plan.assignments[].role_mode` | `enum` | Здесь одна из разрешённых `parent_roles`. |
| `variant.parent_participation_plan.assignments[].count` | `integer ≥1` | Количество родителей в назначении. |
| `variant.parent_participation_plan.assignments[].block_ids` | `array<string>` | В какие блоки назначены родители. |
| `variant.parent_participation_plan.assignments[].block_ids[]` | `string` | Существующий ID блока. |
| `variant.parent_participation_plan.voting` | `object/null, условное` | Регламент зрительского голосования. Если голосования нет, null или отсутствует. |
| `variant.parent_participation_plan.voting.enabled` | `boolean` | Включён ли режим голосования. |
| `variant.parent_participation_plan.voting.award_title` | `string/null` | Название символической награды при режиме `audience_award`. |
| `variant.parent_participation_plan.voting.voters_count_planned` | `integer ≥0` | Запланированное число зрителей-избирателей, а **не** число фактически проголосовавших. |
| `variant.parent_participation_plan.voting.criterion` | `string` | Понятный и объявленный заранее критерий голосования. |
| `variant.parent_participation_plan.voting.method` | `enum/string` | Форма голосования, например `paper_ballot`. |
| `variant.parent_participation_plan.voting.votes_per_person` | `integer ≥1` | Сколько голосов может подать один зритель. |
| `variant.parent_participation_plan.voting.tie_rule` | `string` | Что делать при равенстве голосов. |
| `variant.parent_participation_plan.voting.block_id` | `string` | ID блока для зрительского голосования. |
| `variant.parent_participation_plan.voting.material_ids` | `array<string>` | Ссылки на бланки/инструкции голосования. |
| `variant.parent_participation_plan.voting.material_ids[]` | `string` | Существующий `materials[].material_id`. |
| `variant.parent_participation_plan.teacher_fallback` | `string` | Как провести сценарий силами педагога и школьников, если родители не пришли. |
| `variant.teacher_instructions` | `array<string>` | Чек-лист подготовки и указания организатору. |
| `variant.teacher_instructions[]` | `string` | Одно действие по подготовке или проведению. |
| `variant.sources` | `array<object>` | Верифицированные источники, использованные для утверждений (здесь пусто, потому что исторические факты не используются). **v1.5:** модель может только перечислить `source_id` из `fact_claims`; поля `title`, `publisher`, `url` сервис подставляет из корпуса, а не из ответа модели. |
| `variant.sources[]` | `object, при наличии` | `{source_id, title, publisher, url}`; источник без утверждений в `fact_claims` удаляется. |
| `variant.roles[]` | `object` | Одно описание роли/категории участников. |
| `variant.timeline[]` | `object` | Один блок тайминга мероприятия. |
| `variant.materials[]` | `object` | Один материал: карточка, бланк, инструкция и т. п. |
| `variant.parent_participation_plan.assignments[]` | `object` | Одно назначение родителей на конкретные блоки сценария. |


## 3. Важное разделение: ответ LLM и ответ бэкенда

- **Модель генерирует содержимое** (`concept`, роли, тексты, задания и материалы). Она не назначает окончательный статус качества и не создаёт ID фоновой задачи.
- **Значения по умолчанию применяет бэкенд до обращения к LLM.** В частности, при отсутствии предпочтений педагога в промпте передаются `interaction_level="low"` и `group_work=false`; модель **не** выбирает их самостоятельно. Все остальные необязательные параметры нормализуются по `config/request_defaults.json`. В ответе модели эти параметры не нужно дублировать, если они не предусмотрены конкретной схемой этапа.
- **[v1.5] Ценности, воспитательные задачи и профиль школы** сервис берёт из каталога и конфигурации и передаёт модели в промпте. Модель не выбирает и не добавляет ценности, а только описывает, как реализует переданные.
- **Backend добавляет технику:** проверяет схему, нормализует тайминги, распределение участников, источники и ресурсы; запускает проверки, сохраняет версии, ошибки и прогресс.
- **[v1.5] Сборка ответа фронтенду:** из `variant_package` функция `render_frontend_variant()` строит вариант контракта 02 по белому списку полей и шаблону ТЗ 14.6; внутренние поля этого контракта в ответ 02 не попадают.
- Для прототипа на Qwen3.5-9B **не отправляем один огромный запрос с ожиданием полного `variant_package`**. Это логическая объединённая форма содержательного результата, которую бэкенд собирает из промежуточных JSON нескольких вызовов.
- При `variants_count=3` вначале генерируются три разные концепции, затем каждый вариант детализируется отдельно. Сама LLM не должна самовольно менять количество вариантов, класс, численность или разрешённые роли родителей.
- Дата проверки `quality_report.checked_at` и статус `passed` возникают **после** генерации в валидаторе, не в сыром модельном ответе.

## 4. Фактические JSON-ответы отдельных вызовов модели

### 4.1. Этап `variation_plan` — сразу 1–3 концепции

**v1.5:** схема расширена до требований ТЗ 9.3, чтобы программная проверка разнообразия (ТЗ 9.4) работала по структурным полям, а не по тексту. Ниже — первая из трёх концепций; остальные две имеют ту же структуру.

```json
{
  "schema_version": "1.2",
  "task": "variation_plan",
  "concepts": [
    {
      "variant_id": "v1",
      "title": "Наш класс: новые цели",
      "summary": "Класс формулирует общие цели нового учебного года и конкретные первые шаги.",
      "narrative_approach": "Разговор о прошедшем лете переходит в совместное планирование года.",
      "primary_mechanic": "collaborative_planning",
      "engagement_mode": "small_groups",
      "planned_structure": [
        {"order": 1, "title": "Открытие и настрой", "activity_type": "discussion", "approx_minutes": 5},
        {"order": 2, "title": "Круг идей", "activity_type": "discussion", "approx_minutes": 10},
        {"order": 3, "title": "Командная мастерская", "activity_type": "team_task", "approx_minutes": 20},
        {"order": 4, "title": "Выступления и выбор зрителей", "activity_type": "voting", "approx_minutes": 10}
      ],
      "key_activities": [
        {"activity_type": "team_task", "description": "Группы формулируют две цели и первый шаг"},
        {"activity_type": "voting", "description": "Зрители выбирают самый понятный план"}
      ],
      "distinctive_result": "Плакат с согласованными целями класса",
      "differs_from": [
        {"variant_id": "v2", "difference": "Нет игрового маршрута: результат — общий план, а не прохождение испытаний"},
        {"variant_id": "v3", "difference": "Цели касаются жизни класса, а не проектов улучшения школы"}
      ],
      "values_to_mechanics": [
        {"value_id": "mutual_aid", "mechanic_type": "team_task", "mechanic": "Общая формулировка целей в группе"},
        {"value_id": "citizenship", "mechanic_type": "real_problem_solving", "mechanic": "Реальный первый шаг класса на месяц"}
      ]
    }
  ]
}
```

| Поле | Описание |
|---|---|
| `schema_version` | Версия схемы промежуточного результата (`1.2`). |
| `task` | Идентификатор этапа — здесь `variation_plan`. |
| `concepts` | Массив концепций; длина в пределах 1–3 и равна запросу фронтенда. |
| `concepts[].variant_id` | Уникальный код будущего варианта (= `concept_id` ТЗ 9.3). |
| `concepts[].title` | Название концепции; уникально в пределах проекта. |
| `concepts[].summary` | Краткое содержание. |
| `concepts[].narrative_approach` | **v1.5.** Сюжетный ход: с чего начинается и куда ведёт событие. |
| `concepts[].primary_mechanic` | Основной сценарный подход, **v1.5:** из перечня `collaborative_planning`, `team_game`, `quest_route`, `mini_project`, `source_research`, `creative_workshop`, `performance`, `discussion_club`, `quiz_competition`, `interview_research`. |
| `concepts[].engagement_mode` | **v1.5.** `whole_class`, `pairs`, `small_groups`, `mixed`; при `group_work=false` — без обязательного `small_groups`. |
| `concepts[].planned_structure[]` | **v1.5.** Черновая структура блоков: `order`, `title`, `activity_type`, `approx_minutes` (ориентир; точную сетку рассчитывает Python). |
| `concepts[].key_activities[]` | **v1.5.** 2–4 ключевые активности: `activity_type` + `description`. |
| `activity_type` | **v1.5, закрытый перечень:** `discussion`, `team_task`, `pair_task`, `individual_task`, `game`, `quiz`, `source_work`, `creative_product`, `performance`, `project_pitch`, `research`, `reflection`, `voting`. |
| `concepts[].distinctive_result` | Чем результат этого подхода отличается от других. |
| `concepts[].differs_from[]` | **v1.5.** Отличия от каждой другой концепции: `variant_id` + `difference`. Пустой массив при `variants_count=1`. |
| `concepts[].values_to_mechanics[]` | **v1.5.** Предварительная реализация ценностей (без `block_ids` — блоков ещё нет). |

**Программные проверки этапа (ТЗ 9.4):** уникальность `variant_id` и `title`; у всех концепций не совпадает одновременно `primary_mechanic` и множество `activity_type`; длина `differs_from` равна `variants_count − 1`; каждая ценность из промпта есть в `values_to_mechanics`; при `group_work=false` нет `engagement_mode="small_groups"`.

### 4.2. Этап `scenario_block` — одна подробно проработанная часть сценария

```json
{
  "schema_version": "1.2",
  "task": "scenario_block",
  "variant_id": "v1",
  "block": {
    "block_id": "block_03",
    "start_minute": 15,
    "duration_minutes": 20,
    "title": "Командная мастерская",
    "purpose": "Подготовить реалистичные предложения",
    "teacher_script": "Разделите 27 учеников на 5 групп (6, 6, 5, 5, 5). Раздайте карточки. Попросите записать две цели и по одному первому шагу.",
    "pupil_actions": [
      "Обсуждают цели в группах и готовят краткие представления."
    ],
    "role_ids": [
      "teacher_1",
      "pupils_all",
      "parent_audience",
      "parent_helpers"
    ],
    "material_ids": [
      "card_goals",
      "parent_instruction_01"
    ]
  }
}
```

| Поле | Описание |
|---|---|
| `schema_version` | Версия формата ответа. |
| `task` | `scenario_block`. |
| `variant_id` | Какому варианту принадлежит блок. |
| `block` | Один законченный блок с полями, аналогичными `variant.timeline[]` из основного примера. |
| `block.block_id` | ID блока. |
| `block.start_minute` | Минута начала. |
| `block.duration_minutes` | Число минут. |
| `block.title` | Название блока. |
| `block.purpose` | Цель блока. |
| `block.teacher_script` | Текст ведущего, инструкции. |
| `block.pupil_actions` | Действия учеников (массив строк). |
| `block.role_ids` | Ссылки на роли сценария. |
| `block.material_ids` | Ссылки на создаваемые материалы. |

**v1.5:** `start_minute` и `duration_minutes` блока задаёт сервис (из нормализованной сетки этапа `scenario_plan`) и передаёт в промпт; модель обязана вернуть их без изменений, а при расхождении сервис использует свои значения и пишет предупреждение в журнал. Если в блоке есть фактические утверждения, модель возвращает их в поле `fact_claims` ответа этапа (та же структура, что в разделе 2), а сервис объединяет их в `variant.fact_claims`.

### 4.3. Этап `materials` — материалы варианта

```json
{
  "schema_version": "1.2",
  "task": "materials",
  "variant_id": "v1",
  "materials": [
    {
      "material_id": "card_goals",
      "type": "activity_card",
      "title": "Цели на год",
      "used_in_blocks": [
        "block_03"
      ],
      "audience": "pupils_group",
      "content": "Сформулируйте две достижимые цели класса. Для каждой предложите один первый шаг.",
      "teacher_notes": "Для 27 учеников подготовьте 5 комплектов, по одному каждой группе.",
      "print_required": true,
      "dependencies": [
        "paper",
        "markers",
        "printer"
      ],
      "estimated_preparation_minutes": 5
    },
    {
      "material_id": "parent_instruction_01",
      "type": "parent_instruction",
      "title": "Памятка родителям-помощникам",
      "used_in_blocks": [
        "block_03"
      ],
      "audience": "parent",
      "content": "Помогите выдать пять комплектов карточек. Не выполняйте задания за школьников.",
      "teacher_notes": "Заранее расскажите двум добровольным помощникам их задачи.",
      "print_required": false,
      "dependencies": [],
      "estimated_preparation_minutes": 2
    },
    {
      "material_id": "audience_ballot_01",
      "type": "audience_ballot",
      "title": "Бюллетень зрительских симпатий",
      "used_in_blocks": [
        "block_04"
      ],
      "audience": "parent",
      "content": "Отметьте одну команду по критерию: Понятность сформулированного командного плана. Один голос на одного зрителя.",
      "teacher_notes": "Запланировано 10 зрителей; считать только фактически поданные голоса, при ничьей отметить обе команды.",
      "print_required": true,
      "dependencies": [
        "paper",
        "printer"
      ],
      "estimated_preparation_minutes": 3
    }
  ]
}
```

| Поле | Описание |
|---|---|
| `schema_version` | Версия схемы. |
| `task` | `materials`. |
| `variant_id` | Для какого варианта сгенерированы материалы. |
| `materials` | Массив материалов с той же структурой, что у `variant.materials[]`. |
| `materials[].material_id` | ID материала. |
| `materials[].type` | Тип материала. |
| `materials[].title` | Название. |
| `materials[].used_in_blocks` | Массив ID блоков использования. |
| `materials[].audience` | Для кого материал. |
| `materials[].content` | Полное содержимое. |
| `materials[].teacher_notes` | Инструкция педагогу. |
| `materials[].print_required` | Нужна ли печать. |
| `materials[].dependencies` | Необходимые ресурсы. |
| `materials[].estimated_preparation_minutes` | Время подготовки в минутах. |

### 4.4. Этап `scenario_plan`

В этом этапе модель возвращает концепцию, роли и черновую сетку блоков по схеме `scenario_plan.schema.json`. После этого **Python** нормализует начало/длительности блоков. Точные `start_minute` и итоговые `duration_minutes` нельзя слепо принимать на веру из ответа LLM.

**v1.5 — пример ответа:**

```json
{
  "schema_version": "1.2",
  "task": "scenario_plan",
  "variant_id": "v1",
  "title": "Наш класс: новые цели",
  "concept": {
    "summary": "Класс формулирует общие цели нового учебного года и конкретные первые шаги.",
    "goal": "Согласовать цели и правила сотрудничества на учебный год.",
    "tasks": ["Определить общие приоритеты", "Научиться аргументировать предложения"],
    "expected_outcomes": ["Плакат с согласованными целями класса"],
    "values_to_mechanics": [
      {"value_id": "mutual_aid", "mechanic_type": "team_task", "mechanic": "Группы вместе формулируют цели", "block_ids": ["block_03"]},
      {"value_id": "citizenship", "mechanic_type": "real_problem_solving", "mechanic": "Реальный первый шаг класса на месяц", "block_ids": ["block_02", "block_04"]}
    ]
  },
  "grouping_request": {"mode": "small_groups", "groups_count": 5, "block_ids": ["block_03"]},
  "roles": [
    {"role_id": "teacher_1", "participant_type": "teacher", "title": "Ведущий педагог", "count": 1},
    {"role_id": "pupils_all", "participant_type": "pupils_group", "title": "Учащиеся", "count": 27},
    {"role_id": "parent_helpers", "participant_type": "parent", "role_mode": "helper", "title": "Помощники с карточками", "count": 2},
    {"role_id": "parent_audience", "participant_type": "parent", "role_mode": "audience", "title": "Зрители и голосующие", "count": 10}
  ],
  "blocks": [
    {"block_id": "block_01", "title": "Открытие и настрой", "purpose": "Обозначить смысл встречи", "proposed_minutes": 5, "role_ids": ["teacher_1", "pupils_all", "parent_audience"], "planned_material_ids": []},
    {"block_id": "block_02", "title": "Круг идей", "purpose": "Собрать идеи класса", "proposed_minutes": 10, "role_ids": ["teacher_1", "pupils_all", "parent_audience"], "planned_material_ids": []},
    {"block_id": "block_03", "title": "Командная мастерская", "purpose": "Подготовить реалистичные предложения", "proposed_minutes": 20, "role_ids": ["teacher_1", "pupils_all", "parent_helpers", "parent_audience"], "planned_material_ids": ["card_goals", "parent_instruction_01"]},
    {"block_id": "block_04", "title": "Выступления и выбор зрителей", "purpose": "Обобщить решения и завершить работу", "proposed_minutes": 10, "role_ids": ["teacher_1", "pupils_all", "parent_audience"], "planned_material_ids": ["audience_ballot_01"]}
  ],
  "planned_materials": [
    {"material_id": "card_goals", "type": "activity_card", "purpose": "Задание группам"},
    {"material_id": "parent_instruction_01", "type": "parent_instruction", "purpose": "Памятка помощникам"},
    {"material_id": "audience_ballot_01", "type": "audience_ballot", "purpose": "Бюллетень зрительского приза"}
  ]
}
```

| Поле | Описание |
|---|---|
| `concept` | Как в разделе 2, с `values_to_mechanics` и `block_ids`. |
| `grouping_request` | Желаемое деление: `mode`, `groups_count`, `block_ids`. Размеры групп рассчитывает Python и записывает в `pupil_grouping`. |
| `roles[]` | Роли без `block_ids`: связи с блоками сервис выводит из `blocks[].role_ids`. |
| `blocks[].proposed_minutes` | Предложение модели; итоговую сетку (`start_minute`, `duration_minutes`) рассчитывает `TimingService` (ТЗ 11.2). |
| `blocks[].planned_material_ids` | ID материалов, которые будут созданы на этапе `materials`; каждый есть в `planned_materials`. |
| `planned_materials[]` | Заготовки материалов: `material_id`, `type`, `purpose`. |

### 4.5. Этап `quality_review`

При отдельном LLM-анализе качества модель может возвращать **предложения по исправлению** с привязкой к `variant_id`, `block_id` и коду ошибки. Но окончательный `quality_report` вычисляется бэкендом по программным и содержательным проверкам; модель не может сама утверждать `passed`.

**v1.5 — пример ответа:**

```json
{
  "schema_version": "1.2",
  "task": "quality_review",
  "variant_id": "v1",
  "findings": [
    {
      "rule_code": "VAL-003",
      "severity_suggested": "warning",
      "location": "timeline.block_02",
      "message": "Ценность «Гражданственность» в блоке 2 выражена только фразой педагога, без действия учащихся.",
      "suggested_action": "Добавить шаг: класс выбирает одну цель и называет, кто и что сделает в первую неделю."
    },
    {
      "rule_code": "TIME-FEAS",
      "severity_suggested": "warning",
      "location": "timeline.block_04",
      "message": "Выступления пяти команд, голосование, подсчёт и награждение за 10 минут — плотно.",
      "suggested_action": "Ограничить выступление команды 1 минутой и объявить критерий голосования заранее, в блоке 3."
    }
  ],
  "fact_claims_review": []
}
```

| Поле | Описание |
|---|---|
| `findings[].rule_code` | Код правила из ТЗ (`VAL-*`, ресурсы, тайминг, возраст, культура и т. д.). |
| `findings[].severity_suggested` | Предложение модели; итоговую severity назначает сервис по правилу. |
| `findings[].location` | Путь к элементу варианта. |
| `findings[].message` / `suggested_action` | Описание и предлагаемое исправление для repair-запроса. |
| `fact_claims_review[]` | Для каждого утверждения из `fact_claims`: `claim_id`, `matches_fragment` (`true`/`false`), `comment`. Расхождение → `critical` (ТЗ 17.6). |

## 5. Ограничения, которые обязательны для любого LLM-ответа

1. Только валидный JSON по схеме текущего этапа, без Markdown-обрамления, комментариев и текста после закрывающей скобки.
2. Не придумывать ни дату проведения, ни фактическое количество проголосовавших, ни персональные сведения детей.
3. Не возвращать `job_id`, стоимость, токены, секреты, API-ключи или конечный статус `completed`/`passed` — эти сведения назначает backend.
4. Структура одного варианта не изменяет исходные параметры: 27 школьников, 12 родителей, разрешённые роли `helper` и `audience`, длительность 45 минут.
5. При наличии историко-культурных фактов использовать только выданные бэкендом подтверждённые источники; `sources` не должен содержать придуманные ссылки.
6. Каждый `role_id`, `block_id`, `material_id` связан с реальным элементом результата и проверяется после генерации.
7. Непрошедший проверку ответ сохраняется в DEV-логах для анализа, а фронтенду отдаётся только готовый и провалидированный результат либо структурированная ошибка.
8. **v1.5.** Не выбирать, не добавлять и не удалять ценности: `values_to_mechanics` содержит ровно ценности, переданные в промпте; каждая реализуется действием участников хотя бы в одном блоке.
9. **v1.5.** Каждое фактическое утверждение — в `fact_claims` со ссылкой на переданный фрагмент или с `needs_teacher_check=true`; утверждения «из памяти модели» без пометки запрещены.
10. **v1.5.** Задание семье (`family_task: true`) — только при ценности `family`, только `handout`, всегда необязательное и с равноценной альтернативой в том же материале.
11. **v1.5.** Значения `materials[].dependencies` — только из словаря, переданного в промпте (ТЗ 3.5).
12. **v1.5.** Без блока рассуждений в ответе (`reasoning_mode=disabled`); если модель его всё же вернула, сервис вырезает его до разбора JSON.
