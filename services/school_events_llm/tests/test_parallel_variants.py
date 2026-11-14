"""Варианты одной генерации одновременно (BUG-22, QA 14.11).

Три варианта шли по очереди 17 минут (415 + 326 + 297 с) и не успевали за 15-минутный срок ожидания
фронтенда. Варианты независимы, поэтому до `max_parallel_variants` (3) создаются одновременно.
Проверяется: варианты действительно идут одновременно, результат в порядке v1, v2, v3, трасса цельная
(номера вызовов не повторяются, события и токены не теряются), неустранимая ошибка модели останавливает
соседние варианты, а клиенты с записанными ответами и `1` в настройке работают по очереди, как раньше.
"""

import copy
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from app.generation.pipeline import Generator
from app.llm.client import LLMError
from app.llm.fixture import FixtureLLM
from app.settings import Settings
from app.trace import RunTrace
from tests.helpers import ROOT, catalog, golden, request, settings
from tests.test_material_ids import ReplayLLM


def goldens(count: int) -> list[dict]:
    """Эталон Дня знаний и его копии с другими концепциями: варианты должны отличаться."""
    base = golden("ex1_knowledge_day")
    result = [base]
    for title, mechanic in (("Командная игра знаний", "team_game"), ("Мастерская класса", "creative_workshop"))[: count - 1]:
        item = copy.deepcopy(base)
        item["concept"]["title"] = title
        item["concept"]["primary_mechanic"] = mechanic
        result.append(item)
    return result


class SlowFixture(FixtureLLM):
    """Эталонные ответы с задержкой; считает, сколько обращений к модели идёт одновременно.

    `fail` - (вариант, этап, ошибка): этот вызов падает сразу, остальные идут как обычно.
    """

    def __init__(self, items: list[dict], delay: float = 0.04, fail: tuple[str, str, LLMError] | None = None):
        super().__init__(items)
        self.delay, self.fail = delay, fail
        self.lock = threading.Lock()
        self.current = self.peak = 0

    def generate(self, **kwargs):
        variant = (kwargs.get("meta") or {}).get("variant_id")
        if self.fail and (variant, kwargs["task_name"]) == self.fail[:2]:
            raise self.fail[2]
        with self.lock:
            self.current += 1
            self.peak = max(self.peak, self.current)
        try:
            time.sleep(self.delay)
            return super().generate(**kwargs)
        finally:
            with self.lock:
                self.current -= 1


def run(client, *, parallel: int, count: int = 3, run_dir: Path | None = None):
    raw = request("ex1_knowledge_day")
    raw["generation"]["variants_count"] = count
    trace = RunTrace(run_dir, full_prompts=False, full_responses=False, secrets=[]) if run_dir else None
    gen = Generator(settings(), catalog(), client, trace=trace, parallel_variants=parallel)
    return gen, gen.run(raw)


def events(run_dir: Path) -> list[dict]:
    return [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]


