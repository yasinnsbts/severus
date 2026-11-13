"""Конвейер генерации (ТЗ 9–12, 16.4).

variation_plan → для каждой концепции: scenario_plan → [тайминг и группы кодом] →
scenario_blocks (или scenario_block по одному) → materials → сборка → проверки →
ограниченный repair → рендер в контракт 02.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, get_args

from pydantic import BaseModel, ValidationError

from ..catalog import Catalog
from ..contracts import llm as c03
from ..llm.client import LLMClient, LLMError
from ..llm.jsonx import JSONExtractionError, extract_json
from ..normalize import NormalizedRequest, normalize
from ..prompting.composer import Composer
from ..script_length import script_size_text
from ..render import render_project, render_variant
from ..settings import Settings, sha256_file
from ..trace import RunTrace
from ..usage import TokenTally
from ..validation.checks import Issue, diversity_issues, report_status, validate_variant
from .grouping import compute_grouping, describe
from .ids import normalize_dependencies, normalize_ids, normalize_material_fields
from .timing import build_grid, normalize_minutes

STAGE_ORDER = {"plan": 0, "blocks": 1, "materials": 2}


class StageFailed(RuntimeError):
    def __init__(self, stage: str, message: str, code: str = "OUTPUT_SCHEMA_INVALID"):
        """Создаёт объект ошибки этапа и сохраняет имя этапа и стабильный код ошибки.

        Параметры:
            `stage`, `message`, `code`.
        """
        super().__init__(message)
        self.stage = stage
        self.code = code


@dataclass
class StageResult:
    model: BaseModel
    raw: str
    call_id: str


@dataclass
class VariantOutcome:
    variant_id: str
    package: dict[str, Any] | None
    issues: list[Issue]
    frontend: dict[str, Any] | None
    status: str
    error: str | None = None


@dataclass
class GenerationOutcome:
    job_id: str
    project: dict[str, Any]
    normalized: NormalizedRequest
    concepts: list[dict[str, Any]]
    variants: list[VariantOutcome]
    run_dir: str | None
    calls: int = 0
    duration_ms: int = 0
    warnings: list[dict[str, Any]] = field(default_factory=list)
    tokens: dict[str, Any] = field(default_factory=dict)


_SUFFIX = re.compile(r"^(?P<base>.+?)_\d+$")
_LIST_MARKER = re.compile(r"^\s*(?:[-*•–]\s+|\d{1,2}[.)]\s+)")


AUDIENCES = ("teacher", "pupil", "pupils_group", "parent", "all")
# Расходники и техника: модели иногда объявляют их материалами («paper», «markers») с пустым содержанием.
RESOURCE_IDS = {"paper", "markers", "pens", "pencils", "colored_pencils", "scissors", "glue", "whiteboard", "board",
                "chalk", "projector", "printer", "audio", "internet", "computer", "laptop", "speakers"}


def resource_ids(n: NormalizedRequest) -> set[str]:
    """Имена ресурсов запроса и типовых расходников, которые не могут быть ID материала."""
    named = list(n.resources.get("available_materials") or []) + n.available_resources + n.unavailable_resources
    return RESOURCE_IDS | {str(x).strip().lower() for x in named if x}


def _audience(value: Any) -> Any:
    """Приводит адресата материала к допустимому значению: `parent_audience` -> `parent`, `pupils_all` -> `pupils_group`."""
    if not isinstance(value, str) or value in AUDIENCES:
        return value
    v = value.strip().lower()
    for prefix, target in (("teacher", "teacher"), ("parent", "parent"), ("pupils", "pupils_group"), ("pupil", "pupil"),
                           ("student", "pupils_group"), ("class", "pupils_group")):
        if v.startswith(prefix):
            return target
    return value


_ENUMS: dict[str, tuple[str, ...]] = {
    "activity_type": get_args(c03.ActivityType),
    "engagement_mode": get_args(c03.EngagementMode),
    "primary_mechanic": get_args(c03.PrimaryMechanic),
    "mechanic_type": get_args(c03.MechanicType),
    "material_type": get_args(c03.MaterialType),
    "role_mode": get_args(c03.RoleMode),
}
_SYNONYMS: dict[str, dict[str, str]] = {
    "activity_type": {
        "creative": "creative_product", "creative_workshop": "creative_product", "craft": "creative_product",
        "drawing": "creative_product", "handicraft": "creative_product", "workshop": "creative_product",
        "presentation": "performance", "show": "performance", "concert": "performance", "staging": "performance",
        "conversation": "discussion", "talk": "discussion", "dialogue": "discussion", "discussion_club": "discussion",
        "intro": "discussion", "introduction": "discussion", "greeting": "discussion", "briefing": "discussion",
        "team_game": "game", "quest": "game", "quest_route": "game", "warmup": "game", "warm_up": "game",
        "quiz_competition": "quiz", "mini_project": "project_pitch", "project": "project_pitch",
        "group_task": "team_task", "group_work": "team_task", "teamwork": "team_task",
        "individual": "individual_task", "individual_work": "individual_task",
        "pair": "pair_task", "pair_work": "pair_task", "vote": "voting",
        "summary": "reflection", "conclusion": "reflection", "final": "reflection", "closing": "reflection",
        "interview": "research", "source_research": "source_work",
        "class_collective_task": "team_task", "collaborative_planning": "team_task", "real_problem_solving": "team_task",
        "joint_product": "creative_product", "family_research": "research", "interview_research": "research",
        "culture_comparison": "discussion",
    },
    "primary_mechanic": {
        "joint_product": "creative_workshop", "creative_product": "creative_workshop", "class_collective_task": "collaborative_planning",
        "real_problem_solving": "collaborative_planning", "team_task": "team_game", "game": "team_game", "quest": "quest_route",
        "family_research": "interview_research", "research": "interview_research", "interview": "interview_research",
        "source_work": "source_research", "discussion": "discussion_club", "culture_comparison": "discussion_club",
        "pair_task": "discussion_club", "quiz": "quiz_competition", "project": "mini_project", "project_pitch": "mini_project",
        "concert": "performance", "show": "performance",
    },
    "mechanic_type": {
        "creative_workshop": "joint_product", "creative_product": "joint_product", "mini_project": "joint_product",
        "performance": "joint_product", "team_game": "team_task", "quest_route": "team_task", "quiz_competition": "team_task",
        "game": "team_task", "collaborative_planning": "class_collective_task", "interview_research": "family_research",
        "source_research": "source_work", "research": "source_work", "discussion_club": "discussion",
    },
    "material_type": {
        "reward": "props_checklist", "award": "award_instruction", "diploma": "handout", "certificate": "handout",
        "template": "handout", "examples": "handout", "example": "handout", "reference": "handout", "memo": "handout",
        "sheet": "handout", "printout": "handout", "card": "activity_card", "cards": "activity_card", "task_card": "activity_card",
        "instruction": "teacher_instruction", "teacher_notes": "teacher_instruction", "script": "teacher_instruction",
        "questions": "discussion_questions", "checklist": "props_checklist", "props": "props_checklist",
        "slides": "slide_outline", "presentation": "slide_outline", "ballot": "audience_ballot", "scorecard": "jury_scorecard",
    },
    "engagement_mode": {
        "individual": "whole_class", "individual_task": "whole_class", "individual_work": "whole_class", "frontal": "whole_class", "class": "whole_class", "whole": "whole_class",
        "group": "small_groups", "groups": "small_groups", "teams": "small_groups", "team": "small_groups",
        "pair": "pairs", "mix": "mixed", "combined": "mixed",
    },
}
# Если значение так и не распозналось, берём нейтральное, чтобы этап не падал целиком: для описательных полей концепции
# и для типа материала (раздаточный лист - самый общий тип; проверки по типам касаются только бюллетеней, листов жюри и памяток).
_FALLBACK = {"activity_type": "discussion", "engagement_mode": "mixed", "material_type": "handout",
             "primary_mechanic": "collaborative_planning"}


def _fix_enum(value: Any, kind: str) -> Any:
    """Приводит значение перечисления к допустимому: регистр, пробелы, синонимы, «одно из: a | b» из примера."""
    allowed = _ENUMS[kind]
    if not isinstance(value, str) or value in allowed:
        return value
    s = value.strip().lower()
    norm = re.sub(r"[\s\-]+", "_", s)
    if norm in allowed:
        return norm
    if norm in _SYNONYMS.get(kind, {}):
        return _SYNONYMS[kind][norm]
    found = sorted((m.start(), a) for a in allowed for m in re.finditer(rf"(?<![a-z_]){re.escape(a)}(?![a-z_])", s))
    if found:
        return found[0][1]
    return _FALLBACK.get(kind, value)


def _fix_enums(data: dict, stage: str, changes: list[dict[str, Any]]) -> None:
    """Проходит по полям-перечислениям ответа этапа и исправляет значения через `_fix_enum`."""
    def fix(obj: Any, key: str, kind: str, where: str) -> None:
        if isinstance(obj, dict) and key in obj:
            new = _fix_enum(obj[key], kind)
            if new != obj[key]:
                changes.append({"kind": "enum_fixed", "field": where, "from": obj[key], "to": new})
                obj[key] = new

    def items(obj: Any, key: str) -> list:
        value = obj.get(key) if isinstance(obj, dict) else None
        return value if isinstance(value, list) else []

    if stage == "variation_plan":
        for i, c in enumerate(items(data, "concepts")):
            fix(c, "engagement_mode", "engagement_mode", f"concepts.{i}.engagement_mode")
            fix(c, "primary_mechanic", "primary_mechanic", f"concepts.{i}.primary_mechanic")
            for j, s in enumerate(items(c, "planned_structure")):
                fix(s, "activity_type", "activity_type", f"concepts.{i}.planned_structure.{j}.activity_type")
            for j, a in enumerate(items(c, "key_activities")):
                fix(a, "activity_type", "activity_type", f"concepts.{i}.key_activities.{j}.activity_type")
            for j, v in enumerate(items(c, "values_to_mechanics")):
                fix(v, "mechanic_type", "mechanic_type", f"concepts.{i}.values_to_mechanics.{j}.mechanic_type")
    if stage == "scenario_plan":
        fix(data.get("grouping_request"), "mode", "engagement_mode", "grouping_request.mode")
        for j, v in enumerate(items(data.get("concept"), "values_to_mechanics")):
            fix(v, "mechanic_type", "mechanic_type", f"concept.values_to_mechanics.{j}.mechanic_type")
        for j, r in enumerate(items(data, "roles")):
            if isinstance(r, dict) and r.get("role_mode") is not None:
                fix(r, "role_mode", "role_mode", f"roles.{j}.role_mode")
        for j, m in enumerate(items(data, "planned_materials")):
            fix(m, "type", "material_type", f"planned_materials.{j}.type")
    if stage == "materials":
        for j, m in enumerate(items(data, "materials")):
            fix(m, "type", "material_type", f"materials.{j}.type")


def prepare_stage_output(stage: str, data: Any, resources: set[str],
                         dependency_ids: set[str] | None = None) -> list[dict[str, Any]]:
    """Исправляет до проверки схемы ошибки ответа, которые однозначно понятны программе.

    - План: материалы с ID ресурса (`paper`, `markers`) убираются из `planned_materials` и из блоков.
    - Материалы: такие же материалы убираются; адресат вида `parent_audience` приводится к `parent`.
    - Все этапы: `material_id`, `role_id` и ссылки на них - к виду `^[a-z][a-z0-9_]*$`, ID блоков - к `block_NN`
      (`ids.normalize_ids`); зависимости материалов - только из словаря (`ids.normalize_dependencies`).
    Всё остальное проверяет схема, и при ошибке модель исправляет ответ сама.

    Параметры:
        stage: этап; data: разобранный JSON ответа (меняется на месте); resources: см. `resource_ids`;
        dependency_ids: ID словаря `catalog/dependencies.json` (None - зависимости не трогать).

    Возвращает:
        Список исправлений для трассы.
    """
    changes: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return changes
    _fix_enums(data, stage, changes)
    normalize_ids(stage, data, changes)
    if stage == "materials":
        normalize_material_fields(data, changes)
        if dependency_ids is not None:
            normalize_dependencies(data, dependency_ids, changes)
    grouping = data.get("grouping_request") if stage == "scenario_plan" else None
    if isinstance(grouping, dict) and grouping.get("groups_count") in (None, "", 0):
        grouping["groups_count"] = 1  # программа сама считает группы (`compute_grouping`)
        changes.append({"kind": "groups_count_default", "mode": grouping.get("mode")})
    if stage == "scenario_plan" and isinstance(data.get("planned_materials"), list):
        drop = {m.get("material_id") for m in data["planned_materials"]
                if isinstance(m, dict) and str(m.get("material_id", "")).lower() in resources}
        # Блоки тоже могут ссылаться на расходники напрямую, не объявляя их в planned_materials.
        for b in data.get("blocks") or []:
            if isinstance(b, dict) and isinstance(b.get("planned_material_ids"), list):
                drop |= {mid for mid in b["planned_material_ids"] if str(mid).lower() in resources}
        if drop:
            data["planned_materials"] = [m for m in data["planned_materials"] if not (isinstance(m, dict) and m.get("material_id") in drop)]
            for b in data.get("blocks") or []:
                if isinstance(b, dict) and isinstance(b.get("planned_material_ids"), list):
                    b["planned_material_ids"] = [mid for mid in b["planned_material_ids"] if mid not in drop]
            changes.append({"kind": "resource_materials_dropped", "material_ids": sorted(drop)})
    if stage == "materials" and isinstance(data.get("materials"), list):
        kept = []
        for m in data["materials"]:
            if isinstance(m, dict) and str(m.get("material_id", "")).lower() in resources:
                changes.append({"kind": "resource_material_dropped", "material_id": m.get("material_id")})
                continue
            if isinstance(m, dict) and "audience" in m:
                fixed = _audience(m["audience"])
                if fixed != m["audience"]:
                    changes.append({"kind": "audience_fixed", "material_id": m.get("material_id"), "from": m["audience"], "to": fixed})
                    m["audience"] = fixed
            kept.append(m)
        data["materials"] = kept
    return changes


def strip_list_markers(items: list[str]) -> list[str]:
    """Убирает маркер списка, который модель сама ставит в начало пункта («1. », «2) », «- »).

    Пункты и так выводятся списком, поэтому без этого получается «- 1. Подготовьте…».
    Пустые после очистки пункты отбрасываются.

    Параметры:
        items: пункты списка из ответа модели.

    Возвращает:
        Очищенные пункты в том же порядке.
    """
    cleaned = [_LIST_MARKER.sub("", item, count=1).strip() for item in items]
    return [item for item in cleaned if item] or [item.strip() for item in items if item.strip()]


def _get(obj: Any, key: str) -> Any:
    return obj[key] if isinstance(obj, dict) else getattr(obj, key)


def _set(obj: Any, key: str, value: Any) -> None:
    if isinstance(obj, dict):
        obj[key] = value
    else:
        setattr(obj, key, value)


def reconcile_material_ids(planned_materials: list[dict], materials: list[Any]) -> dict[str, str]:
    """Приводит ID материалов, созданных моделью, к ID из утверждённого плана.

    Модели часто слегка меняют ID (дописывают `_01`) или придумывают свой. Правила, по порядку:
    1. ID есть в плане - не трогаем.
    2. ID вида `<id из плана>_<число>` - убираем числовой суффикс.
    3. В плане ровно один ещё не занятый материал того же типа - берём его ID.
    Материалы без пары остаются как есть. Один ID из плана получает не больше одного материала.

    Параметры:
        planned_materials: `planned_materials` из плана (словари с `material_id` и `type`).
        materials: материалы этапа materials (словари или Pydantic-модели); ID меняются на месте.

    Возвращает:
        Словарь `старый ID -> новый ID` для переименованных материалов.
    """
    planned_ids = [m["material_id"] for m in planned_materials]
    planned_type = {m["material_id"]: m["type"] for m in planned_materials}
    taken = {_get(m, "material_id") for m in materials if _get(m, "material_id") in planned_ids}
    mapping: dict[str, str] = {}
    for m in materials:
        mid = _get(m, "material_id")
        if mid in planned_ids:
            continue
        target = None
        match = _SUFFIX.match(mid)
        if match and match["base"] in planned_ids and match["base"] not in taken:
            target = match["base"]
        else:
            same_type = [pid for pid in planned_ids if planned_type[pid] == _get(m, "type")]
            free = [pid for pid in same_type if pid not in taken]
            if len(same_type) == 1 and free:
                target = free[0]
        if target:
            _set(m, "material_id", target)
            taken.add(target)
            mapping[mid] = target
    return mapping


def fix_material_refs(mat: Any, timeline: list[dict]) -> list[dict[str, Any]]:
    """Оставляет в ответе этапа материалов только ссылки на существующие блоки и материалы.

    - `used_in_blocks`: блоки, которых нет в сценарии, убираются; если не осталось ни одного,
      берутся блоки, которые ссылаются на этот материал по плану.
    - `voting.material_ids`: только созданные материалы; если ни одного - все бюллетени (`audience_ballot`).
    - `voting.block_id`: если такого блока нет - блок, где используется бюллетень.

    Параметры: mat - ответ этапа материалов (Pydantic, меняется на месте); timeline - блоки сценария.
    Возвращает: список исправлений для трассы.
    """
    fixes: list[dict[str, Any]] = []
    valid = [b["block_id"] for b in timeline]
    for m in mat.materials:
        kept = [bid for bid in m.used_in_blocks if bid in valid]
        if len(kept) != len(m.used_in_blocks):
            if not kept:
                kept = [b["block_id"] for b in timeline if m.material_id in b["material_ids"]]
            if not kept and timeline:
                kept = [timeline[0]["block_id"]]
            fixes.append({"kind": "used_in_blocks", "material_id": m.material_id, "from": list(m.used_in_blocks), "to": kept})
            m.used_in_blocks = kept or m.used_in_blocks
    voting = getattr(mat, "voting", None)
    if voting:
        created = {m.material_id for m in mat.materials}
        ids = [mid for mid in voting.material_ids if mid in created]
        if not ids:
            ids = [m.material_id for m in mat.materials if m.type == "audience_ballot"]
        if ids != list(voting.material_ids):
            fixes.append({"kind": "voting_material_ids", "from": list(voting.material_ids), "to": ids})
            voting.material_ids = ids
        if voting.block_id not in valid:
            ballot_blocks = [bid for m in mat.materials if m.material_id in ids for bid in m.used_in_blocks if bid in valid]
            if ballot_blocks:
                fixes.append({"kind": "voting_block_id", "from": voting.block_id, "to": ballot_blocks[-1]})
                voting.block_id = ballot_blocks[-1]
    return fixes


def complete_block_roles(plan: dict) -> dict[str, list[str]]:
    """Дополняет `role_ids` блоков плана теми, кто присутствует на мероприятии всё время.

    Модели часто пишут в `role_ids` только «главное действующее лицо» блока. Правила:
    1. Ведущий педагог (`teacher`) и все учащиеся (`pupils_group`) есть в каждом блоке.
    2. Роль родителей, не указанная ни в одном блоке, присутствует во всех блоках
       (так же её трактует план участия родителей).
    Роли, которые модель уже расставила по блокам, не трогаются.

    Параметры:
        plan: план варианта (словарь `scenario_plan`); `role_ids` блоков меняются на месте.

    Возвращает:
        Словарь `role_id -> список блоков`, куда роль была добавлена.
    """
    blocks = plan.get("blocks", [])
    used = {rid for b in blocks for rid in b["role_ids"]}
    always = [r["role_id"] for r in plan.get("roles", [])
              if r["participant_type"] in ("teacher", "pupils_group")
              or (r["participant_type"] == "parent" and r["role_id"] not in used)]
    added: dict[str, list[str]] = {}
    for b in blocks:
        for rid in always:
            if rid not in b["role_ids"]:
                b["role_ids"].append(rid)
                added.setdefault(rid, []).append(b["block_id"])
    return added


def _issue_lines(issues: list[Issue]) -> list[dict[str, str]]:
    """Преобразует объекты проблем в компактный формат для repair-запроса к модели.

    Параметры:
        `issues`.

    Возвращает:
        list[dict[str, str]].
    """
    return [{"code": i.code, "location": i.location, "message": i.message} for i in issues]


class Generator:
    def __init__(self, settings: Settings, catalog: Catalog, client: LLMClient, *, trace: RunTrace | None = None):
        """Инициализирует генератор и связывает настройки, каталог, LLM-клиент, Composer и трассировку.

        Параметры:
            `settings`, `catalog`, `client`, `trace`.
        """
        self.settings = settings
        self.catalog = catalog
        self.client = client
        self.composer = Composer(settings, catalog)
        self.cfg = settings.generation()
        self.defaults = self.cfg["defaults"]
        self.trace = trace or RunTrace(None)
        self.calls = 0
        self.tokens = TokenTally()
        self._sleep = time.sleep  # подменяется в тестах, чтобы не ждать паузы между повторами

    # Лимит ответа модели для этапа.
    def max_output_tokens(self, stage: str, n: NormalizedRequest) -> int:
        """Возвращает лимит ответа модели для этапа.

        Если в конфигурации этапа задан `max_output_tokens_per_variant`, лимит растёт
        с числом вариантов и ограничивается сверху `max_output_tokens`. Так ответ
        `variation_plan` с тремя концепциями не обрезается, а для одного варианта
        лимит остаётся небольшим.
        """
        task_cfg = self.cfg["tasks"][stage]
        cap = int(task_cfg["max_output_tokens"])
        per_variant = task_cfg.get("max_output_tokens_per_variant")
        if per_variant is None:
            return cap
        return min(cap, int(per_variant) * n.variants_count)

    # Выполнение этапа с ограниченным числом попыток исправления.
    def call_stage(self, stage: str, n: NormalizedRequest, *, stage_input: str = "", output_vars: dict | None = None,
                   meta: dict | None = None, repair: dict | None = None, variant_id: str | None = None,
                   parent_call_id: str | None = None) -> StageResult:
        """Вызывает один LLM-этап, проверяет JSON по Pydantic-схеме и при ошибке выполняет ограниченный repair.

        Параметры:
            `stage`, `n`, `stage_input`, `output_vars`, `meta`, `repair`, `variant_id`, `parent_call_id`.

        Возвращает:
            StageResult.
        """
        model_cls = c03.STAGE_MODELS[stage]
        task_cfg = self.cfg["tasks"][stage]
        attempts = int(self.defaults.get("max_repair_attempts_per_stage", 2)) + 1
        last_error = ""
        prev_raw: str | None = None
        for attempt in range(1, attempts + 1):
            rep = repair
            if prev_raw is not None:
                rep = {"previous_response": prev_raw[:12000], "issues": [{"code": "FORMAT", "location": stage, "message": last_error}]}
            composed = self.composer.compose(stage, n, stage_input=stage_input, output_vars=output_vars, repair=rep)
            call_id = self.trace.next_call_id()
            self.trace.event("llm_call_started", call_id=call_id, stage=stage, variant_id=variant_id, attempt=attempt)
            started = time.monotonic()
            raw = None
            parsed_obj = None
            status = "completed"
            error_code = None
            result = None
            try:
                result = self._generate_with_retry(
                    stage, call_id, variant_id,
                    messages=composed.messages, task_name=stage, output_schema=model_cls.model_json_schema(),
                    max_tokens=self.max_output_tokens(stage, n), temperature=float(task_cfg["temperature_hint"]),
                    meta=meta or {})
                raw = result.text
                data = extract_json(raw)
                fixes = prepare_stage_output(stage, data, resource_ids(n), set(self.catalog.dependencies))
                if fixes:
                    self.trace.event("stage_output_fixed", call_id=call_id, stage=stage, variant_id=variant_id, fixes=fixes)
                parsed_obj = model_cls.model_validate(data)
                return StageResult(parsed_obj, raw, call_id)
            except (JSONExtractionError, ValidationError) as exc:
                status, error_code = "failed", "OUTPUT_SCHEMA_INVALID"
                last_error = self._format_error(exc)
                prev_raw = raw or ""
            except LLMError as exc:
                status, error_code = "failed", exc.code
                self.trace.event("llm_call_failed", call_id=call_id, stage=stage, error_code=exc.code, message=exc.message)
                raise
            finally:
                manifest = {
                    "call_id": call_id, "job_id": meta.get("job_id") if meta else None, "variant_id": variant_id,
                    "stage": stage, "attempt": attempt, "parent_call_id": parent_call_id,
                    "model_key": getattr(result, "model_key", getattr(self.client, "model_key", None)),
                    "provider": getattr(result, "provider", getattr(self.client, "provider", None)),
                    "provider_model_id": getattr(result, "provider_model_id", None),
                    "prompt_manifest_hash": composed.manifest_hash, "prompt_blocks": composed.manifest,
                    "prompt_context": composed.context_metadata,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                    "latency_ms": getattr(result, "latency_ms", None), "mutex_wait_ms": getattr(result, "mutex_wait_ms", None),
                    "usage": getattr(result, "usage", None), "usage_source": "provider" if getattr(result, "usage", None) else "unavailable",
                    "reasoning_stripped": getattr(result, "reasoning_stripped", None),
                    "request_params": getattr(result, "request_params", None),
                    "status": status, "error_code": error_code, "error": last_error if status == "failed" else None,
                }
                if result is not None:
                    self.tokens.add(stage, getattr(result, "usage", None))
                self.trace.save_call(call_id, manifest=manifest, messages=composed.messages, prompt_md=composed.as_markdown(),
                                     raw=raw, parsed=parsed_obj.model_dump() if parsed_obj is not None else None)
                self.trace.event("llm_call_completed" if status == "completed" else "llm_call_invalid", call_id=call_id,
                                 stage=stage, variant_id=variant_id, attempt=attempt, error_code=error_code)
                parent_call_id = call_id
        raise StageFailed(stage, f"Этап {stage}: ответ модели не прошёл схему после {attempts} попыток: {last_error}")

    def _generate_with_retry(self, stage: str, call_id: str, variant_id: str | None, **kwargs: Any) -> Any:
        """Вызывает модель; при временной ошибке провайдера повторяет вызов с паузой (ТЗ: RATE_LIMITED, backoff).

        Повторяются только ошибки с `retryable=True`: 429, 5xx, таймаут, недоступность сети.
        Ошибки авторизации и конфигурации (`MODEL_AUTH_ERROR`, неизвестная модель) не повторяются.
        Число повторов и паузы - `defaults.provider_retry_attempts` и `defaults.provider_retry_backoff_seconds`.
        Каждый повтор - отдельный вызов модели: учитывается в `calls` и пишется в трассу (`llm_call_retry`).
        """
        retries = int(self.defaults.get("provider_retry_attempts", 2))
        backoff = list(self.defaults.get("provider_retry_backoff_seconds", [3, 10])) or [0]
        for retry in range(retries + 1):
            self.calls += 1
            try:
                return self.client.generate(**kwargs)
            except LLMError as exc:
                if not exc.retryable or retry >= retries:
                    raise
                wait = float(backoff[min(retry, len(backoff) - 1)])
                self.trace.event("llm_call_retry", call_id=call_id, stage=stage, variant_id=variant_id,
                                 retry=retry + 1, error_code=exc.code, message=exc.message, wait_seconds=wait)
                self._sleep(wait)
        raise AssertionError("недостижимо")  # pragma: no cover

    @staticmethod
    def _format_error(exc: Exception) -> str:
        """Формирует краткое диагностическое описание ошибки JSON или Pydantic.

        Параметры:
            `exc`.

        Возвращает:
            str.
        """
        if isinstance(exc, ValidationError):
            parts = []
            for err in exc.errors()[:8]:
                loc = ".".join(str(x) for x in err["loc"])
                parts.append(f"{loc}: {err['msg']}")
            return "Ответ не соответствует схеме: " + "; ".join(parts)
        return f"Ответ не является корректным JSON: {exc}"

    # Формирование входных данных для этапов генерации.
    @staticmethod
    def concept_text(concept: dict, others: list[dict]) -> str:
        """Формирует вход следующего этапа из выбранной концепции и кратких сведений о соседних вариантах.

        Параметры:
            `concept`, `others`.

        Возвращает:
            str.
        """
        lines = ["## Вход этапа: выбранная концепция", "```json", json.dumps(concept, ensure_ascii=False, indent=2), "```"]
        if others:
            lines.append("\nДругие варианты этого проекта (их механику не повторять):")
            for o in others:
                lines.append(f"- {o['variant_id']}: «{o['title']}» - {o['primary_mechanic']}; результат: {o['distinctive_result']}")
        return "\n".join(lines)

    @staticmethod
    def plan_text(plan: dict, grid: list[tuple[int, int]], grouping: tuple[str, list[int]], focus_block: str | None = None,
                  previous_excerpt: str | None = None, script_chars: Any = None) -> str:
        """Формирует текстовое представление утверждённого плана, рассчитанного тайминга и группировки.

        Параметры:
            `plan`, `grid`, `grouping`, `focus_block`, `previous_excerpt`;
            `script_chars` - функция «минуты -> текст про нужный объём реплик», для этапов блоков.

        Возвращает:
            str.
        """
        mode, sizes = grouping
        lines = [f"## Вход этапа: утверждённый план варианта {plan['variant_id']} «{plan['title']}»",
                 f"Концепция: {plan['concept']['summary']}", f"Цель: {plan['concept']['goal']}",
                 f"Деление учащихся ({mode}): {describe(sizes)}; блоки: {', '.join(plan['grouping_request'].get('block_ids', [])) or '-'}",
                 "", "Роли:"]
        for r in plan["roles"]:
            mode_txt = f", режим {r['role_mode']}" if r.get("role_mode") else ""
            lines.append(f"- `{r['role_id']}` - {r['title']} ({r['participant_type']}{mode_txt}), человек: {r['count']}")
        lines.append("\nБлоки (время утверждено программой - не менять):")
        for b, (start, dur) in zip(plan["blocks"], grid):
            mark = "  ← ТЕКУЩИЙ БЛОК" if focus_block == b["block_id"] else ""
            size = f" | реплики педагога: {script_chars(dur)}" if script_chars else ""
            lines.append(f"- `{b['block_id']}` | {start}–{start + dur} мин ({dur}) | {b['title']} | цель: {b['purpose']} | "
                         f"роли: {', '.join(b['role_ids'])} | материалы: {', '.join(b['planned_material_ids']) or '-'}{size}{mark}")
        lines.append("\nЦенности → механики:")
        for vm in plan["concept"]["values_to_mechanics"]:
            lines.append(f"- {vm['value_id']} ({vm['mechanic_type']}): {vm['mechanic']} - блоки {', '.join(vm.get('block_ids', []))}")
        if plan.get("planned_materials"):
            lines.append("\nМатериалы (тексты создаются на следующем этапе):")
            for m in plan["planned_materials"]:
                lines.append(f"- `{m['material_id']}` - {m['type']} - {m['purpose']}")
        if previous_excerpt:
            lines.append(f"\nКонец предыдущего блока (для связности): «{previous_excerpt}»")
        return "\n".join(lines)

    @staticmethod
    def planned_materials_list(plan: dict) -> str:
        """Список материалов плана для формата ответа этапа materials: ID и тип, которые нельзя менять."""
        items = plan.get("planned_materials") or []
        if not items:
            return "в плане материалов нет; создавай материал, только если без него блок невыполним"
        return ", ".join(f"`{m['material_id']}` ({m['type']})" for m in items)

    @staticmethod
    def blocks_text(blocks: list[dict]) -> str:
        """Формирует компактный контекст уже готовых сценарных блоков для генерации материалов.

        Параметры:
            `blocks`.

        Возвращает:
            str.
        """
        lines = ["\n## Готовый сценарий блоков (кратко)"]
        for b in blocks:
            script = b["teacher_script"]
            excerpt = script if len(script) <= 700 else script[:700] + "…"
            lines.append(f"### `{b['block_id']}` {b['title']} ({b['start_minute']}–{b['start_minute'] + b['duration_minutes']} мин)\n"
                         f"Действия учеников: {'; '.join(b['pupil_actions'])}\nМатериалы: {', '.join(b['material_ids']) or '-'}\n"
                         f"Сценарий (фрагмент): {excerpt}")
        return "\n".join(lines)

    # Последовательное выполнение этапов для одного варианта.
    def _plan_checks(self, plan: c03.ScenarioPlanResponse, n: NormalizedRequest) -> list[Issue]:
        """Проверяет ссылки, роли, материалы, ценности и ограничения сценарного плана до детализации.

        Параметры:
            `plan`, `n`.

        Возвращает:
            list[Issue].
        """
        issues: list[Issue] = []
        role_ids = {r.role_id for r in plan.roles}
        if "teacher_1" not in role_ids:
            issues.append(Issue("PLAN-TEACHER", "critical", "roles", "Нет роли teacher_1", "plan"))
        if not any(r.participant_type == "pupils_group" and r.count == n.pupils_count for r in plan.roles):
            issues.append(Issue("PLAN-PUPILS", "critical", "roles", f"Нет роли pupils_all с count={n.pupils_count}", "plan"))
        expected = [f"block_{i:02d}" for i in range(1, len(plan.blocks) + 1)]
        if [b.block_id for b in plan.blocks] != expected:
            issues.append(Issue("PLAN-BLOCK-IDS", "critical", "blocks", f"block_id должны идти по порядку: {', '.join(expected)}", "plan"))
        min_block = int(self.defaults.get("min_block_minutes", 2))
        if len(plan.blocks) * min_block > n.duration_minutes:
            issues.append(Issue("PLAN-TOO-MANY-BLOCKS", "critical", "blocks", "Слишком много блоков для длительности", "plan"))
        for b in plan.blocks:
            for rid in b.role_ids:
                if rid not in role_ids:
                    issues.append(Issue("PLAN-REF-ROLE", "critical", f"blocks.{b.block_id}", f"Роль {rid} не описана", "plan"))
        planned = {m.material_id for m in plan.planned_materials}
        for b in plan.blocks:
            for mid in b.planned_material_ids:
                if mid not in planned:
                    issues.append(Issue("PLAN-REF-MATERIAL", "critical", f"blocks.{b.block_id}", f"Материал {mid} не объявлен в planned_materials", "plan"))
        vids = [v.value_id for v in plan.concept.values_to_mechanics]
        for value_id in n.values:
            if value_id not in vids:
                issues.append(Issue("VAL-001", "critical", "concept.values_to_mechanics", f"Ценность {value_id} не реализована", "plan"))
        if not n.parents_enabled and any(r.participant_type == "parent" for r in plan.roles):
            issues.append(Issue("PARENTS-DISABLED", "critical", "roles", "Роли родителей при отключённых родителях", "plan"))
        return issues

    def _build_parent_plan(self, n: NormalizedRequest, roles: list[dict], mat: c03.MaterialsResponse, block_ids: list[str]) -> dict | None:
        """Собирает внутренний план участия родителей из ролей, материалов и режима зрителей.

        Параметры:
            `n`, `roles`, `mat`, `block_ids`.

        Возвращает:
            dict | None.
        """
        if not n.parents_enabled:
            return None
        parent_roles = [r for r in roles if r["participant_type"] == "parent"]
        assignments = [{"role_id": r["role_id"], "participant_type": "parent", "role_mode": r.get("role_mode") or "audience",
                        "count": r["count"], "block_ids": r["block_ids"] or block_ids} for r in parent_roles]
        voting = None
        if n.parent_audience_engagement in ("vote", "audience_award") and mat.voting:
            voters = sum(a["count"] for a in assignments if a["role_mode"] == "audience" and mat.voting.block_id in a["block_ids"])
            if not voters:
                # Модель иногда делает всех родителей помощниками и не выделяет зрителей.
                # Голосуют родители, которые есть в блоке голосования (помощники тоже), иначе все пришедшие.
                voters = sum(a["count"] for a in assignments if mat.voting.block_id in a["block_ids"]) or n.parents_count
            voting = {"enabled": True,
                      "award_title": mat.voting.award_title if n.parent_audience_engagement == "audience_award" else None,
                      "voters_count_planned": voters, "criterion": mat.voting.criterion, "method": "paper_ballot",
                      "votes_per_person": mat.voting.votes_per_person, "tie_rule": mat.voting.tie_rule,
                      "block_id": mat.voting.block_id, "material_ids": mat.voting.material_ids}
        return {"enabled": True, "parents_count": n.parents_count, "parent_size_group": n.parent_size_group,
                "selected_roles": sorted({a["role_mode"] for a in assignments}, key=n.parent_roles.index) if assignments else [],
                "audience_engagement": n.parent_audience_engagement, "assignments": assignments, "voting": voting,
                "teacher_fallback": mat.teacher_fallback or "Если родители не придут, педагог выполняет их задачи сам или с помощью учеников-добровольцев; голосование заменяется общей рефлексией без соревнования."}

    def generate_variant(self, n: NormalizedRequest, concept: dict, others: list[dict], meta: dict) -> VariantOutcome:
        """Последовательно создаёт план, сценарные блоки и материалы одного варианта с repair и валидацией.

        Параметры:
            `n`, `concept`, `others`, `meta`.

        Возвращает:
            VariantOutcome.
        """
        vid = concept["variant_id"]
        rounds_left = int(self.defaults.get("max_repair_attempts_per_stage", 2))
        plan_res = blocks_res = mat_res = None
        block_details: dict[str, dict] = {}
        block_raw: dict[str, str] = {}
        repair_for: dict[str, dict] = {}
        min_block = int(self.defaults.get("min_block_minutes", 2))
        detail = n.teacher_preferences["script_detail"]
        script_chars = lambda minutes: script_size_text(self.cfg, detail, minutes)  # noqa: E731
        per_block_mode = self.defaults.get("block_detail_mode", "auto")
        per_block = per_block_mode == "per_block" or (per_block_mode == "auto" and n.duration_minutes >= int(self.defaults.get("per_block_from_minutes", 60)))
        vmeta = {**meta, "variant_id": vid}

        while True:
            # Генерация и проверка плана сценария.
            if plan_res is None:
                plan_res = self.call_stage("scenario_plan", n, stage_input=self.concept_text(concept, others),
                                           output_vars={"variant_id": vid}, meta=vmeta, variant_id=vid, repair=repair_for.pop("plan", None))
                plan_issues = self._plan_checks(plan_res.model, n)
                if plan_issues and rounds_left > 0:
                    rounds_left -= 1
                    self.trace.event("repair_started", variant_id=vid, stage="plan", issues=_issue_lines(plan_issues))
                    repair_for["plan"] = {"previous_response": plan_res.raw, "issues": _issue_lines(plan_issues)}
                    plan_res = None
                    continue
                if plan_issues:
                    return VariantOutcome(vid, None, plan_issues, None, "failed", "План не прошёл проверку")
                blocks_res = mat_res = None
            plan = plan_res.model.model_dump()
            roles_added = complete_block_roles(plan)
            if roles_added:
                self.trace.event("block_roles_completed", variant_id=vid, added=roles_added)
            minutes = normalize_minutes([b["proposed_minutes"] for b in plan["blocks"]], n.duration_minutes, min_block)
            grid = build_grid(minutes)
            g_mode, sizes, g_notes = compute_grouping(plan["grouping_request"]["mode"], n.pupils_count,
                                                      plan["grouping_request"]["groups_count"], n.group_work)

            # Генерация и проверка сценарных блоков.
            if blocks_res is None:
                if not per_block:
                    res = self.call_stage("scenario_blocks", n, stage_input=self.plan_text(plan, grid, (g_mode, sizes), script_chars=script_chars),
                                          output_vars={"variant_id": vid}, meta=vmeta, variant_id=vid, repair=repair_for.pop("blocks", None))
                    block_details = {b.block_id: b.model_dump() for b in res.model.blocks}
                    block_raw = {"__all__": res.raw}
                    claims = [c.model_dump() for c in res.model.fact_claims]
                else:
                    block_details, claims, prev = {}, [], None
                    rep_all = repair_for.pop("blocks", None)
                    for b, (start, dur) in zip(plan["blocks"], grid):
                        res = self.call_stage("scenario_block", n,
                                              stage_input=self.plan_text(plan, grid, (g_mode, sizes), b["block_id"], prev, script_chars),
                                              output_vars={"variant_id": vid, "block_id": b["block_id"], "start_minute": str(start), "block_minutes": str(dur)},
                                              meta={**vmeta, "block_id": b["block_id"]}, variant_id=vid, repair=rep_all)
                        block_details[b["block_id"]] = res.model.block.model_dump()
                        block_raw[b["block_id"]] = res.raw
                        claims += [c.model_dump() for c in res.model.fact_claims]
                        script = res.model.block.teacher_script
                        prev = script[-300:]
                blocks_res = {"claims": claims}
                mat_res = None

            planned_ids = [m["material_id"] for m in plan.get("planned_materials", [])]
            plan_role_ids = {r["role_id"] for r in plan["roles"]}
            dropped_refs: list[dict[str, str]] = []
            timeline = []
            for b, (start, dur) in zip(plan["blocks"], grid):
                d = block_details.get(b["block_id"])
                if d is None:
                    d = {"teacher_script": "", "pupil_actions": [], "role_ids": b["role_ids"], "material_ids": b["planned_material_ids"]}
                # Ссылаться можно только на материалы из плана; расходники (бумага, маркеры) - не материалы.
                block_mats = []
                for mid in list(b["planned_material_ids"]) + list(d.get("material_ids") or []):
                    if mid in planned_ids:
                        if mid not in block_mats:
                            block_mats.append(mid)
                    else:
                        dropped_refs.append({"block_id": b["block_id"], "material_id": mid})
                # Роли блока задаёт план; этап блоков может только добавить роли, описанные в плане.
                block_roles = list(b["role_ids"])
                for rid in d.get("role_ids") or []:
                    if rid in plan_role_ids and rid not in block_roles:
                        block_roles.append(rid)
                timeline.append({"block_id": b["block_id"], "start_minute": start, "duration_minutes": dur, "title": b["title"],
                                 "purpose": b["purpose"], "teacher_script": d.get("teacher_script", ""),
                                 "pupil_actions": strip_list_markers(d.get("pupil_actions") or []), "role_ids": block_roles,
                                 "material_ids": block_mats})
            if dropped_refs:
                self.trace.event("block_material_refs_dropped", variant_id=vid, refs=dropped_refs)

            # Генерация и проверка материалов.
            if mat_res is None:
                mat_res = self.call_stage("materials", n, stage_input=self.plan_text(plan, grid, (g_mode, sizes)) + self.blocks_text(timeline),
                                          output_vars={"variant_id": vid, "planned_materials_list": self.planned_materials_list(plan)},
                                          meta=vmeta, variant_id=vid, repair=repair_for.pop("materials", None))
            mat = mat_res.model
            renamed = reconcile_material_ids(plan.get("planned_materials", []), mat.materials)
            if renamed:
                if mat.voting:
                    mat.voting.material_ids = [renamed.get(mid, mid) for mid in mat.voting.material_ids]
                self.trace.event("material_ids_reconciled", variant_id=vid, renamed=renamed)
            ref_fixes = fix_material_refs(mat, timeline)
            if ref_fixes:
                self.trace.event("material_refs_fixed", variant_id=vid, fixes=ref_fixes)
            # Блок ссылается на материал, если материал указан для этого блока.
            created = {m.material_id for m in mat.materials}
            for b in timeline:
                for m in mat.materials:
                    if b["block_id"] in m.used_in_blocks and m.material_id not in b["material_ids"]:
                        b["material_ids"].append(m.material_id)
                b["material_ids"] = [mid for mid in b["material_ids"] if mid in created or mid in planned_ids]

            # Сборка полного варианта и итоговая проверка.
            roles = []
            for r in plan["roles"]:
                rb = [b["block_id"] for b in timeline if r["role_id"] in b["role_ids"]]
                roles.append({**r, "block_ids": rb})
            claims = blocks_res["claims"] + [c.model_dump() for c in mat.fact_claims]
            for i, c in enumerate(claims, 1):
                c["claim_id"] = f"fc_{i:02d}"
            body = {
                "variant_id": vid, "title": plan["title"], "concept": plan["concept"],
                "pupil_grouping": {"total_pupils": n.pupils_count, "mode": g_mode, "group_sizes": sizes,
                                   "block_ids": plan["grouping_request"].get("block_ids", [])},
                "roles": roles, "timeline": timeline, "materials": [m.model_dump() for m in mat.materials],
                "parent_participation_plan": self._build_parent_plan(n, roles, mat, [b["block_id"] for b in timeline]),
                "teacher_instructions": strip_list_markers(mat.teacher_instructions), "fact_claims": claims, "sources": [],
            }
            issues: list[Issue] = [Issue("GROUPING-NOTE", "info", "pupil_grouping", note, "local", False) for note in g_notes]
            try:
                body = c03.VariantBody.model_validate(body).model_dump()
            except ValidationError as exc:
                issues.append(Issue("SCHEMA", "critical", "variant", self._format_error(exc), "blocks"))
            else:
                issues += validate_variant(body, n, self.catalog, self.cfg)
                if self.defaults.get("llm_quality_review", False):
                    review_input = "## Вход этапа: готовый вариант для проверки\n```json\n" + json.dumps(body, ensure_ascii=False, indent=2) + "\n```"
                    review = self.call_stage(
                        "quality_review",
                        n,
                        stage_input=review_input,
                        output_vars={"variant_id": vid},
                        meta=vmeta,
                        variant_id=vid,
                    )
                    for finding in review.model.findings:
                        issues.append(Issue(
                            finding.rule_code,
                            "warning" if finding.severity_suggested != "info" else "info",
                            finding.location,
                            f"LLM-review: {finding.message} Предложение: {finding.suggested_action}",
                            "quality",
                            False,
                        ))
                    for fact_review in review.model.fact_claims_review:
                        if not fact_review.matches_fragment:
                            issues.append(Issue(
                                "FACT-REVIEW",
                                "critical",
                                f"fact_claims.{fact_review.claim_id}",
                                f"Содержательная проверка не подтвердила утверждение: {fact_review.comment}",
                                "quality",
                                False,
                            ))

            critical = [i for i in issues if i.severity == "critical" and i.repairable and i.stage in STAGE_ORDER]
            if critical and rounds_left > 0:
                rounds_left -= 1
                first = min(STAGE_ORDER[i.stage] for i in critical)
                stage = next(k for k, v in STAGE_ORDER.items() if v == first)
                stage_issues = _issue_lines([i for i in critical if i.stage == stage])
                self.trace.event("repair_started", variant_id=vid, stage=stage, issues=stage_issues)
                if stage == "plan":
                    repair_for["plan"] = {"previous_response": plan_res.raw, "issues": stage_issues}
                    plan_res = None
                elif stage == "blocks":
                    raw_prev = block_raw.get("__all__") or json.dumps(list(block_details.values()), ensure_ascii=False)
                    repair_for["blocks"] = {"previous_response": raw_prev[:12000], "issues": stage_issues}
                    blocks_res = None
                else:
                    repair_for["materials"] = {"previous_response": mat_res.raw, "issues": stage_issues}
                    mat_res = None
                continue

            package = c03.VariantPackage(variant=c03.VariantBody.model_validate(body)).model_dump() if "SCHEMA" not in {i.code for i in issues} else {"variant": body}
            status = "failed" if report_status(issues) == "blocked" else "completed"
            frontend = render_variant(package["variant"], n, self.catalog, issues) if status == "completed" else None
            return VariantOutcome(vid, package, issues, frontend, status, None if status == "completed" else "Критические проблемы после исправлений")

    # Генерация всей задачи с требуемым числом вариантов.
    def run(self, raw_request: dict[str, Any], *, job_id: str | None = None, project_id: str | None = None,
            context_mode: str = "full", cultural_context: bool = True, experiment_tag: str | None = None,
            experiment_pair_id: str | None = None) -> GenerationOutcome:
        """Запускает генерацию и записывает итог в журнал прогонов `runs.jsonl`, в том числе при ошибке.

        Параметры и результат - как у `_run`.
        """
        started = time.monotonic()
        job_id = job_id or f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        extra = {"context_mode": context_mode, "cultural_context": cultural_context,
                 "experiment_tag": experiment_tag, "experiment_pair_id": experiment_pair_id}
        try:
            outcome = self._run(raw_request, job_id=job_id, project_id=project_id, **extra)
        except Exception as exc:
            error = {"code": getattr(exc, "code", type(exc).__name__), "stage": getattr(exc, "stage", None),
                     "message": str(getattr(exc, "message", None) or exc)[:500]}
            self.trace.append_run_log(self._run_record(job_id, raw_request, started, extra, None, error))
            raise
        self.trace.append_run_log(self._run_record(job_id, raw_request, started, extra, outcome, None))
        return outcome

    def _run_record(self, job_id: str, raw_request: dict[str, Any], started: float, extra: dict[str, Any],
                    outcome: GenerationOutcome | None, error: dict[str, Any] | None) -> dict[str, Any]:
        """Строка журнала прогонов: что генерировали, чем закончилось, сколько вызовов, времени и токенов."""
        record: dict[str, Any] = {
            "job_id": job_id,
            "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "event_id": raw_request.get("event_id") if isinstance(raw_request, dict) else None,
            "grade": raw_request.get("grade") if isinstance(raw_request, dict) else None,
            "format": raw_request.get("format") if isinstance(raw_request, dict) else None,
            "duration_minutes": raw_request.get("duration_minutes") if isinstance(raw_request, dict) else None,
            "model_key": getattr(self.client, "model_key", "unknown"),
            "block_detail_mode": self.defaults.get("block_detail_mode", "auto"),
            "status": outcome.project["status"] if outcome else "failed",
            "requested_variants": outcome.project["requested_variants"] if outcome else None,
            "completed_variants": outcome.project["completed_variants"] if outcome else 0,
            "llm_calls": self.calls,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "tokens": self.tokens.as_dict(),
            "issues": [f"{i.severity}:{i.code}:{i.location}" for v in (outcome.variants if outcome else []) for i in v.issues
                       if i.severity != "info"],
            "error": error,
        }
        if extra.get("experiment_tag") or extra.get("context_mode") != "full" or not extra.get("cultural_context", True):
            record.update(extra)
        return record

    def _run(self, raw_request: dict[str, Any], *, job_id: str, project_id: str | None = None,
             context_mode: str = "full", cultural_context: bool = True, experiment_tag: str | None = None,
             experiment_pair_id: str | None = None) -> GenerationOutcome:
        """Запускает полный конвейер генерации 1-3 вариантов и собирает внешний проект.

        Параметры:
            `raw_request`, `job_id`, `project_id`, `context_mode`, `cultural_context`, `experiment_tag`, `experiment_pair_id`.

        Возвращает:
            GenerationOutcome.
        """
        started = time.monotonic()
        project_id = project_id or ("evt_" + job_id[4:])
        n = normalize(raw_request, self.catalog, self.settings, context_mode=context_mode, cultural_context=cultural_context,
                      experiment_tag=experiment_tag, experiment_pair_id=experiment_pair_id)
        meta = {"job_id": job_id}
        self.trace.write_json("input.json", raw_request)
        self.trace.write_json("normalized_request.json", n.to_dict())
        self.trace.event("job_started", job_id=job_id, event_id=n.event_id, variants=n.variants_count)

        concepts: list[dict] = []
        repair = None
        for attempt in range(int(self.defaults.get("max_concept_retries", 2)) + 1):
            res = self.call_stage("variation_plan", n, meta=meta, repair=repair)
            concepts = [c.model_dump() for c in res.model.concepts]
            problems = []
            if len(concepts) != n.variants_count:
                problems.append(Issue("CONCEPT-COUNT", "critical", "concepts", f"Нужно ровно {n.variants_count} концепций, получено {len(concepts)}", "concepts"))
            ids = [c["variant_id"] for c in concepts]
            if ids != [f"v{i}" for i in range(1, len(concepts) + 1)]:
                for i, c in enumerate(concepts, 1):
                    c["variant_id"] = f"v{i}"
            for c in concepts:
                missing = [v for v in n.values if v not in {x["value_id"] for x in c["values_to_mechanics"]}]
                if missing:
                    problems.append(Issue("VAL-001", "critical", f"concepts.{c['variant_id']}", f"Не реализованы ценности: {', '.join(missing)}", "concepts"))
                if not n.group_work and c["engagement_mode"] == "small_groups":
                    problems.append(Issue("GROUP-WORK-FORBIDDEN", "critical", f"concepts.{c['variant_id']}", "engagement_mode=small_groups при запрете групп", "concepts"))
            problems += diversity_issues(concepts)
            critical = [p for p in problems if p.severity == "critical"]
            self.trace.write_json("concepts.json", {"concepts": concepts, "checks": [p.to_dict() for p in problems]})
            if not critical:
                break
            repair = {"previous_response": res.raw, "issues": _issue_lines(critical)}
            self.trace.event("repair_started", stage="variation_plan", issues=_issue_lines(critical))
        else:
            concepts = concepts[: n.variants_count]

        outcomes: list[VariantOutcome] = []
        for concept in concepts[: n.variants_count]:
            others = [c for c in concepts if c["variant_id"] != concept["variant_id"]]
            try:
                outcome = self.generate_variant(n, concept, others, meta)
            except (StageFailed, LLMError) as exc:
                outcome = VariantOutcome(concept["variant_id"], None, [], None, "failed", str(exc))
                if isinstance(exc, LLMError) and exc.code in ("MODEL_UNAVAILABLE", "MODEL_AUTH_ERROR"):
                    outcomes.append(outcome)
                    self.trace.event("variant_failed", variant_id=concept["variant_id"], error=str(exc))
                    break
            outcomes.append(outcome)
            if outcome.package:
                self.trace.write_json(f"variants/{outcome.variant_id}/variant_package.json", outcome.package)
            self.trace.write_json(f"variants/{outcome.variant_id}/validation.json",
                                  {"status": outcome.status, "error": outcome.error, "issues": [i.to_dict() for i in outcome.issues]})
            self.trace.event("variant_completed" if outcome.status == "completed" else "variant_failed",
                             variant_id=outcome.variant_id, issues=len(outcome.issues))

        model_key = getattr(self.client, "model_key", "unknown")
        project = render_project(job_id=job_id, project_id=project_id, n=n,
                                 variants=[o.frontend for o in outcomes if o.frontend], requested=n.variants_count,
                                 model_key=model_key, prompt_version=self.cfg.get("prompt_version", "0.0.0"),
                                 catalog_version=next(iter(self.catalog.events.values())).get("catalog_version", "1.0"))
        self.trace.write_json("final_result.json", project)
        self.trace.write_json("metadata.json", {
            "job_id": job_id, "model_key": model_key, "context_mode": context_mode, "cultural_context": cultural_context,
            "experiment_tag": experiment_tag, "experiment_pair_id": experiment_pair_id, "calls": self.calls,
            "catalog_hashes": self.catalog.hashes, "defaults_hash": n.defaults_hash,
            "values_hash": self.catalog.hashes.get("catalog/values.json"),
            "school_profile_hash": self.catalog.hashes.get("config/school_profile.json"),
            "experiment_modes_hash": sha256_file(self.settings.experiment_modes_file),
            "duration_ms": int((time.monotonic() - started) * 1000), "status": project["status"],
            "tokens": self.tokens.as_dict(),
        })
        self.trace.event("job_" + project["status"], job_id=job_id, calls=self.calls)
        return GenerationOutcome(job_id, project, n, concepts, outcomes, str(self.trace.run_dir) if self.trace.run_dir else None,
                                 self.calls, int((time.monotonic() - started) * 1000), [w.__dict__ for w in n.warnings],
                                 tokens=self.tokens.totals())