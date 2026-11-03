# -*- coding: utf-8 -*-
"""E2E-прогон по API против живого Backend в режиме llm_service.

Перед запуском:
    cd services/school_events_llm; python -m app serve
    GENERATOR_MODE=llm_service python -m uvicorn backend.main:app --port 8000

Режим выбирается окружением LLM-сервиса: реальная модель (`.env`) или fixture.
Для реальной модели один кейс идёт 2–4 минуты, таймаут по умолчанию 900 секунд.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
INPUTS = sorted(Path("qa/tests/fixtures/inputs").glob("*.json"))
TIMEOUT = float(os.getenv("E2E_TIMEOUT", "900"))
RESULT_FILE = Path(os.getenv("E2E_RESULT_FILE", "qa/docs/testing/e2e_results_latest.json"))
NEGATIVES = {
    "unknown_event": {
        "event_id": "ural_culture", "region_id": "RU-SVE", "grade_group": "5-8",
        "pupils_count": 20, "duration_minutes": 45, "format": "class_hour",
    },
    "wrong_format": {
        "event_id": "last_bell", "region_id": "RU-SVE", "grade_group": "5-8",
        "pupils_count": 20, "duration_minutes": 45, "format": "interactive_lesson",
    },
}


def wait_job(client: httpx.Client, status_url: str, timeout: float) -> dict:
    """Ждёт терминальный статус задания, чтобы не проверять промежуточный running."""
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        last = client.get(BASE + status_url).json()
        if last.get("status") in {"completed", "partial", "failed", "blocked"}:
            return last
        time.sleep(3)
    return last


def summarize(project: dict) -> dict:
    """Собирает минимальные проверки, которые нужны приёмке."""
    variants = project.get("variants") or []
    result = {"project_status": project.get("status"), "variants": len(variants), "checks": []}
    for variant in variants:
        timeline = variant.get("timeline") or []
        quality = variant.get("quality_report") or {}
        result["checks"].append({
            "id": variant.get("variant_id"),
            "title": variant.get("title"),
            "blocks": len(timeline),
            "sum_min": sum(b.get("duration_minutes", 0) for b in timeline),
            "start_zero": bool(timeline) and timeline[0].get("start_minute") == 0,
            "scripts_ok": all((b.get("teacher_script") or "").strip() for b in timeline),
            "quality_status": quality.get("status"),
            "issues": [
                {"code": i.get("code"), "severity": i.get("severity")}
                for i in (quality.get("issues") or [])
            ],
        })
    return result


def main() -> None:
    rows: list[dict] = []
    with httpx.Client(timeout=300) as client:
        for path in INPUTS:
            request = json.loads(path.read_text(encoding="utf-8"))
            row: dict = {"case": path.name}
            started = time.time()
            try:
                response = client.post(BASE + "/api/v1/generations", json=request)
                row["http"] = response.status_code
                if response.status_code != 202:
                    row["error"] = response.text[:300]
                    rows.append(row)
                    continue
                accepted = response.json()
                job = wait_job(client, accepted["status_url"], TIMEOUT)
                project = client.get(BASE + accepted["project_url"]).json()
                row.update(summarize(project))
                row["job_status"] = job.get("status")
                row["job_errors"] = job.get("errors")
                row["job_warnings"] = job.get("warnings")
            except Exception as exc:  # noqa: BLE001
                row["error"] = f"{type(exc).__name__}: {exc}"
            row["duration_sec"] = round(time.time() - started, 1)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)

        for name, request in NEGATIVES.items():
            response = client.post(BASE + "/api/v1/generations", json=request)
            rows.append({"case": name, "http": response.status_code, "body": response.text[:300]})

    RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULT_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SAVED", RESULT_FILE, flush=True)


if __name__ == "__main__":
    main()
