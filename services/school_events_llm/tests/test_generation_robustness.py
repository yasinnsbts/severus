"""Устойчивость генерации: допустимые ID и зависимости, повторы после ошибок, предсказуемые ошибки задачи.

Задача спринта: генератор не создаёт недопустимых ссылок на материалы и неизвестных `dependency_id`;
повторные попытки после ошибок проверены; ошибки генерации обрабатываются предсказуемо.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import job_status
from app.cli import main
from app.contracts import llm as c03
from app.generation.ids import block_id, normalize_dependencies, normalize_ids, slug_id
from app.generation.pipeline import Generator, StageFailed, fix_material_refs, prepare_stage_output
from app.llm.client import LLMClient, LLMError
from app.llm.fixture import FixtureLLM
from app.trace import RunTrace
from tests.helpers import EXAMPLES, catalog, golden, request, settings

DEPS = set(catalog().dependencies)


class MutatingLLM(LLMClient):
    """Эталонные ответы, испорченные так, как это делают реальные модели."""

    model_key = "mutating_fixture"
    provider = "fixture"

    def __init__(self, inner: FixtureLLM, mutate: dict):
        self.inner, self.mutate = inner, mutate

    def health(self):
        return self.inner.health()

    def generate(self, **kwargs):
        res = self.inner.generate(**kwargs)
        fn = self.mutate.get(kwargs["task_name"])
        if fn:
            text = res.text[res.text.index("{"):res.text.rindex("}") + 1]
            data = json.loads(text)
            fn(data)
            res.text = json.dumps(data, ensure_ascii=False)
        return res


class FlakyLLM(LLMClient):
    """Первые `fail_times` вызовов этапа `stage` падают с ошибкой провайдера."""

    model_key = "flaky_fixture"
    provider = "fixture"

    def __init__(self, inner: FixtureLLM, stage: str, error: LLMError, fail_times: int):
        self.inner, self.stage, self.error, self.left = inner, stage, error, fail_times

    def health(self):
        return self.inner.health()

    def generate(self, **kwargs):
        if kwargs["task_name"] == self.stage and self.left > 0:
            self.left -= 1
            raise self.error
        return self.inner.generate(**kwargs)


def fixture(name="ex1_knowledge_day"):
    return FixtureLLM([golden(name)])


def generator(client, run_dir=None):
    trace = RunTrace(run_dir, full_prompts=False, full_responses=False, secrets=[]) if run_dir else None
    gen = Generator(settings(), catalog(), client, trace=trace)
    gen.sleeps = []
    gen._sleep = gen.sleeps.append
    return gen


def events(run_dir: Path) -> list[dict]:
    return [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]


class IdsTest(unittest.TestCase):
    def test_slug_id(self):
        """ID приводится к `^[a-z][a-z0-9_]*$`; правильный ID не меняется."""
        cases = {"card_task": "card_task", "Card-Task": "card_task", "Карточки задания": "kartochki_zadaniya",
                 "1_ballot": "mat_1_ballot", "  Ballot  01 ": "ballot_01", "parent.instruction": "parent_instruction"}
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(slug_id(raw, "mat"), expected)

    def test_block_id(self):
        for raw in ("block_02", "Block_2", "block-2", "block 02"):
            with self.subTest(raw=raw):
                self.assertEqual(block_id(raw), "block_02")

    def test_plan_ids_consistent(self):
        """В плане ID материалов и ссылки блоков исправляются одинаково; дубли материалов схлопываются."""
        data = {"roles": [{"role_id": "Teacher-1"}],
                "planned_materials": [{"material_id": "Card-Task", "type": "activity_card"},
                                      {"material_id": "card_task", "type": "activity_card"}],
                "blocks": [{"block_id": "Block_1", "role_ids": ["Teacher-1"], "planned_material_ids": ["Card-Task", "card_task"]}]}
        changes = []
        normalize_ids("scenario_plan", data, changes)
        self.assertEqual(data["roles"][0]["role_id"], "teacher_1")
        self.assertEqual([m["material_id"] for m in data["planned_materials"]], ["card_task"])
        self.assertEqual(data["blocks"][0], {"block_id": "block_01", "role_ids": ["teacher_1"], "planned_material_ids": ["card_task"]})
        self.assertIn({"kind": "duplicate_material_dropped", "material_id": "card_task"}, changes)


class DependenciesTest(unittest.TestCase):
    def test_synonyms_and_unknown(self):
        """Синонимы - в ID словаря, неизвестное - из `dependencies` в заметку педагогу."""
        data = {"materials": [{"material_id": "m", "teacher_notes": "Раздать командам.",
                               "dependencies": ["Paper", "flipchart", "scotch", "balloons", "paper", "Воздушные шарики"]}]}
        changes = []
        normalize_dependencies(data, DEPS, changes)
        m = data["materials"][0]
        self.assertEqual(m["dependencies"], ["paper", "whatman", "tape"])
        self.assertEqual(m["teacher_notes"], "Раздать командам. Также понадобится: balloons, Воздушные шарики.")
        self.assertTrue(all(d in DEPS for d in m["dependencies"]))

    def test_materials_stage_passes_schema(self):
        """Ответ этапа материалов с неправильными ID и зависимостями проходит схему после исправлений."""
        data = {"schema_version": "1.2", "task": "materials", "variant_id": "v1", "teacher_instructions": ["x"],
                "materials": [{"material_id": "Card-Task", "type": "activity_card", "title": "t", "used_in_blocks": ["Block_2"],
                               "audience": "pupils_all", "content": "Содержание карточки задания для команд",
                               "teacher_notes": "", "print_required": True, "dependencies": ["A4", "stickers", "laser pointer"],
                               "estimated_preparation_minutes": 5}],
                "voting": None, "teacher_fallback": None, "fact_claims": []}
        prepare_stage_output("materials", data, set(), DEPS)
        model = c03.MaterialsResponse.model_validate(data)
        m = model.materials[0]
        self.assertEqual((m.material_id, m.used_in_blocks, m.dependencies, m.audience),
                         ("card_task", ["block_02"], ["paper", "sticky_notes"], "pupils_group"))
        self.assertEqual(m.teacher_notes, "Также понадобится: laser pointer.")


class MaterialRefsTest(unittest.TestCase):
    def test_refs_to_missing_blocks_and_materials(self):
        """Ссылки на несуществующие блоки и материалы исправляются по сценарию."""
        timeline = [{"block_id": "block_01", "material_ids": []}, {"block_id": "block_02", "material_ids": ["ballot"]}]
        mat = SimpleNamespace(
            materials=[SimpleNamespace(material_id="ballot", type="audience_ballot", used_in_blocks=["block_09"])],
            voting=SimpleNamespace(material_ids=["ballot_99"], block_id="block_07"))
        fixes = fix_material_refs(mat, timeline)
        self.assertEqual(mat.materials[0].used_in_blocks, ["block_02"])
        self.assertEqual(mat.voting.material_ids, ["ballot"])
        self.assertEqual(mat.voting.block_id, "block_02")
        self.assertEqual({f["kind"] for f in fixes}, {"used_in_blocks", "voting_material_ids", "voting_block_id"})


class PipelineWithBrokenIdsTest(unittest.TestCase):
    def test_bad_ids_and_dependencies_do_not_fail_generation(self):
        """Модель пишет ID в другом регистре, неизвестные зависимости и блок `Block_4`: генерация проходит без повторов."""
        def plan(data):
            for m in data["planned_materials"]:
                if m["material_id"] == "card_goals":
                    m["material_id"] = "Card-Goals"
            for b in data["blocks"]:
                b["planned_material_ids"] = ["Card-Goals" if x == "card_goals" else x for x in b["planned_material_ids"]]

        def materials(data):
            for m in data["materials"]:
                if m["material_id"] == "card_goals":
                    m["material_id"] = "CARD GOALS"
                    m["dependencies"] = ["Printer", "A4", "flipchart", "balloons"]
                if m["type"] == "audience_ballot":
                    m["used_in_blocks"] = ["Block_4"]
            data["voting"]["block_id"] = "Block-4"

        client = MutatingLLM(fixture(), {"scenario_plan": plan, "materials": materials})
        outcome = generator(client).run(request("ex1_knowledge_day"))
        self.assertEqual(outcome.project["status"], "completed", [i.to_dict() for v in outcome.variants for i in v.issues])
        variant = outcome.project["variants"][0]
        mats = {m["material_id"]: m for m in variant["materials"]}
        self.assertIn("card_goals", mats)
        self.assertEqual(mats["card_goals"]["dependencies"], ["printer", "paper", "whatman"])
        self.assertIn("Также понадобится: balloons.", mats["card_goals"]["teacher_notes"])
        codes = {i["code"] for i in variant["quality_report"]["issues"]}
        self.assertFalse(codes & {"DEP-UNKNOWN", "REF-MATERIAL", "REF-BLOCK", "VOTING-MATERIAL", "VOTING-BLOCK"})
        for block in variant["timeline"]:
            for mid in block["material_ids"]:
                self.assertIn(mid, mats)


class ProviderRetryTest(unittest.TestCase):
    def test_retryable_error_is_retried(self):
        """429 от провайдера: пауза и повтор, генерация завершается, повтор виден в трассе."""
        client = FlakyLLM(fixture(), "scenario_plan", LLMError("RATE_LIMITED", "429", retryable=True), fail_times=2)
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "runs" / "job"
            gen = generator(client, run_dir)
            outcome = gen.run(request("ex1_knowledge_day"), job_id="job")
            retries = [e for e in events(run_dir) if e["event_type"] == "llm_call_retry"]
        self.assertEqual(outcome.project["status"], "completed")
        self.assertEqual(gen.sleeps, [3.0, 10.0])
        self.assertEqual([(e["stage"], e["retry"], e["error_code"]) for e in retries],
                         [("scenario_plan", 1, "RATE_LIMITED"), ("scenario_plan", 2, "RATE_LIMITED")])

    def test_retries_exhausted(self):
        """Если провайдер так и не ответил, ошибка модели доходит до задачи как есть, без «готового» результата."""
        client = FlakyLLM(fixture(), "variation_plan", LLMError("MODEL_UNAVAILABLE", "503", retryable=True), fail_times=5)
        gen = generator(client)
        with self.assertRaises(LLMError) as ctx:
            gen.run(request("ex1_knowledge_day"))
        self.assertEqual(ctx.exception.code, "MODEL_UNAVAILABLE")
        self.assertEqual(gen.calls, 3)
        self.assertEqual(job_status.exception_error(ctx.exception),
                         {"code": "MODEL_UNAVAILABLE", "message": "503", "field": None, "retryable": True})

    def test_auth_error_not_retried(self):
        """Ошибка авторизации не повторяется: повтор ничего не изменит."""
        client = FlakyLLM(fixture(), "variation_plan", LLMError("MODEL_AUTH_ERROR", "401"), fail_times=1)
        gen = generator(client)
        with self.assertRaises(LLMError):
            gen.run(request("ex1_knowledge_day"))
        self.assertEqual((gen.calls, gen.sleeps), (1, []))

    def test_variant_stage_error_fails_only_variant(self):
        """Ошибка модели на этапе варианта: вариант failed с причиной, генерация не падает целиком."""
        client = FlakyLLM(fixture(), "materials", LLMError("MODEL_UNAVAILABLE", "503", retryable=True), fail_times=10)
        outcome = generator(client).run(request("ex1_knowledge_day"))
        self.assertEqual(outcome.project["status"], "failed")
        self.assertEqual(outcome.project["variants"], [])
        errors = job_status.variant_errors(outcome)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["code"], "VARIANT_GENERATION_FAILED")
        self.assertTrue(errors[0]["retryable"])


class JobStatusTest(unittest.TestCase):
    def issue(self, code):
        return SimpleNamespace(code=code, severity="critical", message=f"текст {code}", location="timeline.block_02")

    def test_variant_errors_format(self):
        """Ошибки по контракту 02: `field=None`, `retryable=True`, не больше 5 на вариант, причина из `variant.error`."""
        outcome = SimpleNamespace(variants=[
            SimpleNamespace(variant_id="v1", status="failed", error="x", issues=[self.issue(f"C{i}") for i in range(8)]),
            SimpleNamespace(variant_id="v2", status="failed", error="Этап materials: ответ не прошёл схему", issues=[]),
            SimpleNamespace(variant_id="v3", status="completed", error=None, issues=[]),
        ])
        errors = job_status.variant_errors(outcome)
        self.assertEqual([e["code"] for e in errors], ["C0", "C1", "C2", "C3", "C4", "VARIANT_GENERATION_FAILED"])
        self.assertTrue(all(e["field"] is None and e["retryable"] for e in errors))
        self.assertEqual(errors[-1]["message"], "Вариант v2: Этап materials: ответ не прошёл схему")
        self.assertEqual(job_status.variant_statuses(outcome, 3),
                         [{"variant_id": "v1", "status": "failed", "revision": 1},
                          {"variant_id": "v2", "status": "failed", "revision": 1},
                          {"variant_id": "v3", "status": "completed", "revision": 1}])

    def test_exception_errors(self):
        """Ошибка до вариантов: понятный код и текст без технических подробностей."""
        stage = job_status.exception_error(StageFailed("variation_plan", "Ответ не соответствует схеме: concepts.0..."))
        self.assertEqual(stage["code"], "OUTPUT_SCHEMA_INVALID")
        self.assertTrue(stage["retryable"])
        self.assertNotIn("concepts.0", stage["message"])
        internal = job_status.exception_error(KeyError("secret_path"))
        self.assertEqual(internal["code"], "INTERNAL_ERROR")
        self.assertNotIn("secret_path", internal["message"])


class BatchCliTest(unittest.TestCase):
    def test_batch_summary(self):
        """`python -m app batch` прогоняет набор запросов, печатает таблицу и сохраняет сводку."""
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"DATA_DIR": tmp}):
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["batch", str(EXAMPLES / "requests" / "ex1_knowledge_day.json"),
                             "--fixture", str(EXAMPLES / "golden" / "ex1_knowledge_day.json")])
            saved = list((Path(tmp) / "runs").glob("batch_*.json"))
            rows = json.loads(saved[0].read_text(encoding="utf-8"))
            journal = (Path(tmp) / "runs" / "runs.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(code, 0)
        self.assertIn("| ex1_knowledge_day.json | completed |", stdout.getvalue())
        self.assertIn("Итого: completed 1 из 1.", stdout.getvalue())
        self.assertEqual((rows[0]["status"], rows[0]["critical"]), ("completed", []))
        self.assertEqual(len(journal), 1)

    def test_matrix_requests_are_valid(self):
        """Запросы матрицы E2E (возраст, длительность, родители) проходят нормализацию."""
        from app.normalize import normalize
        files = sorted((EXAMPLES / "requests" / "matrix").glob("*.json"))
        self.assertGreaterEqual(len(files), 6)
        seen = set()
        for path in files:
            with self.subTest(path=path.name):
                n = normalize(json.loads(path.read_text(encoding="utf-8")), catalog(), settings())
                seen.add((n.age_group, n.duration_minutes))
                self.assertEqual([w.code for w in n.warnings], [])
        self.assertEqual({g for g, _ in seen}, {"1-4", "5-8", "9-11"})
        self.assertEqual({d for _, d in seen}, {30, 45, 60, 90})


if __name__ == "__main__":
    unittest.main()