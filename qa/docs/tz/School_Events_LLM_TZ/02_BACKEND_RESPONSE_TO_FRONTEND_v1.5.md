# Контракт 02 — JSON-ответ LLM-бэкенда фронтенду (v1.5 — без изменений относительно v1.4, `schema_version` 1.2)

> **v1.5: контракт заморожен.** JSON этого документа (состав полей, типы, ограничения, значения по умолчанию, примеры) **идентичен v1.4**. Новые возможности v1.5 — ценностный слой, профиль школы, правила участия семьи, культурный контур, режимы экспериментов — реализуются внутри сервиса и в контракте 03 и не требуют изменений фронтенда и `backend/schemas.py`. Общий бэкенд «Северус» передаёт этот JSON в сервис `services/school_events_llm` без преобразования (ТЗ 1.3, 15.0).

**Источник:** наш бэкенд. **Получатель:** фронтенд через `GET /api/v1/projects/{project_id}`. Основной пример — полностью завершённый проект из трёх самостоятельных сценариев. Каждый содержит концепцию, роли, 45-минутный план, материалы, работу с родителями и результат проверки. Примеры текстов сценария сжаты для иллюстрации схемы; продуктивная генерация должна детализировать реплики.

## 1. Полный пример JSON

```json
{
  "schema_version": "1.2",
  "job_id": "job_20261017_a001",
  "project_id": "evt_20261017_0001",
  "status": "completed",
  "requested_variants": 3,
  "completed_variants": 3,
  "input": {
    "event_id": "knowledge_day",
    "grade_group": "5-8",
    "grade": 6,
    "pupils_count": 27,
    "duration_minutes": 45,
    "format": "class_hour",
    "region_id": "RU-SVE",
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
      "available_materials": ["paper", "markers"],
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
  },
  "variants": [
    {
      "variant_id": "v1",
      "revision": 1,
      "status": "completed",
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
        ]
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
      "sources": [],
      "quality_report": {
        "status": "passed",
        "issues": [],
        "checked_at": "2026-10-17T10:00:00Z"
      }
    },
    {
      "variant_id": "v2",
      "revision": 1,
      "status": "completed",
      "title": "Миссия: учебный год",
      "concept": {
        "summary": "Класс проходит командный маршрут из заданий о сотрудничестве, планировании и взаимопомощи.",
        "goal": "Развить навыки командного взаимодействия и распределения задач.",
        "tasks": [
          "Тренировать работу в группах",
          "Составить командный план действий"
        ],
        "expected_outcomes": [
          "Памятка правил командного сотрудничества"
        ]
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
          "title": "Старт миссии",
          "purpose": "Объяснить правила маршрута",
          "teacher_script": "Объявите миссию: получить карту совместных действий класса. Кратко сформулируйте правила безопасности и поддержки.",
          "pupil_actions": [
            "Слушают правила и задают вопросы."
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
          "title": "Сбор команды",
          "purpose": "Распределить командные роли",
          "teacher_script": "Разделите школьников на пять команд и предложите распределить роли: координатор, докладчик, хранитель времени.",
          "pupil_actions": [
            "Определяют роли и договариваются о правилах."
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
          "title": "Командные станции",
          "purpose": "Выполнить последовательные задания",
          "teacher_script": "Раздайте карточки с двумя ситуациями. Команды предлагают решения, отмечая действие каждого участника.",
          "pupil_actions": [
            "Решают задачи и фиксируют общий маршрут."
          ],
          "role_ids": [
            "teacher_1",
            "pupils_all",
            "parent_audience",
            "parent_helpers"
          ],
          "material_ids": [
            "card_mission",
            "parent_instruction_01"
          ]
        },
        {
          "block_id": "block_04",
          "start_minute": 35,
          "duration_minutes": 10,
          "title": "Финал миссии и голосование",
          "purpose": "Подвести итог игры",
          "teacher_script": "Попросите команды представить решения. Зрители голосуют за самую понятную командную инструкцию. Объявите символический приз и завершите общим обсуждением.",
          "pupil_actions": [
            "Представляют решения и называют правило сотрудничества."
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
          "material_id": "card_mission",
          "type": "activity_card",
          "title": "Карточка командной миссии",
          "used_in_blocks": [
            "block_03"
          ],
          "audience": "pupils_group",
          "content": "Ситуация 1: команда не успевает. Предложите решение. Ситуация 2: участник остаётся без роли. Как его вовлечь?",
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
          "content": "Отметьте одну команду по критерию: Понятность решения для совместной работы. Один голос на одного зрителя.",
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
          "criterion": "Понятность решения для совместной работы",
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
      "sources": [],
      "quality_report": {
        "status": "passed",
        "issues": [],
        "checked_at": "2026-10-17T10:00:00Z"
      }
    },
    {
      "variant_id": "v3",
      "revision": 1,
      "status": "completed",
      "title": "Школа будущего: лаборатория идей",
      "concept": {
        "summary": "Учащиеся разрабатывают мини-проекты улучшения школьной среды и презентуют их.",
        "goal": "Развивать умение совместно проектировать изменения школьной среды.",
        "tasks": [
          "Выделить конкретную проблему",
          "Предложить достижимое улучшение"
        ],
        "expected_outcomes": [
          "Мини-проекты пяти ученических команд"
        ]
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
          "title": "Открытие лаборатории",
          "purpose": "Поставить исследовательский вопрос",
          "teacher_script": "Спросите, какие небольшие изменения сделают школьную жизнь удобнее и интереснее. Уточните, что идеи должны быть посильными.",
          "pupil_actions": [
            "Приводят идеи и наблюдения."
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
          "title": "Выбор проблем",
          "purpose": "Определить темы проектов",
          "teacher_script": "Предложите выбрать пять небольших задач. Разделите учеников на пять команд и закрепите задачу за каждой.",
          "pupil_actions": [
            "Формулируют проблему своей команды."
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
          "title": "Проектная мастерская",
          "purpose": "Создать черновик решения",
          "teacher_script": "Раздайте бланки проекта: проблема, решение, первые действия, нужные ресурсы. Помогите уточнить реалистичность идей.",
          "pupil_actions": [
            "Готовят проект на листе и договариваются о выступлении."
          ],
          "role_ids": [
            "teacher_1",
            "pupils_all",
            "parent_audience",
            "parent_helpers"
          ],
          "material_ids": [
            "card_ideas",
            "parent_instruction_01"
          ]
        },
        {
          "block_id": "block_04",
          "start_minute": 35,
          "duration_minutes": 10,
          "title": "Защита проектов и награждение",
          "purpose": "Собрать предложения",
          "teacher_script": "Каждая команда кратко защищает идею. Зрители выбирают наиболее понятно объяснённое решение. Объявите символический приз и подчеркните вклад всех групп.",
          "pupil_actions": [
            "Защищают идеи и формулируют итоговые шаги."
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
          "material_id": "card_ideas",
          "type": "activity_card",
          "title": "Бланк идеи для школы",
          "used_in_blocks": [
            "block_03"
          ],
          "audience": "pupils_group",
          "content": "Запишите проблему, предложенное решение, ресурсы и первый достижимый шаг.",
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
          "content": "Отметьте одну команду по критерию: Ясность и выполнимость предлагаемой идеи. Один голос на одного зрителя.",
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
          "criterion": "Ясность и выполнимость предлагаемой идеи",
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
      "sources": [],
      "quality_report": {
        "status": "passed",
        "issues": [],
        "checked_at": "2026-10-17T10:00:00Z"
      }
    }
  ],
  "generation_meta": {
    "model_key": "qwen_local_9b",
    "prompt_version": "1.0.0",
    "catalog_version": "1.0"
  }
}
```

