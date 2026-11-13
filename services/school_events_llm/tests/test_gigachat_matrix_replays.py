"""Прогон матрицы на GigaChat-2-Max (03.11.2026): записанные ответы модели и исправления по ним.

Из 18 прогонов 2 упали, ещё в 10 этапы повторялись. Причины:
- `content` материала списком или словарём, а не строкой (вопросы, карточки станций) - 6 повторов этапа материалов;
- задание семье «до мероприятия» с пустым `used_in_blocks`;
- комментарий `// …` и неэкранированная кавычка внутри JSON;
- значения не из списков: `primary_mechanic=joint_product`, `mechanic_type=creative_workshop`, `type=reward`;
- нет `groups_count` при работе парами;
- альтернатива в задании семье «если тебе сложно…, можешь написать…» не распознавалась (`VAL-005`).

Повторный прогон матрицы на версии с этими исправлениями: 5 из 6. Ещё два случая:
- m3 (жюри): инструкция к награждению по итогам жюри считалась запрещённой (`BALLOT-NOT-ALLOWED`),
  а блоки плана ссылались на расходники `paper`, `markers` без объявления в `planned_materials`;
- m2 (голосование): все родители стали помощниками, зрителей нет - голосующих 0 (`VOTING-NO-VOTERS`);
  памятка родителям помечена `family_task`, и исправление `VAL-005` превращало её в раздаточный материал.

Третий прогон: 5 из 6, m1 упал на блоке рефлексии. Модель разбила `teacher_script` на абзацы отдельными
строками без ключа, а исправление кавычек склеивало их со следующим ключом, и `pupil_actions` пропадал.
"""

import copy
import json
import unittest

from app.generation.ids import UNASSIGNED_BLOCK, content_to_text, normalize_material_fields
from app.generation.pipeline import Generator, _fix_enum, prepare_stage_output
from app.llm.jsonx import extract_json
from app.normalize import normalize
from app.validation.checks import FAMILY_ALTERNATIVE, validate_variant
from tests.helpers import ROOT, catalog, settings
from tests.test_material_ids import ReplayLLM

FIXTURES = ROOT / "tests" / "fixtures"


def replay(name):
    directory = FIXTURES / name
    client = ReplayLLM(directory)
    outcome = Generator(settings(), catalog(), client).run(json.loads((directory / "request.json").read_text(encoding="utf-8")))
    return outcome, client


class JsonRepairTest(unittest.TestCase):
    def test_comment_inside_json(self):
        text = '{"materials": [{"used_in_blocks": [\n "block_03" // Добавлено использование\n ], "x": 1}]}'
        self.assertEqual(extract_json(text), {"materials": [{"used_in_blocks": ["block_03"], "x": 1}]})

    def test_comment_marker_inside_string_kept(self):
        self.assertEqual(extract_json('{"url": "https://example.org/a", "n": 1,}'), {"url": "https://example.org/a", "n": 1})

    def test_unescaped_quote_and_newline(self):
        text = '{"block": {"teacher_script": "«Начинаем!" (Через 10 минут)\n"Молодцы!"", "pupil_actions": ["a"]}}'
        data = extract_json(text)
        self.assertEqual(data["block"]["pupil_actions"], ["a"])
        self.assertIn("(Через 10 минут)", data["block"]["teacher_script"])


    def test_stray_strings_joined_to_previous_value(self):
        text = '{"a": {"teacher_script": "Раз.", "Два.",\n "Три."\n ,\n "pupil_actions": ["x"]}}'
        self.assertEqual(extract_json(text), {"a": {"teacher_script": "Раз.\nДва.\nТри.", "pupil_actions": ["x"]}})

    def test_stray_string_before_closing_brace(self):
        self.assertEqual(extract_json('{"text": "Раз.", "Два."}'), {"text": "Раз.\nДва."})

    def test_m1_reflection_block_split_into_paragraphs(self):
        """m1 (третий прогон): все 3 попытки блока рефлексии падали с `pupil_actions: Field required`."""
        data = extract_json((FIXTURES / "gigachat_block_stray_strings.txt").read_text(encoding="utf-8"))
        block = data["block"]
        self.assertEqual(len(block["pupil_actions"]), 2)
        self.assertEqual(block["role_ids"], ["teacher_1", "pupils_all"])
        self.assertTrue(block["teacher_script"].startswith("(После завершения церемонии дарения.)"))
        self.assertTrue(block["teacher_script"].endswith("Всего хорошего!"))
        self.assertIn("\nКакие чувства вызвало у вас", block["teacher_script"])


