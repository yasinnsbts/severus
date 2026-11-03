# -*- coding: utf-8 -*-
"""Дополнительные E2E-кейсы: оставшиеся события каталога и роль evaluator."""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
OUT = Path("qa/docs/testing/e2e_extra_events_2026-10-28.json")

TEMPLATE = {
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
    "generation": {"variants_count": 1, "language": "ru"},
}

CASES = [
    ("E2E-13", "christmas", "5-8", None, 22, 45, "class_hour", None, 0),
    ("E2E-14", "defender_day", "9-11", None, 24, 60, "school_event", None, 0),
    ("E2E-15", "graduation", "9-11", 11, 26, 60, "school_event", ["audience"], 10),
    ("E2E-16", "labour_day", "9-11", 10, 25, 60, "interactive_lesson", ["evaluator"], 4),
    ("E2E-17", "middle_urals_peoples_day", "5-8", None, 20, 45, "class_hour", None, 0),
    ("E2E-18", "sverdlovsk_oblast_day", "1-4", None, 18, 30, "class_hour", None, 0),
]


def build(case):
    _, event, group, grade, pupils, duration, fmt, roles, parents = case
    req = json.loads(json.dumps(TEMPLATE))
    req.update({
        "event_id": event, "grade_group": group, "pupils_count": pupils,
        "duration_minutes": duration, "format": fmt,
        "participants": {
            "teachers_count": 1,
            "parents_enabled": bool(roles),
            "parents_count": parents,
            "parent_roles": roles or [],
            "parent_audience_engagement": "none",
        },
    })
    if grade is not None:
        req["grade"] = grade
    return req


def wait(client, url, timeout=900):
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = client.get(BASE + url).json()
        if last.get("status") in {"completed", "partial", "failed", "blocked"}:
            return last
        time.sleep(3)
    return last


rows = []
with httpx.Client(timeout=300) as client:
    for case in CASES:
        case_id, event = case[0], case[1]
        started = time.time()
        row = {"id": case_id, "event": event}
        try:
            resp = client.post(BASE + "/api/v1/generations", json=build(case))
            row["http"] = resp.status_code
            if resp.status_code != 202:
                row["error"] = resp.text[:300]
                rows.append(row)
                continue
            accepted = resp.json()
            job = wait(client, accepted["status_url"])
            project = client.get(BASE + accepted["project_url"]).json()
            row["job_status"] = job.get("status")
            row["job_errors"] = job.get("errors")
            row["project_status"] = project.get("status")
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
        except Exception as exc:  # noqa: BLE001
            row["error"] = f"{type(exc).__name__}: {exc}"
        row["duration_sec"] = round(time.time() - started, 1)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
print("SAVED", OUT, flush=True)