## 2. Описание каждого поля

| Поле | Тип | Обязательность / смысл |
|---|---|---|
| `schema_version` | `string` | Версия контракта **бэкенд → фронтенд**, не версия используемой модели. |
| `job_id` | `string` | Идентификатор текущей задачи генерации и ключ к диагностическим журналам; новый при регенерации. |
| `project_id` | `string` | Постоянный идентификатор проекта, объединяющий 1–3 варианта. |
| `status` | `enum` | Состояние всей задачи: `queued`, `running`, `completed`, `partial`, `failed` (и другие статусы по регламенту API). `completed` допустим лишь когда готовы все запрошенные варианты. |
| `requested_variants` | `integer 1–3` | Запрошенное число вариантов. |
| `completed_variants` | `integer 0–3` | Число прошедших проверку и доступных вариантов. |
| `input` | `object` | **Эффективные нормализованные параметры** после применения V1-дефолтов. Содержит `participants`, `resources`, `teacher_preferences`, `generation`; без секретов. |
| `input.event_id` | `string` | Каталожный идентификатор праздника. |
| `input.grade_group` | `enum` | Возрастная группа `1-4`, `5-8`, `9-11`. |
| `input.grade` | `integer/null` | Точный класс. |
| `input.pupils_count` | `integer` | Точное число учеников. |
| `input.duration_minutes` | `enum integer` | Точная длительность мероприятия. |
| `input.format` | `enum string` | Формат мероприятия. |
| `input.region_id` | `string` | Регион, пилот `RU-SVE`. |
| `input.participants` | `object` | Нормализованные параметры состава участников; значение всех дочерних полей соответствует входному контракту. |
| `input.participants.teachers_count` | `integer` | Фактически доступное число педагогов. |
| `input.participants.parents_enabled` | `boolean` | Разрешено ли участие родителей. |
| `input.participants.parents_count` | `integer` | Точное число родителей без округления. |
| `input.participants.parent_roles` | `array<enum>` | Разрешённые пользователем роли родителей. |
| `input.participants.parent_roles[]` | `string enum` | Отдельная разрешённая роль: `helper`, `active_participant`, `audience`, `evaluator`. |
| `input.participants.parent_audience_engagement` | `enum` | Выбранный способ вовлечения зрителей: `none`, `feedback`, `vote`, `audience_award`. |
| `input.participants.parent_notes` | `string|null` | Дополнительное пожелание по родительским ролям, если пришло и сохраняется. |
| `input.resources` | `object` | Использованные ограничения по оборудованию и материалам. Отсутствовавшие ресурсные флаги остаются `null` («неизвестно»). |
| `input.resources.projector` | `boolean/null` | Проектор: `true`/`false`/`null` (V1 по умолчанию `null`). |
| `input.resources.printer` | `boolean/null` | Принтер, V1 по умолчанию `null`. |
| `input.resources.internet` | `boolean/null` | Интернет, V1 по умолчанию `null`. |
| `input.resources.audio` | `boolean/null` | Аудиооборудование, V1 по умолчанию `null`. |
| `input.resources.room` | `string/null` | Помещение, V1 по умолчанию `null`. |
| `input.resources.available_materials` | `array<string>` | Указанные доступные материалы; V1 по умолчанию `[]`. |
| `input.resources.extra_notes` | `string/null` | Примечания к ресурсам; V1 по умолчанию `null`. |
| `input.teacher_preferences` | `object` | Эффективные настройки педагога после подстановки V1-дефолтов. |
| `input.teacher_preferences.style` | `enum` | `classic`/`interactive`/`creative`/`research`; V1 по умолчанию `classic`. |
| `input.teacher_preferences.script_detail` | `enum` | `brief`/`standard`/`detailed`; V1 по умолчанию `standard`. |
| `input.teacher_preferences.difficulty` | `enum` | `basic`/`standard`/`advanced`; V1 по умолчанию `standard`. |
| `input.teacher_preferences.interaction_level` | `enum` | `low`/`medium`/`high`; **V1 по умолчанию `low`**. |
| `input.teacher_preferences.group_work` | `boolean` | Работа в малых группах; **V1 по умолчанию `false` (0)**. |
| `input.teacher_preferences.preparation_effort` | `enum` | `minimal`/`standard`/`extended`; V1 по умолчанию `minimal`. |
| `input.teacher_preferences.notes` | `string/null` | Пожелания; V1 по умолчанию `null`. |
| `input.generation` | `object` | Эффективные настройки генерации. |
| `input.generation.variants_count` | `integer 1–3` | Число вариантов, V1 по умолчанию `1`. |
| `input.generation.language` | `enum` | Язык, V1 `ru`. |
| `variants` | `array<object>, 0–3` | Массив готовых вариантов. При завершённом успешном проекте длина равна `requested_variants`. В частичном состоянии содержит только готовые варианты. |
| `variants[].variant_id` | `string` | Уникальный ID варианта в проекте, например `v1`. |
| `variants[].revision` | `integer ≥1` | Номер сохранённой версии варианта. Повышается при успешной регенерации. |
| `variants[].status` | `enum` | `completed` для прошедшего проверку готового варианта; незавершённые представлены в отдельном статусе задачи. |
| `variants[].title` | `string` | Человеко-читаемое название сценария. |
| `variants[].concept` | `object` | Педагогическая концепция сценария. |
| `variants[].concept.summary` | `string` | Краткое описание основной сценарной идеи. |
| `variants[].concept.goal` | `string` | Основная педагогическая цель. |
| `variants[].concept.tasks` | `array<string>` | Действия/задачи, которые ведут к достижению цели. |
| `variants[].concept.tasks[]` | `string` | Одна задача. |
| `variants[].concept.expected_outcomes` | `array<string>` | Конкретные ожидаемые результаты мероприятия. |
| `variants[].concept.expected_outcomes[]` | `string` | Один ожидаемый результат. |
| `variants[].roles` | `array<object>` | Список участников-исполнителей и их функций в сценарии. |
| `variants[].roles[].role_id` | `string` | Уникальный ID роли, на него ссылаются тайминг и план родителей. |
| `variants[].roles[].participant_type` | `enum` | Тип: `teacher`, `pupil`, `pupils_group`, `parent`, `guest`. |
| `variants[].roles[].role_mode` | `enum, условное` | Режим родительской роли (`helper`/`active_participant`/`audience`/`evaluator`). Для педагогов и детей отсутствует. |
| `variants[].roles[].title` | `string` | Понятное название роли. |
| `variants[].roles[].count` | `integer ≥1` | Число людей, выполняющих роль (нельзя превышать доступную численность в один момент). |
| `variants[].roles[].block_ids` | `array<string>` | Какие блоки связываются с ролью. |
| `variants[].roles[].block_ids[]` | `string` | ID блока из `timeline[].block_id`. |
| `variants[].timeline` | `array<object>` | Временная сетка мероприятия, сумма длительностей строго равна заявленным минутам. |
| `variants[].timeline[].block_id` | `string` | Уникальный ID блока в пределах варианта. |
| `variants[].timeline[].start_minute` | `integer ≥0` | Минута начала относительно старта мероприятия. Первый блок начинается с 0. |
| `variants[].timeline[].duration_minutes` | `integer >0` | Длительность блока; блоки не пересекаются и не создают пробелов. |
| `variants[].timeline[].title` | `string` | Название блока. |
| `variants[].timeline[].purpose` | `string` | Для чего нужен блок. |
| `variants[].timeline[].teacher_script` | `string` | Текст ведущего и исполнимые инструкции педагогу (в финальном результате — подробный, не условная заглушка). |
| `variants[].timeline[].pupil_actions` | `array<string>` | Что непосредственно делают школьники. |
| `variants[].timeline[].pupil_actions[]` | `string` | Одно действие учащихся. |
| `variants[].timeline[].role_ids` | `array<string>` | Роли, задействованные в блоке. |
| `variants[].timeline[].role_ids[]` | `string` | Существующий `roles[].role_id`. |
| `variants[].timeline[].material_ids` | `array<string>` | Материалы, используемые в блоке. |
| `variants[].timeline[].material_ids[]` | `string` | Существующий `materials[].material_id`. |
| `variants[].materials` | `array<object>` | Все материалы, необходимые для выполнения сценария. |
| `variants[].materials[].material_id` | `string` | Уникальный ID материала в пределах варианта. |
| `variants[].materials[].type` | `enum` | `teacher_instruction`, `worksheet`, `activity_card`, `slide_outline`, `quiz`, `discussion_questions`, `handout`, `props_checklist`, `parent_instruction`, `audience_ballot`, `jury_scorecard`, `award_instruction`. |
| `variants[].materials[].title` | `string` | Название материала. |
| `variants[].materials[].used_in_blocks` | `array<string>` | В каких блоках применяется. |
| `variants[].materials[].used_in_blocks[]` | `string` | Существующий `timeline[].block_id`. |
| `variants[].materials[].audience` | `string/enum` | Для кого материал предназначен: педагог, ученик, группа, родитель и др. |
| `variants[].materials[].content` | `string` | Полный текст материала или структурированное содержимое по типу материала. |
| `variants[].materials[].teacher_notes` | `string` | Пояснения педагогу по использованию материала. |
| `variants[].materials[].print_required` | `boolean` | Обязательна ли печать (если true — доступный принтер должен быть предусмотрен либо дана альтернатива). |
| `variants[].materials[].dependencies` | `array<string>` | Необходимый реквизит/оборудование. |
| `variants[].materials[].dependencies[]` | `string` | Название зависимости, должно согласовываться с `resources`. |
| `variants[].materials[].estimated_preparation_minutes` | `integer ≥0, предложено` | Ориентировочное время подготовки материала. Не часть продолжительности самого события. |
| `variants[].parent_participation_plan` | `object, условное` | Обязателен у готового варианта с родителями; при их отсутствии — можно опустить либо вернуть `enabled=false` без назначений. |
| `variants[].parent_participation_plan.enabled` | `boolean` | Включено ли участие родителей. |
| `variants[].parent_participation_plan.parents_count` | `integer` | Точное исходное число родителей. |
| `variants[].parent_participation_plan.parent_size_group` | `enum` | Вычисленная категория `none`, `1-2`, `3-5`, `6-10`, `11_plus`. |
| `variants[].parent_participation_plan.selected_roles` | `array<enum>` | Роли, разрешённые пользователем и применяемые в плане. |
| `variants[].parent_participation_plan.selected_roles[]` | `string` | Одна родительская роль. |
| `variants[].parent_participation_plan.audience_engagement` | `enum` | Режим вовлечения зрителей из входа. |
| `variants[].parent_participation_plan.assignments` | `array<object>` | Назначения по блокам; нельзя назначить 12 помощников плюс 12 зрителей одновременно при наличии 12 родителей. |
| `variants[].parent_participation_plan.assignments[].role_id` | `string` | Ссылка на существующую родительскую роль. |
| `variants[].parent_participation_plan.assignments[].participant_type` | `enum` | Здесь `parent`. |
| `variants[].parent_participation_plan.assignments[].role_mode` | `enum` | Здесь одна из разрешённых `parent_roles`. |
| `variants[].parent_participation_plan.assignments[].count` | `integer ≥1` | Количество родителей в назначении. |
| `variants[].parent_participation_plan.assignments[].block_ids` | `array<string>` | В какие блоки назначены родители. |
| `variants[].parent_participation_plan.assignments[].block_ids[]` | `string` | Существующий ID блока. |
| `variants[].parent_participation_plan.voting` | `object/null, условное` | Регламент зрительского голосования. Если голосования нет, null или отсутствует. |
| `variants[].parent_participation_plan.voting.enabled` | `boolean` | Включён ли режим голосования. |
| `variants[].parent_participation_plan.voting.award_title` | `string/null` | Название символической награды при режиме `audience_award`. |
| `variants[].parent_participation_plan.voting.voters_count_planned` | `integer ≥0` | Запланированное число зрителей-избирателей, а **не** число фактически проголосовавших. |
| `variants[].parent_participation_plan.voting.criterion` | `string` | Понятный и объявленный заранее критерий голосования. |
| `variants[].parent_participation_plan.voting.method` | `enum/string` | Форма голосования, например `paper_ballot`. |
| `variants[].parent_participation_plan.voting.votes_per_person` | `integer ≥1` | Сколько голосов может подать один зритель. |
| `variants[].parent_participation_plan.voting.tie_rule` | `string` | Что делать при равенстве голосов. |
| `variants[].parent_participation_plan.voting.block_id` | `string` | ID блока для зрительского голосования. |
| `variants[].parent_participation_plan.voting.material_ids` | `array<string>` | Ссылки на бланки/инструкции голосования. |
| `variants[].parent_participation_plan.voting.material_ids[]` | `string` | Существующий `materials[].material_id`. |
| `variants[].parent_participation_plan.teacher_fallback` | `string` | Как провести сценарий силами педагога и школьников, если родители не пришли. |
| `variants[].teacher_instructions` | `array<string>` | Чек-лист подготовки и указания организатору. |
| `variants[].teacher_instructions[]` | `string` | Одно действие по подготовке или проведению. |
| `variants[].sources` | `array<object>` | Верифицированные источники, использованные для утверждений (здесь пусто, потому что исторические факты не используются). |
| `variants[].sources[]` | `object, при наличии` | Запись разрешённого источника из каталога с ID, названием и ссылкой/локатором; формат отдельно утверждается в JSON Schema. |
| `variants[].quality_report` | `object` | Результаты валидаторов и проверок бэкенда (LLM не выставляет себе финальный статус). |
| `variants[].quality_report.status` | `enum` | `passed`, `warning`, `blocked`; для `completed` не допускается критический `blocked`. |
| `variants[].quality_report.issues` | `array<object>` | Обнаруженные проблемы или предупреждения (пустой массив означает, что проверка не нашла проблем). |
| `variants[].quality_report.issues[]` | `object, при наличии` | Описание проблемы с `code`, `severity`, `message`, полем/блоком и действиями по исправлению; полная схема определяется валидатором. |
| `variants[].quality_report.checked_at` | `ISO-8601 string` | Время завершения проверки качества. |
| `generation_meta` | `object` | Технические метаданные генерации (не сырые промпты и не ключи доступа). |
| `generation_meta.model_key` | `string` | Ключ выбранной модельной конфигурации, например `qwen_local_9b`. |
| `generation_meta.prompt_version` | `string` | Версия набора промптов. |
| `generation_meta.catalog_version` | `string` | Версия каталога мероприятий. |
| `variants[]` | `object` | Один полностью проверенный самостоятельный вариант мероприятия. |
| `variants[].roles[]` | `object` | Одно описание роли/категории участников. |
| `variants[].timeline[]` | `object` | Один блок тайминга мероприятия. |
| `variants[].materials[]` | `object` | Один материал: карточка, бланк, инструкция и т. п. |
| `variants[].parent_participation_plan.assignments[]` | `object` | Одно назначение родителей на конкретные блоки сценария. |


