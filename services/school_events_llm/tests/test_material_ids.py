"""Согласование ID материалов между планом, блоками и этапом материалов.

Регрессия по реальному прогону GigaChat-2-Max (2026-10-26): модель
- объявила материалы в плане, но не привязала их к блокам;
- на этапе блоков сослалась на расходник `paper` из ресурсов, а не на материал;
- на этапе материалов дописала к ID суффикс `_01`.
Раньше вариант падал с REF-MATERIAL даже после исправлений.
"""

import json
import tempfile
import unittest
from pathlib import Path

from app.generation.pipeline import Generator, reconcile_material_ids
from app.llm.client import LLMClient, LLMResult
from app.trace import RunTrace
from tests.helpers import ROOT, catalog, settings

REPLAY_DIR = ROOT / "tests" / "fixtures" / "replay_gigachat_material_ids"


class ReplayLLM(LLMClient):
    """Возвращает записанные ответы реальной модели по этапам; повторные вызовы этапа получают последний ответ."""

    model_key = "replay_gigachat_2_max"
    provider = "replay"
    # Ответы этапа выдаются по порядку вызовов, как при записи (варианты по очереди).
    parallel_variants_safe = False

    def __init__(self, directory: Path):
        self.responses: dict[str, list[str]] = {}
        for path in sorted(directory.glob("call_*.txt")):
            stage = path.stem.split("_", 2)[2]
            self.responses.setdefault(stage, []).append(path.read_text(encoding="utf-8"))
        self.calls: list[str] = []
        self._used: dict[str, int] = {}

    def health(self):
        return {"model_key": self.model_key, "provider": self.provider}

    def generate(self, *, messages, task_name, output_schema, max_tokens, temperature, meta=None) -> LLMResult:
        self.calls.append(task_name)
        items = self.responses[task_name]
        index = min(self._used.get(task_name, 0), len(items) - 1)
        self._used[task_name] = self._used.get(task_name, 0) + 1
        return LLMResult(text=items[index], model_key=self.model_key, provider=self.provider,
                         provider_model_id="GigaChat-2-Max", usage=None, latency_ms=0)


def replay_generator(client, trace=None) -> Generator:
    """Генератор для записанных прогонов: блоки одним вызовом, как в момент записи (до 60 минут)."""
    gen = Generator(settings(), catalog(), client, trace=trace)
    gen.defaults = {**gen.defaults, "block_detail_mode": "auto", "per_block_from_minutes": 60}
    return gen


def planned(*items):
    return [{"material_id": mid, "type": mtype, "purpose": "-"} for mid, mtype in items]


def material(mid, mtype, blocks):
    return {"material_id": mid, "type": mtype, "used_in_blocks": list(blocks)}


class ReconcileMaterialIdsTest(unittest.TestCase):
    def test_suffix_is_removed(self):
        """`parent_instruction_01` возвращается к ID из плана `parent_instruction`."""
        mats = [material("parent_instruction_01", "parent_instruction", ["block_02"])]
        mapping = reconcile_material_ids(planned(("parent_instruction", "parent_instruction")), mats)
        self.assertEqual(mapping, {"parent_instruction_01": "parent_instruction"})
        self.assertEqual(mats[0]["material_id"], "parent_instruction")

    def test_unique_type_match(self):
        """Материал с другим ID, но единственным подходящим типом получает ID из плана."""
        mats = [material("ballot_for_parents", "audience_ballot", ["block_04"])]
        mapping = reconcile_material_ids(planned(("votes", "audience_ballot")), mats)
        self.assertEqual(mapping, {"ballot_for_parents": "votes"})

    def test_exact_ids_untouched_and_extras_kept(self):
        """Совпадающие ID не трогаются, лишние материалы без пары остаются как есть."""
        mats = [material("card_task", "activity_card", ["block_02"]), material("paper_01", "props_checklist", ["block_02"])]
        mapping = reconcile_material_ids(planned(("card_task", "activity_card")), mats)
        self.assertEqual(mapping, {})
        self.assertEqual([m["material_id"] for m in mats], ["card_task", "paper_01"])

    def test_ambiguous_type_is_not_guessed(self):
        """Если подходящих по типу материалов в плане несколько, ID не угадываются."""
        mats = [material("card_x", "activity_card", ["block_02"])]
        mapping = reconcile_material_ids(planned(("card_a", "activity_card"), ("card_b", "activity_card")), mats)
        self.assertEqual(mapping, {})

    def test_no_duplicate_targets(self):
        """Два материала не получают один и тот же ID из плана."""
        mats = [material("ballot_01", "audience_ballot", ["block_04"]), material("ballot_02", "audience_ballot", ["block_05"])]
        mapping = reconcile_material_ids(planned(("ballot", "audience_ballot")), mats)
        self.assertEqual(mapping, {"ballot_01": "ballot"})
        self.assertEqual(sorted(m["material_id"] for m in mats), ["ballot", "ballot_02"])


class ReplayRealModelTest(unittest.TestCase):
    def test_gigachat_trace_now_completes_without_repairs(self):
        """Записанные ответы GigaChat проходят проверки без дополнительных вызовов модели."""
        raw = json.loads((REPLAY_DIR / "request.json").read_text(encoding="utf-8"))
        client = ReplayLLM(REPLAY_DIR)
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            outcome = replay_generator(client, trace=RunTrace(run_dir, full_prompts=False, full_responses=False, secrets=[])).run(raw)
            events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        variant = outcome.variants[0]
        critical = [f"{i.code}:{i.location}" for i in variant.issues if i.severity == "critical"]
        self.assertEqual(critical, [])
        self.assertEqual(outcome.project["status"], "completed")
        self.assertEqual(client.calls, ["variation_plan", "scenario_plan", "scenario_blocks", "materials"])

        result = outcome.project["variants"][0]
        material_ids = {m["material_id"] for m in result["materials"]}
        self.assertEqual(material_ids, {"parent_instruction", "audience_ballot", "award_instruction"})
        by_block = {b["block_id"]: b["material_ids"] for b in result["timeline"]}
        self.assertEqual(by_block["block_02"], ["parent_instruction"])
        self.assertEqual(by_block["block_04"], ["audience_ballot"])
        self.assertEqual(by_block["block_05"], ["award_instruction"])
        for block in result["timeline"]:
            self.assertNotIn("paper", block["material_ids"])
        # Технические исправления пишутся в трассу, а не в отчёт для педагога.
        renamed = next(e for e in events if e["event_type"] == "material_ids_reconciled")["renamed"]
        self.assertEqual(renamed, {"parent_instruction_01": "parent_instruction", "audience_ballot_01": "audience_ballot",
                                   "award_instruction_01": "award_instruction"})
        dropped = next(e for e in events if e["event_type"] == "block_material_refs_dropped")["refs"]
        self.assertIn({"block_id": "block_02", "material_id": "paper"}, dropped)
        self.assertNotIn("MAT", " ".join(i["code"] for i in result["quality_report"]["issues"]))

        # Модель указала по одной роли на блок; педагог, ученики и родители досчитываются программой.
        all_blocks = [b["block_id"] for b in result["timeline"]]
        for role in result["roles"]:
            self.assertEqual(role["block_ids"], all_blocks, role["role_id"])
        self.assertEqual(result["parent_participation_plan"]["voting"]["voters_count_planned"], 10)
        added = next(e for e in events if e["event_type"] == "block_roles_completed")["added"]
        self.assertEqual(added["pupils_all"], ["block_01", "block_02", "block_05"])


if __name__ == "__main__":
    unittest.main()