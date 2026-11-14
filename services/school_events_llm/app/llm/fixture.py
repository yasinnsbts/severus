"""Тестовый провайдер: отвечает за модель по эталонным примерам (examples/golden).

Нужен, чтобы проверять конвейер, валидаторы и рендер без LM Studio:
`python -m app generate examples/requests/ex1_knowledge_day.json --fixture examples/golden/ex1_knowledge_day.json`.
`broken` - сколько первых ответов каждого этапа вернуть битыми (проверка repair).
"""

from __future__ import annotations

import copy
import json
from typing import Any

from .client import LLMClient, LLMResult


class FixtureLLM(LLMClient):
    provider = "fixture"

    def __init__(self, goldens: list[dict[str, Any]], *, broken: dict[str, int] | None = None, model_key: str = "fixture"):
        """Создаёт fixture-клиент из эталонных пакетов и настраивает намеренно повреждаемые этапы.

        Параметры:
            `goldens`, `broken`, `model_key`.
        """
        if not goldens:
            raise ValueError("Нужен хотя бы один эталон")
        self.goldens = goldens
        self.broken = dict(broken or {})
        # Битые ответы выдаются первым вызовам этапа: при параллельных вариантах неизвестно, какому варианту.
        self.parallel_variants_safe = not self.broken
        self.model_key = model_key
        self.calls: list[dict[str, Any]] = []

    def health(self) -> dict[str, Any]:
        """Проверяет доступность провайдера и возвращает диагностические сведения о модели.

        Возвращает:
            dict[str, Any].
        """
        return {"model_key": self.model_key, "provider": "fixture", "goldens": len(self.goldens)}

    def _golden(self, variant_id: str | None) -> dict[str, Any]:
        """Выбирает эталонный пакет, соответствующий текущему варианту тестовой генерации.

        Параметры:
            `variant_id`.

        Возвращает:
            dict[str, Any].
        """
        idx = int(variant_id[1:]) - 1 if variant_id else 0
        return self.goldens[idx % len(self.goldens)]

    def _respond(self, task: str, meta: dict[str, Any]) -> dict[str, Any]:
        """Формирует ответ конкретного этапа из эталонного пакета без обращения к реальной модели.

        Параметры:
            `task`, `meta`.

        Возвращает:
            dict[str, Any].
        """
        if task == "variation_plan":
            n = int(meta.get("variants_count") or 0) or None
            concepts = []
            for i, g in enumerate(self.goldens[: n or len(self.goldens)], 1):
                c = copy.deepcopy(g["concept"])
                c["variant_id"] = f"v{i}"
                concepts.append(c)
            return {"schema_version": "1.2", "task": "variation_plan", "concepts": concepts}
        g = self._golden(meta.get("variant_id"))
        v = g["variant_package"]["variant"]
        vid = meta.get("variant_id", "v1")
        if task == "scenario_plan":
            grouping = v["pupil_grouping"]
            groups = 1 if grouping["mode"] == "whole_class" else len(grouping["group_sizes"])
            return {
                "schema_version": "1.2", "task": "scenario_plan", "variant_id": vid, "title": v["title"],
                "concept": v["concept"],
                "grouping_request": {"mode": grouping["mode"], "groups_count": groups, "block_ids": grouping["block_ids"]},
                "roles": [{k: r[k] for k in ("role_id", "participant_type", "role_mode", "title", "count") if k in r} for r in v["roles"]],
                "blocks": [{"block_id": b["block_id"], "title": b["title"], "purpose": b["purpose"], "proposed_minutes": b["duration_minutes"],
                            "role_ids": b["role_ids"], "planned_material_ids": b["material_ids"]} for b in v["timeline"]],
                "planned_materials": [{"material_id": m["material_id"], "type": m["type"], "purpose": m["title"]} for m in v["materials"]],
            }
        if task == "scenario_blocks":
            return {"schema_version": "1.2", "task": "scenario_blocks", "variant_id": vid,
                    "blocks": copy.deepcopy(v["timeline"]), "fact_claims": copy.deepcopy(v.get("fact_claims", []))}
        if task == "scenario_block":
            block = next(b for b in v["timeline"] if b["block_id"] == meta.get("block_id"))
            return {"schema_version": "1.2", "task": "scenario_block", "variant_id": vid, "block": copy.deepcopy(block), "fact_claims": []}
        if task == "materials":
            plan = v.get("parent_participation_plan") or {}
            voting = plan.get("voting")
            return {"schema_version": "1.2", "task": "materials", "variant_id": vid,
                    "materials": copy.deepcopy(v["materials"]), "teacher_instructions": list(v["teacher_instructions"]),
                    "voting": ({k: voting[k] for k in ("award_title", "criterion", "votes_per_person", "tie_rule", "block_id", "material_ids")}
                               if voting else None),
                    "teacher_fallback": plan.get("teacher_fallback"), "fact_claims": []}
        raise ValueError(f"FixtureLLM не знает этап {task}")

    def generate(self, *, messages, task_name, output_schema, max_tokens, temperature, meta=None) -> LLMResult:
        """Отправляет сообщения модели, применяет локальную очередь, обрабатывает structured output и возвращает нормализованный результат.

        Параметры:
            `messages`, `task_name`, `output_schema`, `max_tokens`, `temperature`, `meta`.

        Возвращает:
            LLMResult.
        """
        meta = dict(meta or {})
        if task_name == "variation_plan" and "variants_count" not in meta:
            for line in messages[-1]["content"].splitlines():
                if line.startswith("| Количество вариантов |"):
                    meta["variants_count"] = line.split("|")[2].strip()
        self.calls.append({"task": task_name, "meta": meta})
        if self.broken.get(task_name, 0) > 0:
            self.broken[task_name] -= 1
            text = '{"schema_version": "1.2", "task": "' + task_name + '", "oops": '
        else:
            text = "<think>служебные рассуждения</think>\n```json\n" + json.dumps(self._respond(task_name, meta), ensure_ascii=False) + "\n```"
        return LLMResult(text=text, model_key=self.model_key, provider="fixture", provider_model_id="fixture",
                         usage=None, latency_ms=0, reasoning_stripped=True, structured_mode="none")