## 3. Особые правила ответа

- Сервер возвращает в `input` **фактически использованные настройки**, а не только те поля, которые были присланы фронтендом. Отсутствующие необязательные поля дополнены согласно `config/request_defaults.json`. Значения, явно переданные фронтендом, не заменяются дефолтами.
- Если `teacher_preferences` полностью отсутствовал, `input.teacher_preferences.interaction_level="low"`, `input.teacher_preferences.group_work=false`, остальные предпочтения берутся из конфигурации V1. Родители без включения: `parents_enabled=false`, `parents_count=0`, `parent_roles=[]`.
- Для исходного примера фронтенд явно передал `interaction_level="high"` и `group_work=true`, поэтому в полном ответе отражаются именно они. `false` и `true` передаются типом boolean, не числами `0`/`1`.

1. Это **объект бэкенда**, а не сырой ответ LLM. Backend сам добавляет `job_id`, `project_id`, `revision`, `status`, `quality_report`, `generation_meta` и вычисляет тайминги.
2. Успешный итог `status="completed"` означает **ровно** `requested_variants` готовых полноценных сценариев, где каждый `variants[].status="completed"`.
3. Если готовы два сценария из трёх, сервер может вернуть `status="running"` или итоговый `status="partial"` при исчерпанных попытках; успешный полный статус запрещён.
4. Фронтенду доступны 1–3 **разные концепции**, но все исходные ограничения общие.
5. `timeline` каждого варианта начинается с 0 и заканчивается на `input.duration_minutes`. В примере 5+10+20+10=45 минут. Перекрёстные `role_ids` и `material_ids` всегда разрешаются.
6. Родительские назначения считаются по одновременной занятости в каждом блоке; роль `parent_audience` и два `parent_helpers` не превышают 12 присутствующих родителей.
7. `voting.voters_count_planned=10` — план, а не фактическое число голосов на мероприятии.
8. В данном JSON достаточно краткие реплики **для демонстрации структуры**. В рабочем ответе сценарий должен содержать развернутые педагогические реплики и точные инструкции по каждому действию.
9. Секреты, полные промпты, сырые LLM-ответы и промежуточные невалидные ответы не передаются фронтенду: они доступны только в диагностических журналах DEV.
10. **v1.5 — как новые механики видны в этом же JSON (без новых полей).** Воспитательные задачи события и строки «Ценность «…» → механика (блоки: …)» сервис добавляет первыми элементами `concept.tasks`; деление на группы — в `roles[].title`, `teacher_script` и `teacher_instructions`; необязательное задание семье — обычный материал `handout` с пометкой «(по желанию, до мероприятия)»; утверждения, требующие проверки педагогом, — в `quality_report.issues` с `severity=warning`; `sources[]` содержит записи `{source_id, title, publisher, url}` только из проверенного корпуса. Формат вывода — ТЗ 14.6. Фронтенду достаточно показывать эти поля как раньше.