class ParallelVariantsTest(unittest.TestCase):
    def test_three_variants_at_once(self):
        """Три варианта идут одновременно; результат в порядке v1, v2, v3; трасса цельная."""
        client = SlowFixture(goldens(3))
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            gen, outcome = run(client, parallel=3, run_dir=run_dir)
            self.assertEqual(outcome.project["status"], "completed")
            self.assertEqual([v.variant_id for v in outcome.variants], ["v1", "v2", "v3"])
            self.assertEqual([v["variant_id"] for v in outcome.project["variants"]], ["v1", "v2", "v3"])
            self.assertGreaterEqual(client.peak, 2)
            log = events(run_dir)
            started = [e["call_id"] for e in log if e["event_type"] == "llm_call_started"]
            finished = [e for e in log if e["event_type"] in ("llm_call_completed", "llm_call_invalid")]
            # Номера вызовов не повторяются, папка на каждый вызов, счётчики сходятся.
            self.assertEqual(len(started), len(set(started)))
            self.assertEqual(sorted(p.name for p in (run_dir / "calls").iterdir()), sorted(started))
            self.assertEqual((gen.calls, gen.tokens.calls, len(finished)), (len(started),) * 3)
            self.assertEqual(sorted(e["variant_id"] for e in log if e["event_type"] == "variant_completed"), ["v1", "v2", "v3"])
            for vid in ("v1", "v2", "v3"):
                self.assertTrue((run_dir / "variants" / vid / "variant_package.json").is_file(), vid)

    def test_faster_than_one_by_one(self):
        """С одинаковой задержкой ответа три варианта одновременно заметно быстрее, чем по очереди."""
        times = {}
        for parallel in (1, 3):
            client = SlowFixture(goldens(3), delay=0.05)
            started = time.monotonic()
            _, outcome = run(client, parallel=parallel)
            times[parallel] = time.monotonic() - started
            self.assertEqual(outcome.project["status"], "completed")
            if parallel == 1:
                self.assertEqual(client.peak, 1)
        self.assertLess(times[3], times[1] * 0.75, times)

    def test_one_means_one_by_one(self):
        """`max_parallel_variants: 1` - варианты по очереди, как до правки."""
        client = SlowFixture(goldens(2), delay=0.01)
        _, outcome = run(client, parallel=1, count=2)
        self.assertEqual(client.peak, 1)
        self.assertEqual([v.status for v in outcome.variants], ["completed", "completed"])

    def test_fatal_model_error_stops_neighbours(self):
        """Ключ не подходит у варианта v2: v1 и v3 останавливаются на следующем обращении к модели,
        генерация завершается, а не ждёт их до конца; в трассе видно, кто остановлен и почему."""
        error = LLMError("MODEL_AUTH_ERROR", "Ключ не подходит")
        client = SlowFixture(goldens(3), delay=0.05, fail=("v2", "scenario_plan", error))
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            gen, outcome = run(client, parallel=3, run_dir=run_dir)
            self.assertEqual([(v.variant_id, v.status) for v in outcome.variants], [("v2", "failed")])
            self.assertIn("Ключ не подходит", outcome.variants[0].error)
            log = events(run_dir)
            self.assertEqual(sorted(e["variant_id"] for e in log if e["event_type"] == "variant_stopped"), ["v1", "v3"])
            # Остановленные варианты не дошли до материалов.
            self.assertNotIn("materials", [c["task"] for c in client.calls])

    def test_ordinary_failure_does_not_stop_neighbours(self):
        """Вариант, не прошедший схему, - обычная неудача: соседние варианты доделываются."""
        bad = copy.deepcopy(goldens(2)[1])
        values = bad["variant_package"]["variant"]["concept"]["values_to_mechanics"]
        bad["variant_package"]["variant"]["concept"]["values_to_mechanics"] = values[:1]
        _, outcome = run(SlowFixture([goldens(1)[0], bad], delay=0.01), parallel=3, count=2)
        self.assertEqual([v.status for v in outcome.variants], ["completed", "failed"])
        self.assertEqual(outcome.project["status"], "partial")


class WhenOneByOneTest(unittest.TestCase):
    def test_recorded_answers_and_broken_fixture(self):
        """Записанные ответы выдаются по порядку вызовов, битые ответы эталона - первым вызовам этапа:
        таким клиентам варианты по очереди, иначе непонятно, какому варианту достанется ответ."""
        gen = Generator(settings(), catalog(), ReplayLLM(ROOT / "tests" / "fixtures" / "replay_gigachat_bug17_parents"),
                        parallel_variants=3)
        self.assertEqual(gen._variant_workers(3), 1)
        gen = Generator(settings(), catalog(), FixtureLLM(goldens(1), broken={"materials": 1}), parallel_variants=3)
        self.assertEqual(gen._variant_workers(3), 1)
        gen = Generator(settings(), catalog(), FixtureLLM(goldens(1)), parallel_variants=3)
        self.assertEqual((gen._variant_workers(1), gen._variant_workers(2), gen._variant_workers(3)), (1, 2, 3))

    def test_service_config(self):
        """В `config/service.json` - 3 варианта одновременно; генератор берёт значение оттуда."""
        self.assertEqual(Settings(root=ROOT, env={}).service()["max_parallel_variants"], 3)
        self.assertEqual(Generator(settings(), catalog(), FixtureLLM(goldens(1))).parallel_variants, 3)


if __name__ == "__main__":
    unittest.main()