# -*- coding: utf-8 -*-
"""Регрессия API: варианты, родители, ресурсы, размер класса.

Запускается против живого Backend (GENERATOR_MODE=llm_service) и реальной модели.
Сохраняет результат в JSON и печатает строки по мере выполнения.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
RUNS = Path("services/school_events_llm/data/runs/runs.jsonl")
OUT = Path(r"C:\Users\user\AppData\Local\Temp\opencode\regression_results.json")

BASE_REQ = {
    "region_id": "RU-SVE",
    "resources": {
        "projector": True, "printer": True, "internet": True, "audio": True,
        "room": "classroom", "available_materials": ["paper", "markers"],
    },
    "teacher_preferences": {
        "style": "interactive", "script_detail": "standard", "difficulty": "standard",
        "interaction_level": "medium", "group_work": True, "preparation_effort": "minimal",
        "notes": None,
    },
}

CASES = [
    ("variants_1", dict(event_id="knowledge_day", grade=6, grade_group="5-8", pupils_count=27,
                        duration_minutes=45, format="class_hour",
                        participants={"teachers_count": 1, "parents_enabled": True, "parents_count": 12,
                                      "parent_roles": ["helper", "audience"], "parent_audience_engagement": "audience_award"},
                        generation={"variants_count": 1, "language": "ru"})),
    ("variants_2", dict(event_id="knowledge_day", grade=6, grade_group="5-8", pupils_count=27,
                        duration_minutes=45, format="class_hour",
                        participants={"teachers_count": 1, "parents_enabled": True, "parents_count": 12,
                                      "parent_roles": ["helper", "audience"], "parent_audience_engagement": "audience_award"},
                        generation={"variants_count": 2, "language": "ru"})),
    ("variants_3", dict(event_id="knowledge_day", grade=6, grade_group="5-8", pupils_count=27,
                        duration_minutes=45, format="class_hour",
                        participants={"teachers_count": 1, "parents_enabled": True, "parents_count": 12,
                                      "parent_roles": ["helper", "audience"], "parent_audience_engagement": "audience_award"},
                        generation={"variants_count": 3, "language": "ru"})),
    ("parents_off", dict(event_id="teachers_day", grade_group="5-8", pupils_count=22,
                         duration_minutes=45, format="class_hour",
                         participants={"teachers_count": 1, "parents_enabled": False, "parents_count": 0,
                                       "parent_roles": [], "parent_audience_engagement": "none"},
                         generation={"variants_count": 1, "language": "ru"})),
    ("minimal_resources", dict(event_id="teachers_day", grade_group="1-4", pupils_count=16,
                               duration_minutes=30, format="class_hour",
                               participants={"teachers_count": 1, "parents_enabled": False, "parents_count": 0,
                                             "parent_roles": [], "parent_audience_engagement": "none"},
                               resources={"projector": False, "printer": False, "internet": False,
                                          "audio": False, "room": "classroom", "available_materials": []},
                               generation={"variants_count": 1, "language": "ru"})),
    ("small_class_1", dict(event_id="knowledge_day", grade_group="1-4", pupils_count=1,
                           duration_minutes=30, format="class_hour",
                           participants={"teachers_count": 1, "parents_enabled": False, "parents_count": 0,
                                         "parent_roles": [], "parent_audience_engagement": "none"},
                           generation={"variants_count": 1, "language": "ru"})),
    ("large_class_35", dict(event_id="new_year", grade_group="5-8", pupils_count=35,
                            duration_minutes=45, format="class_hour",
                            participants={"teachers_count": 1, "parents_enabled": False, "parents_count": 0,
                                          "parent_roles": [], "parent_audience_engagement": "none"},
                            generation={"variants_count": 1, "language": "ru"})),
]


def build(spec: dict) -> dict:
    req = json.loads(json.dumps(BASE_REQ))
    for key, value in spec.items():
        if key == "resources":
            req["resources"].update(value)
        else:
            req[key] = value
    return req


def tokens_for(job_id: str) -> dict | None:
    if not RUNS.exists():
        return None
    for line in RUNS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("job_id") == job_id:
            return row.get("tokens")
    return None


def wait(client: httpx.Client, status_url: str, timeout: float = 900.0) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        last = client.get(BASE + status_url).json()
        if last.get("status") in {"completed", "partial", "failed", "blocked"}:
            return last
        time.sleep(3)
    return last


rows = []
with httpx.Client(timeout=300) as client:
    for name, spec in CASES:
        started = time.time()
        row = {"case": name}
        try:
            resp = client.post(BASE + "/api/v1/generations", json=build(spec))
            row["http"] = resp.status_code
            if resp.status_code != 202:
                row["error"] = resp.text[:400]
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
                continue
            accepted = resp.json()
            row["job_id"] = accepted["job_id"]
            job = wait(client, accepted["status_url"])
            project = client.get(BASE + accepted["project_url"]).json()
            row["job_status"] = job.get("status")
            row["completed_variants"] = job.get("completed_variants")
            row["errors"] = job.get("errors")
            row["warnings"] = job.get("warnings")
            row["variants"] = []
            for variant in project.get("variants") or []:
                timeline = variant.get("timeline") or []
                quality = variant.get("quality_report") or {}
                row["variants"].append({
                    "id": variant.get("variant_id"),
                    "blocks": len(timeline),
                    "sum_min": sum(b.get("duration_minutes", 0) for b in timeline),
                    "quality": quality.get("status"),
                    "issues": [i.get("code") for i in (quality.get("issues") or [])],
                })
            row["tokens"] = tokens_for(accepted["job_id"])
        except Exception as exc:  # noqa: BLE001
            row["error"] = f"{type(exc).__name__}: {exc}"
        row["duration_sec"] = round(time.time() - started, 1)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
print("SAVED", OUT, flush=True)
