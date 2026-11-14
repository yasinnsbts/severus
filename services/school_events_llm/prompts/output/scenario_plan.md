<!-- id: output.scenario_plan | version: 1.1.0 -->
## Формат ответа

Верни один JSON-объект плана для варианта `{{variant_id}}`. Сумма `proposed_minutes` = {{duration_minutes}}.

```json
{
  "schema_version": "1.2",
  "task": "scenario_plan",
  "variant_id": "{{variant_id}}",
  "title": "Название варианта",
  "concept": {
    "summary": "2–3 предложения",
    "goal": "Главная педагогическая цель",
    "tasks": ["Педагогическая задача 1", "Педагогическая задача 2"],
    "expected_outcomes": ["Конкретный результат"],
    "values_to_mechanics": [
      {"value_id": "{{first_value_id}}", "mechanic_type": "…", "mechanic": "Как реализуется действием участников", "block_ids": ["block_03"]}
    ]
  },
  "grouping_request": {"mode": "whole_class | pairs | small_groups | mixed", "groups_count": 1, "block_ids": ["block_03"]},
  "roles": [
    {"role_id": "teacher_1", "participant_type": "teacher", "title": "Ведущий педагог", "count": 1},
    {"role_id": "pupils_all", "participant_type": "pupils_group", "title": "Учащиеся", "count": {{pupils_count}}}{{parent_roles_example}}
  ],
  "blocks": [
    {"block_id": "block_01", "title": "Название", "purpose": "Зачем нужен блок", "proposed_minutes": 5, "role_ids": ["teacher_1", "pupils_all"], "planned_material_ids": []}
  ],
  "planned_materials": [
    {"material_id": "card_task", "type": "activity_card", "title": "Карточки заданий", "purpose": "Для чего"}
  ]
}
```

`type` материала: teacher_instruction | worksheet | activity_card | slide_outline | quiz | discussion_questions | handout | props_checklist | parent_instruction | audience_ballot | jury_scorecard | award_instruction.
`role_id` и `material_id` - латиница, цифры и `_`, начинаются с буквы. В `values_to_mechanics` - ровно ценности: {{value_ids}}.