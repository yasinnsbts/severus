"""Баг-лист QA от 14.11.2026 (сборка PR #30, 03c6b0c) на записанных ответах GigaChat из трасс Максима.

- BUG-14: жюри (`labour_day`, 10 класс) - лист назван `jury_scorecard`, тип `quiz`; вариант падал после двух исправлений.
- BUG-17: 12 родителей, помощники и зрители - 12 + 1 = 13; вариант терялся после двух пересборок (30 вызовов).
- BUG-09: помощники есть, памятки `parent_instruction` нет; при «призе зрительских симпатий» нет `award_instruction`.
- BUG-16: `teacher_fallback` в памятке педагогу, `colored_papers` в заметках (это писала программа).
- BUG-11: «1 сентября 2023 г.» в шаблоне письма; проверенный факт с годом без записи в `fact_claims`.
"""

import unittest

from app.generation.humanize import DATE_BLANK, blank_template_dates
from app.generation.ids import normalize_dependencies
from app.generation.pipeline import prepare_stage_output
from app.generation.plan_fixes import fix_plan_for_request
from app.generation.source_refs import register_fragment_facts
from tests.helpers import catalog
from tests.test_gigachat_matrix_replays import replay


def issues(variant):
    return {(i["code"], i["location"]) for i in variant["quality_report"]["issues"]}


class Bug14JuryTest(unittest.TestCase):
    def test_recorded_run_completes(self):
        outcome, client = replay("replay_gigachat_bug14_jury")
        self.assertEqual(outcome.project["status"], "completed")
        self.assertEqual(len(client.calls), 8)  # было 10 вызовов и failed
        variant = outcome.project["variants"][0]
        self.assertIn(("jury_scorecard", "jury_scorecard"), {(m["material_id"], m["type"]) for m in variant["materials"]})
        self.assertNotIn("JURY-SCORECARD", {code for code, _ in issues(variant)})

    def test_type_by_id(self):
        data = {"planned_materials": [{"material_id": "jury_scorecard", "type": "quiz", "purpose": "p"},
                                      {"material_id": "audience_ballot_2", "type": "handout", "purpose": "p"},
                                      {"material_id": "quiz_cards", "type": "quiz", "purpose": "p"}], "roles": []}
        fixes = prepare_stage_output("scenario_plan", data, set())
        self.assertEqual([m["type"] for m in data["planned_materials"]], ["jury_scorecard", "audience_ballot", "quiz"])
        self.assertEqual(sum(f["kind"] == "type_by_id" for f in fixes), 2)


class Bug17ParentsTest(unittest.TestCase):
    def test_recorded_run_keeps_both_variants(self):
        outcome, client = replay("replay_gigachat_bug17_parents")
        self.assertEqual(outcome.project["status"], "completed")
        self.assertEqual(len(client.calls), 15)  # было 30 вызовов и partial
        self.assertEqual([v["status"] for v in outcome.project["variants"]], ["completed", "completed"])
        v1 = outcome.project["variants"][0]
        self.assertEqual({(a["role_mode"], a["count"]) for a in v1["parent_participation_plan"]["assignments"]},
                         {("helper", 11), ("audience", 1)})
        self.assertNotIn("PARENTS-OVER", {code for code, _ in issues(v1)})

    def test_zero_count_and_balance(self):
        data = {"roles": [{"role_id": "parent_helpers", "participant_type": "parent", "role_mode": "helper", "count": 12},
                          {"role_id": "parent_audience", "participant_type": "parent", "role_mode": "audience", "count": 0}]}
        prepare_stage_output("scenario_plan", data, set())
        self.assertEqual(data["roles"][1]["count"], 1)
        plan = {"roles": data["roles"], "blocks": [], "planned_materials": [{"material_id": "parent_instruction", "type": "parent_instruction"}]}
        fixes = fix_plan_for_request(plan, True, 12, "none")
        self.assertEqual([r["count"] for r in plan["roles"]], [11, 1])
        self.assertEqual(fixes[0]["kind"], "parent_counts_balanced")

    def test_counts_within_limit_untouched(self):
        plan = {"roles": [{"role_id": "a", "participant_type": "parent", "role_mode": "audience", "count": 5}], "blocks": [],
                "planned_materials": []}
        self.assertEqual(fix_plan_for_request(plan, True, 12, "none"), [])
        self.assertEqual(plan["roles"][0]["count"], 5)