class MaterialFieldsTest(unittest.TestCase):
    def test_content_to_text(self):
        self.assertEqual(content_to_text(["Вопрос один", "Вопрос два"]), "1. Вопрос один\n2. Вопрос два")
        self.assertEqual(content_to_text([{"question": "Что?", "answer": "Это"}]), "1. Вопрос: Что?; Ответ: Это")
        self.assertEqual(content_to_text({"Язык": "Башкирский", "приветствие": "Сәлам!"}), "Язык: Башкирский\nприветствие: Сәлам!")

    def test_empty_used_in_blocks_and_props(self):
        data = {"materials": [{"material_id": "family", "type": "handout", "content": "Задание для семьи на дом", "used_in_blocks": []},
                              {"material_id": "kit", "type": "props_checklist", "title": "Набор для украшения", "content": "",
                               "teacher_notes": "Разложить на столах.", "used_in_blocks": ["block_02"]}]}
        normalize_material_fields(data, [])
        self.assertEqual(data["materials"][0]["used_in_blocks"], [UNASSIGNED_BLOCK])
        self.assertEqual(data["materials"][1]["content"], "Подготовить: Набор для украшения. Разложить на столах.")

    def test_groups_count_default(self):
        data = {"grouping_request": {"mode": "pairs", "block_ids": ["block_03"]}}
        prepare_stage_output("scenario_plan", data, set())
        self.assertEqual(data["grouping_request"]["groups_count"], 1)

    def test_enum_synonyms_from_runs(self):
        self.assertEqual(_fix_enum("joint_product", "primary_mechanic"), "creative_workshop")
        self.assertEqual(_fix_enum("creative_workshop", "mechanic_type"), "joint_product")
        self.assertEqual(_fix_enum("class_collective_task", "activity_type"), "team_task")
        self.assertEqual(_fix_enum("reward", "material_type"), "props_checklist")

    def test_block_refs_to_resources_dropped(self):
        data = {"planned_materials": [{"material_id": "cards", "type": "activity_card", "purpose": "-"}],
                "blocks": [{"block_id": "block_01", "planned_material_ids": ["cards", "paper", "markers"]}]}
        changes = prepare_stage_output("scenario_plan", data, {"paper", "markers"})
        self.assertEqual(data["blocks"][0]["planned_material_ids"], ["cards"])
        self.assertIn({"kind": "resource_materials_dropped", "material_ids": ["markers", "paper"]}, changes)

    def test_family_task_cleared_for_parent_materials(self):
        data = {"materials": [{"material_id": "parent_instruction", "type": "parent_instruction", "family_task": True,
                               "content": "Памятка", "used_in_blocks": ["block_01"]},
                              {"material_id": "home", "type": "handout", "family_task": True,
                               "content": "Задание семье", "used_in_blocks": ["block_01"]}]}
        changes = []
        normalize_material_fields(data, changes)
        self.assertFalse(data["materials"][0]["family_task"])
        self.assertTrue(data["materials"][1]["family_task"])
        self.assertEqual([c["kind"] for c in changes], ["family_task_cleared"])

    def test_family_alternative_wording(self):
        self.assertTrue(FAMILY_ALTERNATIVE.search("Если тебе сложно заполнить анкету или спросить взрослого, можешь написать своё желание"))
        self.assertFalse(FAMILY_ALTERNATIVE.search("Заполни анкету вместе с родителями и принеси её."))


