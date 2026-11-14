"""Объём реплик педагога зависит от длительности блока.

Раньше порог был один на любой блок (600 символов при detailed): трёхминутное приветствие
считалось коротким наравне с двадцатиминутной работой в командах.
"""

import unittest

from app.generation.pipeline import Generator
from app.llm.fixture import FixtureLLM
from app.normalize import normalize
from app.prompting.composer import Composer
from app.script_length import script_min_chars, script_target_chars
from app.validation.checks import validate_variant
from tests.helpers import catalog, golden, minimal_request, request, settings
from tests.test_validation_render import codes, setup


def gen_cfg():
    return settings().generation()


class ScriptLengthTest(unittest.TestCase):
    def test_grows_with_duration(self):
        """Длинному блоку нужно больше текста, чем короткому; детальный сценарий длиннее стандартного."""
        cfg = gen_cfg()
        self.assertLess(script_min_chars(cfg, "detailed", 3), script_min_chars(cfg, "detailed", 20))
        self.assertLess(script_min_chars(cfg, "standard", 10), script_min_chars(cfg, "detailed", 10))
        self.assertLess(script_min_chars(cfg, "brief", 10), script_min_chars(cfg, "standard", 10))
        self.assertGreater(script_target_chars(cfg, "detailed", 10), script_min_chars(cfg, "detailed", 10))

    def test_younger_grades_shorter(self):
        """Для 1-4 классов норма меньше (age_factor 0,7): с восьмилетними говорят короче (QA c3, BUG-05)."""
        cfg = gen_cfg()
        self.assertEqual(script_min_chars(cfg, "detailed", 10, "1-4"), int(script_min_chars(cfg, "detailed", 10) * 0.7))
        self.assertEqual(script_min_chars(cfg, "detailed", 10, "5-8"), script_min_chars(cfg, "detailed", 10))
        self.assertEqual(script_min_chars(cfg, "detailed", 10, None), script_min_chars(cfg, "detailed", 10))

    def test_younger_grades_prompt_and_warning(self):
        """Промпт блока для 1-4 классов называет уменьшенный объём и просит короткие предложения; SCRIPT-SHORT по той же норме."""
        n = normalize(minimal_request(grade_group="1-4", teacher_preferences={"script_detail": "detailed"}), catalog(), settings())
        composed = Composer(settings(), catalog()).compose(
            "scenario_block", n, stage_input="",
            output_vars={"variant_id": "v1", "block_id": "block_02", "start_minute": "5", "block_minutes": "10"})
        text = "\n".join(m["content"] for m in composed.messages)
        self.assertIn(f"на 10 мин - от {script_min_chars(gen_cfg(), 'detailed', 10, '1-4')},", text)
        self.assertIn("короткими простыми предложениями", text)
        _, v = setup("ex1_knowledge_day")
        block = v["timeline"][2]
        block["teacher_script"] = "Х" * (script_min_chars(gen_cfg(), "detailed", block["duration_minutes"], "1-4") + 5)
        self.assertNotIn("SCRIPT-SHORT", {i.code for i in validate_variant(v, n, catalog(), gen_cfg())
                                          if i.location == f"timeline.{block['block_id']}"})

    def test_warning_depends_on_block_duration(self):
        """Один и тот же текст достаточен для короткого блока и мал для длинного."""
        n, v = setup("ex1_knowledge_day")
        cfg = gen_cfg()
        short, long_ = v["timeline"][0], v["timeline"][2]
        text = "Х" * (script_min_chars(cfg, "detailed", short["duration_minutes"]) + 10)
        self.assertLess(len(text), script_min_chars(cfg, "detailed", long_["duration_minutes"]))
        short["teacher_script"] = text
        self.assertNotIn("SCRIPT-SHORT", codes(v, n))
        long_["teacher_script"] = text
        self.assertIn("SCRIPT-SHORT", codes(v, n))

    def test_prompts_name_the_size(self):
        """Промпт блоков называет объём; в плане для этапа блоков объём указан у каждого блока."""
        n = normalize(request("ex1_knowledge_day"), catalog(), settings())
        composed = Composer(settings(), catalog()).compose(
            "scenario_block", n, stage_input="",
            output_vars={"variant_id": "v1", "block_id": "block_02", "start_minute": "5", "block_minutes": "15"})
        text = "\n".join(m["content"] for m in composed.messages)
        self.assertIn(f"на 15 мин - от {script_min_chars(gen_cfg(), 'detailed', 15)}", text)
        plan = {"variant_id": "v1", "title": "T", "concept": {"summary": "s", "goal": "g", "values_to_mechanics": []},
                "roles": [], "blocks": [{"block_id": "block_01", "title": "A", "purpose": "p", "role_ids": [], "planned_material_ids": []}],
                "planned_materials": [], "grouping_request": {"block_ids": []}}
        plan_text = Generator.plan_text(plan, [(0, 10)], ("whole_class", [27]), script_chars=lambda m: f"от {m * 100}")
        self.assertIn("реплики педагога: от 1000", plan_text)