## 4. Ответ при создании задачи и при выполнении

При первоначальном `POST /api/v1/generations` возвращаем `HTTP 202`, структуру см. в документе `01_FRONTEND_REQUEST.md`. Затем фронтенд опрашивает `GET /api/v1/generations/{job_id}`:

```json
{
  "job_id": "job_20261017_a001",
  "project_id": "evt_20261017_0001",
  "status": "running",
  "phase": "materials",
  "requested_variants": 3,
  "completed_variants": 2,
  "variants": [
    {
      "variant_id": "v1",
      "status": "completed",
      "revision": 1
    },
    {
      "variant_id": "v2",
      "status": "completed",
      "revision": 1
    },
    {
      "variant_id": "v3",
      "status": "materials",
      "revision": 1
    }
  ],
  "warnings": [],
  "errors": []
}
```

| Поле | Тип | Обязательность / смысл |
|---|---|---|
| `job_id` | `string` | ID задачи. |
| `project_id` | `string` | ID проекта. |
| `status` | `enum` | Общий статус задачи (`queued`, `running`, `completed`, `partial`, `failed`). |
| `phase` | `enum/string` | Текущий шаг конвейера (например `variation_plan`, `scenario_plan`, `scenario_block`, `materials`, `validating`). |
| `requested_variants` | `integer` | Сколько вариантов требовалось. |
| `completed_variants` | `integer` | Сколько полностью готово. |
| `variants` | `array<object>` | Краткая сводка по всем слотам, включая незавершённые. |
| `variants[].variant_id` | `string` | ID слота варианта. |
| `variants[].status` | `enum` | Текущий статус варианта (например `completed`, `materials`). |
| `variants[].revision` | `integer` | Текущая/целевая ревизия варианта. |
| `warnings` | `array<object>` | Неблокирующие предупреждения, если есть. |
| `errors` | `array<object>` | Ошибки исполнения, если есть. |

После появления готовых вариантов фронтенд запрашивает `GET /api/v1/projects/{project_id}` или `GET /api/v1/projects/{project_id}/variants/{variant_id}` и показывает уже полностью провалидированные результаты.

## 5. Формат ошибок (HTTP 4xx/5xx)

```json
{
  "error": {
    "code": "INVALID_VARIANTS_COUNT",
    "message": "Количество вариантов должно быть от 1 до 3",
    "field": "generation.variants_count",
    "retryable": false
  }
}
```

| Поле | Значение |
|---|---|
| `error` | Контейнер ошибки. |
| `error.code` | Стабильный машинный код для фронтенда. |
| `error.message` | Текст для отображения пользователю. |
| `error.field` | Поле входного запроса, связанное с ошибкой (если есть). |
| `error.retryable` | Можно ли повторить запрос без изменения входных параметров. |