class MatrixReplayTest(unittest.TestCase):
    def test_m1_mothers_day_active_parents(self):
        """m1: был failed (этап материалов не прошёл схему трижды), теперь completed с первой попытки материалов."""
        outcome, client = replay("replay_gigachat_matrix_m1")
        self.assertEqual(outcome.project["status"], "completed")
        self.assertEqual(client.calls.count("materials"), 1)
        variant = outcome.project["variants"][0]
        mats = {m["material_id"]: m for m in variant["materials"]}
        blocks = [b["block_id"] for b in variant["timeline"]]
        for m in mats.values():
            self.assertTrue(set(m["used_in_blocks"]) <= set(blocks), m["material_id"])
        quiz = next(m for m in mats.values() if m["type"] == "quiz")
        self.assertIn("Ответ:", quiz["content"])

    def test_m2_new_year_vote(self):
        """m2: был failed по VAL-005, теперь completed без исправлений этапа материалов."""
        outcome, client = replay("replay_gigachat_matrix_m2")
        self.assertEqual(outcome.project["status"], "completed")
        self.assertEqual(client.calls.count("materials"), 1)

    def test_m3_jury_award_without_repairs(self):
        """m3: был failed по BALLOT-NOT-ALLOWED и с лишним вызовом плана, теперь без повторов этапов."""
        outcome, client = replay("replay_gigachat_matrix_m3_jury")
        self.assertEqual(outcome.project["status"], "completed")
        self.assertEqual(client.calls.count("scenario_plan"), 1)
        self.assertEqual(client.calls.count("materials"), 1)
        variant = outcome.project["variants"][0]
        codes = {i["code"] for i in variant["quality_report"]["issues"]}
        self.assertEqual(codes, {"SCRIPT-SHORT"})
        self.assertIn("award_instruction", {m["type"] for m in variant["materials"]})

    def test_ballot_still_forbidden_with_jury(self):
        """Жюри разрешает инструкцию к награждению, но не бюллетень зрителей."""
        outcome, _ = replay("replay_gigachat_matrix_m3_jury")
        variant = copy.deepcopy(outcome.project["variants"][0])
        variant["materials"].append({**variant["materials"][-1], "material_id": "ballot", "type": "audience_ballot"})
        n = normalize(json.loads((FIXTURES / "replay_gigachat_matrix_m3_jury" / "request.json").read_text(encoding="utf-8")), catalog(), settings())
        gen = Generator(settings(), catalog(), None)
        codes = [(i.code, i.location) for i in validate_variant(variant, n, catalog(), gen.cfg)]
        self.assertIn(("BALLOT-NOT-ALLOWED", "materials.ballot"), codes)
        self.assertNotIn(("BALLOT-NOT-ALLOWED", "materials.award_instruction"), codes)

    def test_m2_vote_helpers_count_as_voters(self):
        """m2: зрителей в плане нет, голосуют родители-помощники из блока голосования; памятка родителям остаётся памяткой."""
        outcome, client = replay("replay_gigachat_matrix_m2_vote")
        self.assertEqual(outcome.project["status"], "completed")
        self.assertEqual(client.calls.count("materials"), 1)
        variant = outcome.project["variants"][0]
        self.assertEqual(variant["quality_report"]["issues"], [])
        self.assertEqual(variant["parent_participation_plan"]["voting"]["voters_count_planned"], 15)
        types = {m["material_id"]: m["type"] for m in variant["materials"]}
        self.assertEqual(types["parent_instruction"], "parent_instruction")

    def test_unescaped_quote_block(self):
        """06: ответ блока с неэкранированной кавычкой разбирается без повтора, текст блока не обрезан."""
        outcome, client = replay("replay_gigachat_unescaped_quote")
        self.assertEqual(outcome.project["status"], "completed")
        self.assertEqual(client.calls.count("scenario_block"), len(outcome.project["variants"][0]["timeline"]))
        scripts = " ".join(b["teacher_script"] for b in outcome.project["variants"][0]["timeline"])
        self.assertIn("(Через 10 минут педагог собирает группу обратно)", scripts)


if __name__ == "__main__":
    unittest.main()