class Bug09RequiredMaterialsTest(unittest.TestCase):
    def test_recorded_run_has_memos(self):
        """Записанные материалы памятки не содержат: программа добавила её в план и написала простую версию."""
        outcome, _ = replay("replay_gigachat_bug09_helpers")
        self.assertEqual(outcome.project["status"], "completed")
        for variant in outcome.project["variants"]:
            with self.subTest(variant=variant["variant_id"]):
                types = {m["type"] for m in variant["materials"]}
                self.assertLessEqual({"parent_instruction", "award_instruction"}, types)
                codes = {code for code, _ in issues(variant)}
                self.assertFalse(codes & {"PARENT-INSTRUCTION", "AWARD-INSTRUCTION", "REF-MATERIAL"})
                memo = next(m for m in variant["materials"] if m["type"] == "parent_instruction")
                if variant["variant_id"] != "v1":  # в v1 модель написала памятку сама, в v2 и v3 - простая версия программы
                    self.assertIn("мин)", memo["content"])

    def test_added_to_plan_and_blocks(self):
        plan = {"roles": [{"role_id": "teacher_1", "participant_type": "teacher", "count": 1},
                          {"role_id": "helpers", "participant_type": "parent", "role_mode": "helper", "count": 3},
                          {"role_id": "jury", "participant_type": "parent", "role_mode": "evaluator", "count": 2},
                          {"role_id": "audience", "participant_type": "parent", "role_mode": "audience", "count": 4}],
                "blocks": [{"block_id": "block_01", "role_ids": ["teacher_1", "helpers"], "planned_material_ids": []},
                           {"block_id": "block_02", "role_ids": ["teacher_1", "jury", "audience"], "planned_material_ids": []},
                           {"block_id": "block_03", "role_ids": ["teacher_1", "audience"], "planned_material_ids": []}],
                "planned_materials": []}
        fix_plan_for_request(plan, True, 9, "audience_award")
        self.assertEqual({m["type"] for m in plan["planned_materials"]}, {"parent_instruction", "jury_scorecard", "award_instruction"})
        self.assertEqual([b["planned_material_ids"] for b in plan["blocks"]],
                         [["parent_instruction"], ["jury_scorecard"], ["award_instruction"]])
        again = fix_plan_for_request(plan, True, 9, "audience_award")
        self.assertEqual(again, [])


class Bug16TechIdsTest(unittest.TestCase):
    def test_recorded_runs_clean(self):
        outcome, _ = replay("replay_gigachat_bug16_e2e18")
        self.assertNotIn(("TECH-ID-IN-TEXT", "materials.poster_materials"), issues(outcome.project["variants"][0]))
        outcome, _ = replay("replay_gigachat_bug09_helpers")
        self.assertNotIn(("TECH-ID-IN-TEXT", "teacher_instructions"), issues(outcome.project["variants"][0]))
        self.assertIn("запасной план", " ".join(outcome.project["variants"][0]["teacher_instructions"]))

    def test_unknown_dependencies_readable(self):
        data = {"materials": [{"material_id": "m", "teacher_notes": "Раздайте.",
                               "dependencies": ["whatman", "colored_papers", "envelopes", "glitter_glue"]}]}
        normalize_dependencies(data, set(catalog().dependencies), [])
        material = data["materials"][0]
        self.assertEqual(material["dependencies"], ["whatman", "paper"])
        self.assertEqual(material["teacher_notes"], "Раздайте. Также понадобится: конверты, glitter glue.")


class Bug11DatesTest(unittest.TestCase):
    def test_letter_date_blanked(self):
        outcome, _ = replay("replay_gigachat_bug09_helpers")
        v3 = outcome.project["variants"][2]
        letter = next(m for m in v3["materials"] if m["material_id"] == "letter_template")
        self.assertNotIn("2023", letter["content"])
        self.assertIn(DATE_BLANK, letter["content"])
        self.assertNotIn("FACT-UNREGISTERED", {code for code, _ in issues(v3)})

    def test_only_date_lines_blanked(self):
        variant = {"materials": [{"material_id": "m", "content": "С уважением, Маша\n1 сентября 2023 г.\nДата: 01.09.2023\n"
                                                                    "17 января 1934 года область разделили."}]}
        blank_template_dates(variant)
        self.assertEqual(variant["materials"][0]["content"],
                         f"С уважением, Маша\n{DATE_BLANK}\nДата: {DATE_BLANK}\n17 января 1934 года область разделили.")

    def test_fact_from_fragment_registered(self):
        """«…начать год с 1 января 1700 года» есть в проверенной цитате о Новом годе - факт записывается программой."""
        fragments = catalog().verified_fragments("new_year", "RU-SVE")
        variant = {"timeline": [{"block_id": "block_02",
                                 "teacher_script": "Пётр I постановил начать год с 1 января 1700 года. А в 1800 году всё изменилось."}],
                   "materials": [], "fact_claims": []}
        changes = register_fragment_facts(variant, fragments)
        self.assertEqual([c["fragment_id"] for c in variant["fact_claims"]], ["frag_new_year_001"])
        self.assertEqual(variant["fact_claims"][0]["text"], "Пётр I постановил начать год с 1 января 1700 года.")
        self.assertEqual(len(changes), 1)


if __name__ == "__main__":
    unittest.main()