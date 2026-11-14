"""Параллельная работа сервиса: генерации без очереди до предела из config/service.json, изоляция задач.

Сервисом пользуется вся школа: одновременно идут генерации разных педагогов. Проверяется:
- до `max_parallel_generations` генераций идут сразу, остальные ждут (`queued`), сверх очереди - 503 SERVICE_BUSY;
- обращения к модели ограничены `max_parallel_llm_requests`, к локальной модели - `local_model_max_parallel`;
- задачи не смешиваются: у каждой свой запрос, свой результат, своя трасса; каталог не меняется;
- журнал runs.jsonl не портится при одновременной записи;
- старые статусы и проекты убираются из памяти через `results_keep_hours`.
"""

import copy
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.http_api import create_app
from app.llm import limits
from app.llm.client import LLMError, OpenAICompatibleClient
from app.llm.fixture import FixtureLLM
from app.settings import Settings
from app.trace import RunTrace
from tests.helpers import ROOT

EXAMPLES = {
    "ex1_knowledge_day": "День знаний",
    "ex2_mothers_day": "День матери",
    "ex3_labour_day": "Праздник Весны и Труда",
}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


GOLDENS = {name: _load(ROOT / "examples" / "golden" / f"{name}.json") for name in EXAMPLES}
REQUESTS = {name: _load(ROOT / "examples" / "requests" / f"{name}.json") for name in EXAMPLES}


class Probe:
    """Считает, сколько обращений к модели идёт одновременно."""

    def __init__(self):
        self.lock = threading.Lock()
        self.current = 0
        self.peak = 0
        self.calls = 0

    def __enter__(self):
        with self.lock:
            self.current += 1
            self.calls += 1
            self.peak = max(self.peak, self.current)

    def __exit__(self, *exc):
        with self.lock:
            self.current -= 1


class EventAwareFixture(FixtureLLM):
    """Отвечает эталоном того события, о котором промпт. Если промпт чужой задачи - ответ не подойдёт."""

    def __init__(self, probe: Probe, delay: float = 0.03, gate: threading.Event | None = None):
        super().__init__(list(GOLDENS.values()), model_key="fixture_parallel")
        self.probe, self.delay, self.gate = probe, delay, gate

    def generate(self, *, messages, task_name, output_schema, max_tokens, temperature, meta=None):
        text = "\n".join(m["content"] for m in messages)
        name = next(n for n, title in EXAMPLES.items() if f"Событие: {title}" in text or f"**Событие:** {title}" in text)
        with self.probe:
            if self.gate is not None:
                self.gate.wait(timeout=10)
            time.sleep(self.delay)
            self.goldens = [GOLDENS[name]]
            return super().generate(messages=messages, task_name=task_name, output_schema=output_schema,
                                    max_tokens=max_tokens, temperature=temperature, meta=meta)


def _settings(tmp: str) -> Settings:
    return Settings(root=ROOT, env={"DATA_DIR": tmp, "LOG_FULL_PROMPTS": "false", "LOG_FULL_RESPONSES": "false"})


def _wait_all(client: TestClient, job_ids, timeout=60.0):
    deadline = time.monotonic() + timeout
    while True:
        jobs = [client.get(f"/api/v1/generations/{job_id}").json() for job_id in job_ids]
        if all(job["status"] not in ("queued", "running") for job in jobs):
            return jobs
        if time.monotonic() > deadline:
            raise AssertionError("Генерации не завершились вовремя")
        time.sleep(0.05)


class ParallelGenerationsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(limits.configure, Settings(root=ROOT, env={}).service())

    def app(self, probe, **config):
        gate = config.pop("gate", None)
        delay = config.pop("delay", 0.03)
        app = create_app(_settings(self.tmp.name), client_factory=lambda: EventAwareFixture(probe, delay, gate),
                         service_config=config)
        self.addCleanup(app.state.executor.shutdown, wait=True)
        return app

    def test_thirty_at_once_rest_wait(self):
        """40 генераций при пределе 30: 30 идут сразу, 10 ждут, все завершаются, ничего не смешивается."""
        probe = Probe()
        app = self.app(probe, max_parallel_generations=30, max_waiting_generations=100, delay=0.25)
        client = TestClient(app)
        names = [list(EXAMPLES)[i % 3] for i in range(40)]
        accepted = []
        for name in names:
            response = client.post("/api/v1/generations", json=copy.deepcopy(REQUESTS[name]))
            self.assertEqual(response.status_code, 202)
            accepted.append(response.json())
        load = client.get("/api/v1/load").json()
        self.assertEqual(load["max_parallel_generations"], 30)
        self.assertGreater(load["waiting_generations"], 0)

        jobs = _wait_all(client, [a["job_id"] for a in accepted])
        self.assertEqual({job["status"] for job in jobs}, {"completed"})
        self.assertEqual(probe.peak, 30)

        for name, item in zip(names, accepted):
            project = client.get(f"/api/v1/projects/{item['project_id']}").json()
            self.assertEqual(project["job_id"], item["job_id"])
            self.assertEqual(project["input"]["event_id"], REQUESTS[name]["event_id"])
            self.assertEqual(project["input"]["pupils_count"], REQUESTS[name]["pupils_count"])
            self.assertEqual(project["variants"][0]["title"], GOLDENS[name]["variant_package"]["variant"]["title"])

        runs = Path(self.tmp.name) / "runs"
        self.assertEqual(len([p for p in runs.iterdir() if p.is_dir()]), 40)
        lines = (runs / "runs.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 40)
        self.assertEqual({json.loads(line)["job_id"] for line in lines}, {a["job_id"] for a in accepted})
        load = client.get("/api/v1/load").json()
        self.assertEqual((load["running_generations"], load["waiting_generations"]), (0, 0))

    def test_busy_when_queue_full(self):
        """Предел 2 и очередь 1: четвёртая задача получает 503 SERVICE_BUSY с retryable=true."""
        probe, gate = Probe(), threading.Event()
        app = self.app(probe, max_parallel_generations=2, max_waiting_generations=1, gate=gate)
        client = TestClient(app)
        ids = [client.post("/api/v1/generations", json=REQUESTS["ex1_knowledge_day"]).json()["job_id"] for _ in range(3)]
        busy = client.post("/api/v1/generations", json=REQUESTS["ex1_knowledge_day"])
        self.assertEqual(busy.status_code, 503)
        self.assertEqual(busy.json()["error"]["code"], "SERVICE_BUSY")
        self.assertTrue(busy.json()["error"]["retryable"])
        gate.set()
        self.assertEqual({job["status"] for job in _wait_all(client, ids)}, {"completed"})
        self.assertEqual(client.post("/api/v1/generations", json=REQUESTS["ex1_knowledge_day"]).status_code, 202)

    def test_status_answers_while_all_slots_busy(self):
        """Пока все места заняты долгими генерациями, статус и нагрузка отвечают сразу."""
        probe, gate = Probe(), threading.Event()
        app = self.app(probe, max_parallel_generations=3, max_waiting_generations=5, gate=gate)
        client = TestClient(app)
        ids = [client.post("/api/v1/generations", json=REQUESTS["ex2_mothers_day"]).json()["job_id"] for _ in range(5)]
        started = time.monotonic()
        statuses = [client.get(f"/api/v1/generations/{job_id}").json()["status"] for job_id in ids]
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(statuses.count("queued"), 2)
        gate.set()
        _wait_all(client, ids)

    def test_catalog_not_changed_by_parallel_jobs(self):
        probe = Probe()
        app = self.app(probe, max_parallel_generations=10)
        before = json.dumps([app.state.catalog.events, app.state.catalog.fragments], sort_keys=True, ensure_ascii=False)
        client = TestClient(app)
        ids = [client.post("/api/v1/generations", json=REQUESTS[name]).json()["job_id"] for name in list(EXAMPLES) * 4]
        _wait_all(client, ids)
        after = json.dumps([app.state.catalog.events, app.state.catalog.fragments], sort_keys=True, ensure_ascii=False)
        self.assertEqual(before, after)

    def test_old_results_removed_from_memory(self):
        probe = Probe()
        app = self.app(probe, results_keep_hours=0.0000001)
        client = TestClient(app)
        first = client.post("/api/v1/generations", json=REQUESTS["ex1_knowledge_day"]).json()
        _wait_all(client, [first["job_id"]])
        time.sleep(0.01)
        client.post("/api/v1/generations", json=REQUESTS["ex1_knowledge_day"])
        self.assertEqual(client.get(f"/api/v1/generations/{first['job_id']}").status_code, 404)
        self.assertEqual(client.get(f"/api/v1/projects/{first['project_id']}").status_code, 404)


class LLMSlotsTest(unittest.TestCase):
    def setUp(self):
        self.addCleanup(limits.configure, Settings(root=ROOT, env={}).service())

    @staticmethod
    def run_threads(count, target):
        threads = [threading.Thread(target=target) for _ in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

    def test_remote_and_local_limits(self):
        limits.configure({"max_parallel_llm_requests": 3, "local_model_max_parallel": 1})
        remote, local = Probe(), Probe()

        def remote_call():
            with limits.llm_request_slot(local=False), remote:
                time.sleep(0.05)

        def local_call():
            with limits.llm_request_slot(local=True), local:
                time.sleep(0.02)

        self.run_threads(10, remote_call)
        self.assertEqual(remote.peak, 3)
        self.run_threads(5, local_call)
        self.assertEqual(local.peak, 1)

    def test_client_calls_use_slots(self):
        """Реальный клиент OpenAI-совместимой модели (GigaChat через LiteLLM) не превышает общий предел."""
        limits.configure({"max_parallel_llm_requests": 2})
        probe = Probe()
        client = OpenAICompatibleClient("x", {"base_url": "http://gateway.invalid/v1", "model_id": "m", "local": False}, None, None)

        def fake_call(body):
            with probe:
                time.sleep(0.05)
            return 200, {"choices": [{"message": {"content": "{}"}}], "usage": {}}

        client._call = fake_call

        def one():
            client.generate(messages=[{"role": "user", "content": "x"}], task_name="t", output_schema=None, max_tokens=10, temperature=0)

        self.run_threads(6, one)
        self.assertEqual(probe.peak, 2)
        self.assertEqual(probe.calls, 6)

    def test_slot_timeout_is_retryable_busy(self):
        limits.configure({"max_parallel_llm_requests": 1, "llm_slot_wait_seconds": 0.1})
        client = OpenAICompatibleClient("x", {"base_url": "http://gateway.invalid/v1", "model_id": "m", "local": False}, None, None)
        client._call = lambda body: (200, {"choices": [{"message": {"content": "{}"}}]})
        with limits.llm_request_slot():
            with self.assertRaises(LLMError) as ctx:
                client.generate(messages=[{"role": "user", "content": "x"}], task_name="t", output_schema=None, max_tokens=10, temperature=0)
        self.assertEqual(ctx.exception.code, "SERVICE_BUSY")
        self.assertTrue(ctx.exception.retryable)


class GatewayCacheTest(unittest.TestCase):
    """Шлюз LiteLLM кэширует одинаковые запросы: генерации и исправления должны получать новый ответ модели."""

    PROFILE = {"base_url": "http://gateway.invalid/v1", "model_id": "GigaChat-2-Max", "local": False, "gateway_cache": True}

    def bodies(self, cfg, metas, statuses=None, errors=None):
        client = OpenAICompatibleClient("urfu", cfg, "k", None)
        sent, statuses = [], list(statuses or [])

        def fake_call(body):
            sent.append(json.loads(json.dumps(body)))
            status = statuses.pop(0) if statuses else 200
            return status, (errors or {}).get(status, {"choices": [{"message": {"content": "{}"}}]})

        client._call = fake_call
        for meta in metas:
            client.generate(messages=[{"role": "user", "content": "Сценарий"}], task_name="t", output_schema=None,
                            max_tokens=10, temperature=0.4, meta=meta)
        return sent

    def test_every_call_unique_and_no_cache(self):
        sent = self.bodies(self.PROFILE, [{"job_id": "job_a", "call_id": "call_0001"}, {"job_id": "job_a", "call_id": "call_0002"},
                                          {"job_id": "job_b", "call_id": "call_0001"}])
        self.assertTrue(all(body["cache"] == {"no-cache": True, "no-store": True} for body in sent))
        prompts = [body["messages"][-1]["content"] for body in sent]
        self.assertEqual(len(set(prompts)), 3)
        self.assertTrue(prompts[0].startswith("Сценарий"))

    def test_switch_off_and_other_providers(self):
        off = self.bodies({**self.PROFILE, "cache_bypass": False}, [{"job_id": "j", "call_id": "c"}])[0]
        self.assertNotIn("cache", off)
        self.assertEqual(off["messages"][-1]["content"], "Сценарий")
        local = self.bodies({**self.PROFILE, "gateway_cache": False}, [{"job_id": "j", "call_id": "c"}])[0]
        self.assertNotIn("cache", local)
        self.assertEqual(local["messages"][-1]["content"], "Сценарий")

    def test_gateway_without_cache_param(self):
        """Шлюз ответил 400 на параметр кэша: повтор без него, отметка вызова остаётся."""
        sent = self.bodies(self.PROFILE, [{"job_id": "j", "call_id": "c1"}, {"job_id": "j", "call_id": "c2"}], statuses=[400])
        self.assertIn("cache", sent[0])
        self.assertNotIn("cache", sent[1])
        self.assertNotIn("cache", sent[2])
        self.assertIn("c2", sent[2]["messages"][-1]["content"])

    def test_reasoning_effort(self):
        """Рассуждения GigaChat: уровень этапа из meta или профиля; не для моделей с выключенными рассуждениями;
        шлюз ответил 400 на параметр - повтор без него и дальше без него (проверка шлюза УрФУ 14.11: параметр принимается)."""
        profile = {**self.PROFILE, "reasoning_mode": "provider_default"}
        sent = self.bodies(profile, [{"call_id": "c1", "reasoning_effort": "medium"}, {"call_id": "c2"}])
        self.assertEqual(sent[0]["reasoning_effort"], "medium")
        self.assertNotIn("reasoning_effort", sent[1])
        self.assertEqual(self.bodies({**profile, "reasoning_effort": "low"}, [{"call_id": "c"}])[0]["reasoning_effort"], "low")
        self.assertNotIn("reasoning_effort", self.bodies({**profile, "reasoning_mode": "disabled"}, [{"reasoning_effort": "high"}])[0])
        sent = self.bodies(profile, [{"reasoning_effort": "medium"}, {"reasoning_effort": "medium"}], statuses=[400],
                           errors={400: {"error": {"message": "Unsupported parameter: reasoning_effort"}}})
        self.assertEqual(["reasoning_effort" in body for body in sent], [True, False, False])
        self.assertTrue(all("cache" in body for body in sent))  # обход кэша не отключился

    def test_reasoning_content_kept_apart(self):
        client = OpenAICompatibleClient("urfu", {**self.PROFILE, "reasoning_mode": "provider_default"}, "k", None)
        client._call = lambda body: (200, {"choices": [{"message": {"content": '{"a": 1}', "reasoning_content": "4 × 3 = 12, 12 + 10 = 22"}}]})
        result = client.generate(messages=[{"role": "user", "content": "x"}], task_name="t", output_schema=None, max_tokens=10,
                                 temperature=0.4, meta={"reasoning_effort": "medium"})
        self.assertEqual(result.text, '{"a": 1}')
        self.assertEqual(result.reasoning, "4 × 3 = 12, 12 + 10 = 22")
        self.assertEqual(result.request_params["reasoning_effort"], "medium")

    def test_profiles_and_setting(self):
        models = Settings(root=ROOT, env={}).models()["models"]
        self.assertTrue(all(cfg.get("gateway_cache") for key, cfg in models.items() if cfg.get("base_url_env") == "LITELLM_BASE_URL"))
        self.assertFalse(models["qwen_local_9b"].get("gateway_cache"))
        self.assertTrue(Settings(root=ROOT, env={}).service()["llm_cache_bypass"])

    def test_repair_attempts_differ(self):
        """Повторы исправления одного этапа идут с разными call_id: шлюз не отдаст прошлый неверный ответ."""
        from app.generation.pipeline import Generator
        from tests.helpers import catalog, settings

        seen = []

        class Recorder(FixtureLLM):
            def generate(self, **kwargs):
                seen.append(kwargs["meta"].get("call_id"))
                return super().generate(**kwargs)

        Generator(settings(), catalog(), Recorder([GOLDENS["ex1_knowledge_day"]], broken={"scenario_plan": 2})).run(
            copy.deepcopy(REQUESTS["ex1_knowledge_day"]))
        self.assertEqual(len(seen), len(set(seen)))
        self.assertGreater(len(seen), 4)


class RunLogTest(unittest.TestCase):
    def test_parallel_writes_keep_lines_whole(self):
        with tempfile.TemporaryDirectory() as tmp:
            traces = [RunTrace(Path(tmp) / f"job_{i}", full_prompts=False, full_responses=False) for i in range(40)]
            text = "Сценарий " * 400

            def write(trace):
                for _ in range(5):
                    trace.append_run_log({"job_id": trace.run_dir.name, "text": text})

            threads = [threading.Thread(target=write, args=(trace,)) for trace in traces]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            lines = (Path(tmp) / "runs.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 200)
            self.assertTrue(all(json.loads(line)["text"] == text for line in lines))


class ServiceConfigTest(unittest.TestCase):
    def test_defaults_from_json(self):
        config = Settings(root=ROOT, env={}).service()
        self.assertEqual(config["max_parallel_generations"], 30)
        self.assertEqual(config["max_parallel_llm_requests"], 30)
        self.assertEqual(config["local_model_max_parallel"], 1)


if __name__ == "__main__":
    unittest.main()