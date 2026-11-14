"""Исправления ответа модели до проверки схемы.

Регрессия по прогону GigaChat-2-Max без схемы провайдера (structured_output_mode=none, 2026-10-26):
- план объявил материалами расходники `markers` и `paper`, на этапе материалов у них пустое содержание;
- адресат бюллетеня записан ID роли `parent_audience` вместо `parent`.
Раньше этап материалов повторялся дважды (6 вызовов, около 4 минут).
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.cli import main
from app.contracts import llm as c03
from app.generation.pipeline import StageFailed, _fix_enum, prepare_stage_output, resource_ids
from app.llm.jsonx import extract_json
from app.normalize import normalize
from app.trace import RunTrace
from tests.helpers import EXAMPLES, ROOT, catalog, request, settings
from tests.test_material_ids import ReplayLLM, replay_generator

REPLAY_DIR = ROOT / "tests" / "fixtures" / "replay_gigachat_no_schema"


def resources():
    return resource_ids(normalize(request("ex1_knowledge_day"), catalog(), settings()))


class PrepareStageOutputTest(unittest.TestCase):
    def test_resources_removed_from_plan(self):
        """Материалы с ID ресурса убираются из плана и из блоков."""
        data = {"planned_materials": [{"material_id": "paper", "type": "handout"}, {"material_id": "card_task", "type": "activity_card"}],
                "blocks": [{"block_id": "block_01", "planned_material_ids": ["paper", "card_task"]}]}
        fixes = prepare_stage_output("scenario_plan", data, resources())
        self.assertEqual([m["material_id"] for m in data["planned_materials"]], ["card_task"])
        self.assertEqual(data["blocks"][0]["planned_material_ids"], ["card_task"])
        self.assertEqual(fixes, [{"kind": "resource_materials_dropped", "material_ids": ["paper"]}])

    def test_materials_resources_and_audience(self):
        """На этапе материалов расходники убираются, адресат-роль приводится к типу участника."""
        data = {"materials": [{"material_id": "markers", "audience": "pupils_group", "content": ""},
                              {"material_id": "ballot", "audience": "parent_audience"},
                              {"material_id": "cards", "audience": "pupils_all"},
                              {"material_id": "memo", "audience": "teacher_1"},
                              {"material_id": "odd", "audience": "somebody"}]}
        prepare_stage_output("materials", data, resources())
        self.assertEqual([(m["material_id"], m["audience"]) for m in data["materials"]],
                         [("ballot", "parent"), ("cards", "pupils_group"), ("memo", "teacher"), ("odd", "somebody")])

    def test_other_stages_untouched(self):
        """Другие этапы не меняются."""
        data = {"blocks": [{"material_ids": ["paper"]}]}
        self.assertEqual(prepare_stage_output("scenario_blocks", data, resources()), [])
        self.assertEqual(data, {"blocks": [{"material_ids": ["paper"]}]})


class EnumFixTest(unittest.TestCase):
    """Без схемы провайдера модель иногда пишет значения не из списка (ex2, 2026-10-26: этап variation_plan падал трижды)."""

    def test_values_mapped(self):
        """Регистр, пробелы, синонимы и копия «одно из: a | b» из примера приводятся к допустимому значению."""
        cases = [("Small groups", "engagement_mode", "small_groups"), ("individual", "engagement_mode", "whole_class"),
                 ("одно из: whole_class | pairs | small_groups | mixed", "engagement_mode", "whole_class"),
                 ("creative_workshop", "activity_type", "creative_product"), ("presentation", "activity_type", "performance"),
                 ("game, quiz", "activity_type", "game"), ("team_game", "primary_mechanic", "team_game")]
        for value, kind, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(_fix_enum(value, kind), expected)

    def test_unknown_values(self):
        """Нераспознанное описательное поле концепции получает нейтральное значение, остальные остаются для проверки схемы."""
        self.assertEqual(_fix_enum("rhythm_dance", "activity_type"), "discussion")
        self.assertEqual(_fix_enum("something", "engagement_mode"), "mixed")
        self.assertEqual(_fix_enum("something", "mechanic_type"), "something")

    def test_variation_plan_fixed_before_schema(self):
        """Ответ variation_plan с чужими значениями исправляется и записывается в список исправлений."""
        data = {"concepts": [{"engagement_mode": "individual", "primary_mechanic": "creative_workshop",
                              "planned_structure": [{"activity_type": "discussion"}, {"activity_type": "craft"}],
                              "key_activities": [{"activity_type": "Team task"}],
                              "values_to_mechanics": [{"mechanic_type": "joint_product"}]}]}
        fixes = prepare_stage_output("variation_plan", data, set())
        c = data["concepts"][0]
        self.assertEqual((c["engagement_mode"], c["planned_structure"][1]["activity_type"], c["key_activities"][0]["activity_type"]),
                         ("whole_class", "creative_product", "team_task"))
        self.assertEqual([f["field"] for f in fixes], ["concepts.0.engagement_mode", "concepts.0.planned_structure.1.activity_type",
                                                       "concepts.0.key_activities.0.activity_type"])


class MechanicFallbackTest(unittest.TestCase):
    """Механика ценности не из списка (прогон 14.11, Рождество 7 кл, 30 мин): для «семьи» модель писала `sharing`
    и на просьбу исправить трижды вернула тот же ответ байт в байт - сценарий падал на первом этапе."""

    @staticmethod
    def mechanics():
        return {vid: value.get("allowed_mechanic_types", []) for vid, value in catalog().values.items()}

    def test_recorded_gigachat_answer_passes_schema(self):
        raw = (ROOT / "tests" / "fixtures" / "replay_gigachat_q03_mechanic" / "variation_plan.raw.txt").read_text(encoding="utf-8")
        data = extract_json(raw)
        fixes = prepare_stage_output("variation_plan", data, set(), None, self.mechanics())
        c03.VariationPlanResponse.model_validate(data)
        self.assertIn({"kind": "enum_fallback", "field": "concepts.0.values_to_mechanics.1.mechanic_type",
                       "from": "sharing", "to": "family_research"}, fixes)
        self.assertEqual(data["concepts"][0]["values_to_mechanics"][0]["mechanic_type"], "culture_comparison")

    def test_fallback_by_value(self):
        """Замена - первая разрешённая механика ценности; без каталога или для чужой ценности - `discussion`."""
        for value_id, mechanics, expected in (("mutual_aid", self.mechanics(), "team_task"),
                                               ("family", None, "discussion"), ("unknown_value", self.mechanics(), "discussion")):
            with self.subTest(value_id=value_id):
                data = {"concept": {"values_to_mechanics": [{"value_id": value_id, "mechanic_type": "storytelling"}]}}
                prepare_stage_output("scenario_plan", data, set(), None, mechanics)
                self.assertEqual(data["concept"]["values_to_mechanics"][0]["mechanic_type"], expected)

    def test_known_values_untouched(self):
        data = {"concepts": [{"values_to_mechanics": [{"value_id": "family", "mechanic_type": "discussion"},
                                                      {"value_id": "family", "mechanic_type": "Joint product"}]}]}
        fixes = prepare_stage_output("variation_plan", data, set(), None, self.mechanics())
        self.assertEqual([r["mechanic_type"] for r in data["concepts"][0]["values_to_mechanics"]], ["discussion", "joint_product"])
        self.assertNotIn("enum_fallback", {f["kind"] for f in fixes})


class FactClaimsWithoutTextTest(unittest.TestCase):
    """Прогон 14.11 (День народов Среднего Урала): факты в материалах только с `source_id` и `fragment_id`, без текста -
    ответ уходил на повторный вызов модели."""

    def quotes(self):
        return {f["fragment_id"]: f.get("quote", "") for f in catalog().verified_fragments("middle_urals_peoples_day", "RU-SVE")}

    def test_recorded_answer_passes_schema(self):
        raw = (ROOT / "tests" / "fixtures" / "replay_gigachat_q10_fact_claims" / "materials.raw.txt").read_text(encoding="utf-8")
        data = extract_json(raw)
        fixes = prepare_stage_output("materials", data, set(), set(catalog().dependencies), None, self.quotes())
        c03.STAGE_MODELS["materials"].model_validate(data)
        self.assertEqual([c["text"] for c in data["fact_claims"]], [self.quotes()[c["fragment_id"]] for c in data["fact_claims"]])
        self.assertEqual(sum("text_from_fragment" in f.get("fields", []) for f in fixes), 2)

    def test_unknown_fragment_dropped(self):
        data = {"materials": [], "fact_claims": [{"source_id": "src_x", "fragment_id": "frag_unknown"},
                                                 {"text": "Праздник отмечают в сентябре.", "fragment_id": "frag_unknown"}]}
        fixes = prepare_stage_output("materials", data, set(), None, None, self.quotes())
        self.assertEqual([c["text"] for c in data["fact_claims"]], ["Праздник отмечают в сентябре."])
        self.assertIn("fact_claims_dropped", {f["kind"] for f in fixes})

    def test_without_fragments_map_unchanged(self):
        """Без цитат фрагментов (старый вызов) факт без текста не трогается: его увидит проверка схемы."""
        data = {"materials": [], "fact_claims": [{"source_id": "src_x", "fragment_id": "frag_x"}]}
        prepare_stage_output("materials", data, set())
        self.assertNotIn("text", data["fact_claims"][0])
        self.assertEqual(len(data["fact_claims"]), 1)


class CliStageFailedTest(unittest.TestCase):
    def test_stage_failure_is_reported_as_json(self):
        """Если общий этап не прошёл схему, CLI печатает понятный JSON со статусом failed, а не трассировку Python."""
        request_path = str(EXAMPLES / "requests" / "ex1_knowledge_day.json")
        golden_path = str(EXAMPLES / "golden" / "ex1_knowledge_day.json")
        stdout = io.StringIO()
        with patch("app.generation.pipeline.Generator.run", side_effect=StageFailed("variation_plan", "Этап variation_plan: ответ не прошёл схему")), \
                contextlib.redirect_stdout(stdout):
            code = main(["generate", request_path, "--fixture", golden_path, "--no-trace"])
        self.assertEqual(code, 2)
        out = json.loads(stdout.getvalue())
        self.assertEqual(out["status"], "failed")
        self.assertEqual(out["error"]["stage"], "variation_plan")


class ReplayNoSchemaRunTest(unittest.TestCase):
    def test_materials_pass_first_time(self):
        """Записанный прогон без схемы проходит за 4 вызова: этап материалов не повторяется."""
        raw = json.loads((REPLAY_DIR / "request.json").read_text(encoding="utf-8"))
        client = ReplayLLM(REPLAY_DIR)
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            outcome = replay_generator(client, trace=RunTrace(run_dir, full_prompts=False, full_responses=False, secrets=[])).run(raw)
            events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(outcome.project["status"], "completed")
        self.assertEqual(client.calls, ["variation_plan", "scenario_plan", "scenario_blocks", "materials"])
        result = outcome.project["variants"][0]
        ids = {m["material_id"] for m in result["materials"]}
        self.assertFalse(ids & {"paper", "markers"})
        self.assertEqual(next(m for m in result["materials"] if m["type"] == "audience_ballot")["audience"], "parent")
        for block in result["timeline"]:
            self.assertGreaterEqual(len(block["pupil_actions"]), 2, block["block_id"])
        fixed = [e for e in events if e["event_type"] == "stage_output_fixed"]
        self.assertEqual([e["stage"] for e in fixed], ["scenario_plan", "materials"])
        self.assertEqual([i for i in result["quality_report"]["issues"] if i["severity"] == "critical"], [])



class FamilyTaskReplayTest(unittest.TestCase):
    """ex2 (День матери, 2 класс), 2026-10-26: типы материалов `template`/`examples`/`reference`
    и задание семье с альтернативой «Если поговорить не получается… представь героя книжки».
    Раньше: 7 вызовов и failed по VAL-005, хотя альтернатива в тексте была."""

    def test_family_task_with_alternative_passes(self):
        directory = ROOT / "tests" / "fixtures" / "replay_gigachat_family_task"
        raw = json.loads((directory / "request.json").read_text(encoding="utf-8"))
        client = ReplayLLM(directory)
        outcome = replay_generator(client).run(raw)
        self.assertEqual(outcome.project["status"], "completed")
        self.assertEqual(client.calls, ["variation_plan", "scenario_plan", "scenario_blocks", "materials"])
        result = outcome.project["variants"][0]
        family = [m for m in result["materials"] if m["material_id"] == "optional_family_interview"]
        self.assertEqual(len(family), 1)
        self.assertEqual({m["type"] for m in result["materials"]}, {"handout"})
        self.assertEqual(result["quality_report"]["issues"], [])

    def test_alternative_wording(self):
        """Альтернатива, сформулированная без слова «альтернатива», распознаётся; задание без неё - нет."""
        from app.validation.checks import FAMILY_ALTERNATIVE
        self.assertTrue(FAMILY_ALTERNATIVE.search("Если поговорить не получается, ничего страшного!"))
        self.assertTrue(FAMILY_ALTERNATIVE.search("Можно представить, как ответил бы герой твоей любимой книжки"))
        self.assertTrue(FAMILY_ALTERNATIVE.search("Если дома некому помочь, расскажи об учителе"))
        self.assertTrue(FAMILY_ALTERNATIVE.search("Если такой возможности нет, ничего страшного! Просто подумай сам"))
        self.assertFalse(FAMILY_ALTERNATIVE.search("Спроси маму, какое у неё любимое блюдо, и запиши ответ."))


if __name__ == "__main__":
    unittest.main()