class PerBlockModeTest(unittest.TestCase):
    def test_blocks_written_one_by_one(self):
        """Блоки пишутся по одному вызову и для 45 минут: у каждого блока свой запрос и свой лимит ответа."""
        client = FixtureLLM([golden("ex1_knowledge_day")])
        outcome = Generator(settings(), catalog(), client).run(request("ex1_knowledge_day"))
        tasks = [c["task"] for c in client.calls]
        self.assertNotIn("scenario_blocks", tasks)
        self.assertEqual(tasks.count("scenario_block"), len(outcome.project["variants"][0]["timeline"]))
        self.assertEqual(outcome.project["status"], "completed")


if __name__ == "__main__":
    unittest.main()


class ReasoningStageTest(unittest.TestCase):
    """Рассуждения по этапам: по умолчанию выключены; включаются в config/generation.json или LLM_REASONING."""

    def generator(self):
        return Generator(settings(), catalog(), FixtureLLM([golden("ex1_knowledge_day")]))

    def test_default_off_and_override(self):
        import os
        from unittest.mock import patch
        gen = self.generator()
        n = normalize(request("ex1_knowledge_day"), catalog(), settings())
        base = gen.max_output_tokens("scenario_plan", n)
        self.assertIsNone(gen.reasoning_effort("scenario_plan"))
        with patch.dict(os.environ, {"LLM_REASONING": "scenario_plan=medium, materials=extreme"}):
            self.assertEqual(gen.reasoning_effort("scenario_plan"), "medium")
            self.assertIsNone(gen.reasoning_effort("materials"))  # неизвестный уровень не передаётся
            self.assertIsNone(gen.reasoning_effort("scenario_block"))
            self.assertEqual(gen.max_output_tokens("scenario_plan", n), base + gen.cfg["reasoning_extra_output_tokens"])
        with patch.dict(os.environ, {"LLM_REASONING": "*=low"}):
            self.assertEqual(gen.reasoning_effort("materials"), "low")
        gen.cfg = {**gen.cfg, "tasks": {**gen.cfg["tasks"], "scenario_block": {**gen.cfg["tasks"]["scenario_block"], "reasoning_effort": "high"}}}
        self.assertEqual(gen.reasoning_effort("scenario_block"), "high")

    def test_from_dotenv(self):
        """`LLM_REASONING` из `.env` (настройки сервиса), а не только из окружения процесса."""
        import os
        from unittest.mock import patch
        from app.settings import Settings
        from tests.helpers import ROOT
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LLM_REASONING", None)
            gen = Generator(Settings(root=ROOT, env={"LLM_REASONING": "scenario_plan=high"}), catalog(),
                            FixtureLLM([golden("ex1_knowledge_day")]))
            self.assertEqual(gen.reasoning_effort("scenario_plan"), "high")
            self.assertIsNone(gen.reasoning_effort("materials"))

    def test_reasoning_saved_in_trace(self):
        """Рассуждения модели - отдельным файлом в трассе вызова, уровень и объём - в manifest; JSON разбирается как обычно."""
        import dataclasses
        import json
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from app.trace import RunTrace
        from tests.test_material_ids import ReplayLLM

        class Thinking(ReplayLLM):
            def generate(self, **kwargs):
                result = super().generate(**kwargs)
                effort = (kwargs.get("meta") or {}).get("reasoning_effort")
                return dataclasses.replace(result, reasoning=f"рассуждения ({effort})") if effort else result

        directory = Path(__file__).parent / "fixtures" / "replay_gigachat_bug14_jury"
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"LLM_REASONING": "scenario_plan=medium"}):
            trace = RunTrace(Path(tmp), secrets=[])
            outcome = Generator(settings(), catalog(), Thinking(directory), trace=trace).run(
                json.loads((directory / "request.json").read_text(encoding="utf-8")))
            self.assertEqual(outcome.project["status"], "completed")
            plan_calls = [p.parent for p in Path(tmp).glob("calls/*/manifest.json")
                          if json.loads(p.read_text(encoding="utf-8"))["stage"] == "scenario_plan"]
            manifest = json.loads((plan_calls[0] / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["reasoning_effort"], "medium")
            self.assertEqual((plan_calls[0] / "response.reasoning.txt").read_text(encoding="utf-8"), "рассуждения (medium)")
            block = next(p.parent for p in Path(tmp).glob("calls/*/manifest.json")
                         if json.loads(p.read_text(encoding="utf-8"))["stage"] == "scenario_block")
            self.assertFalse((block / "response.reasoning.txt").exists())