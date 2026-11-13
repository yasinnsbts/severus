"""Контракт 03 (schema_version 1.2): ответы модели по этапам и `variant_package`.

Это ВНУТРЕННИЙ контракт сервиса: фронтенд и общий бэкенд его не видят.
Лишние поля в ответах модели игнорируются (модели их иногда добавляют),
а обязательные поля и перечисления проверяются строго.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.2"

ValueId = Literal["family", "mutual_aid", "historical_memory", "labour_creation", "cultural_diversity", "citizenship"]
MechanicType = Literal[
    "family_research", "team_task", "source_work", "joint_product", "culture_comparison",
    "real_problem_solving", "class_collective_task", "pair_task", "discussion",
]
ActivityType = Literal[
    "discussion", "team_task", "pair_task", "individual_task", "game", "quiz", "source_work",
    "creative_product", "performance", "project_pitch", "research", "reflection", "voting",
]
PrimaryMechanic = Literal[
    "collaborative_planning", "team_game", "quest_route", "mini_project", "source_research",
    "creative_workshop", "performance", "discussion_club", "quiz_competition", "interview_research",
]
EngagementMode = Literal["whole_class", "pairs", "small_groups", "mixed"]
ParticipantType = Literal["teacher", "pupil", "pupils_group", "parent", "guest"]
RoleMode = Literal["helper", "active_participant", "audience", "evaluator"]
MaterialType = Literal[
    "teacher_instruction", "worksheet", "activity_card", "slide_outline", "quiz", "discussion_questions",
    "handout", "props_checklist", "parent_instruction", "audience_ballot", "jury_scorecard", "award_instruction",
]
MaterialAudience = Literal["teacher", "pupil", "pupils_group", "parent", "all"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


# Общие структуры ответа модели.

class ValueMechanic(_Model):
    value_id: ValueId
    mechanic_type: MechanicType
    mechanic: str = Field(min_length=10)
    block_ids: list[str] = Field(default_factory=list)


class Concept(_Model):
    summary: str = Field(min_length=10)
    goal: str = Field(min_length=5)
    tasks: list[str] = Field(min_length=1)
    expected_outcomes: list[str] = Field(min_length=1)
    values_to_mechanics: list[ValueMechanic] = Field(min_length=1)


class FactClaim(_Model):
    claim_id: str
    text: str
    location: str
    source_id: str | None = None
    fragment_id: str | None = None
    needs_teacher_check: bool = False


class Role(_Model):
    role_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    participant_type: ParticipantType
    role_mode: RoleMode | None = None
    title: str
    count: int = Field(ge=1)
    block_ids: list[str] = Field(default_factory=list)


class Block(_Model):
    block_id: str = Field(pattern=r"^block_\d{2}$")
    start_minute: int = Field(ge=0)
    duration_minutes: int = Field(gt=0)
    title: str
    purpose: str
    teacher_script: str = Field(min_length=20)
    pupil_actions: list[str] = Field(min_length=1)
    role_ids: list[str] = Field(min_length=1)
    material_ids: list[str] = Field(default_factory=list)


class Material(_Model):
    material_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: MaterialType
    title: str
    used_in_blocks: list[str] = Field(min_length=1)
    audience: MaterialAudience
    content: str = Field(min_length=20)
    teacher_notes: str
    print_required: bool
    dependencies: list[str] = Field(default_factory=list)
    estimated_preparation_minutes: int = Field(ge=0, le=240)
    family_task: bool = False


class PupilGrouping(_Model):
    total_pupils: int = Field(ge=1)
    mode: EngagementMode
    group_sizes: list[int] = Field(min_length=1)
    block_ids: list[str] = Field(default_factory=list)


class Assignment(_Model):
    role_id: str
    participant_type: Literal["parent"] = "parent"
    role_mode: RoleMode
    count: int = Field(ge=1)
    block_ids: list[str] = Field(min_length=1)


class Voting(_Model):
    enabled: bool
    award_title: str | None = None
    voters_count_planned: int = Field(ge=0)
    criterion: str
    method: str = "paper_ballot"
    votes_per_person: int = Field(ge=1, default=1)
    tie_rule: str
    block_id: str
    material_ids: list[str] = Field(default_factory=list)


class ParentParticipationPlan(_Model):
    enabled: bool
    parents_count: int = Field(ge=0)
    parent_size_group: Literal["none", "1-2", "3-5", "6-10", "11_plus"]
    selected_roles: list[RoleMode] = Field(default_factory=list)
    audience_engagement: Literal["none", "feedback", "vote", "audience_award"]
    assignments: list[Assignment] = Field(default_factory=list)
    voting: Voting | None = None
    teacher_fallback: str


class Source(_Model):
    source_id: str
    title: str
    publisher: str
    url: str


# Структуры полного варианта мероприятия.

class VariantBody(_Model):
    variant_id: str = Field(pattern=r"^v[1-3]$")
    title: str
    concept: Concept
    pupil_grouping: PupilGrouping
    roles: list[Role] = Field(min_length=2)
    timeline: list[Block] = Field(min_length=2)
    materials: list[Material] = Field(default_factory=list)
    parent_participation_plan: ParentParticipationPlan | None = None
    teacher_instructions: list[str] = Field(min_length=1)
    fact_claims: list[FactClaim] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)


class VariantPackage(_Model):
    schema_version: str = SCHEMA_VERSION
    task: Literal["variant_package"] = "variant_package"
    variant: VariantBody


# Структуры этапа variation_plan.

class PlannedBlockStub(_Model):
    order: int = Field(ge=1)
    title: str
    activity_type: ActivityType
    approx_minutes: int = Field(ge=1)


class KeyActivity(_Model):
    activity_type: ActivityType
    description: str


class Difference(_Model):
    variant_id: str
    difference: str


class ConceptValuePreview(_Model):
    value_id: ValueId
    mechanic_type: MechanicType
    mechanic: str


class ConceptPlan(_Model):
    variant_id: str = Field(pattern=r"^v[1-3]$")
    title: str
    summary: str
    narrative_approach: str
    primary_mechanic: PrimaryMechanic
    engagement_mode: EngagementMode
    planned_structure: list[PlannedBlockStub] = Field(min_length=2)
    key_activities: list[KeyActivity] = Field(min_length=1)
    distinctive_result: str
    differs_from: list[Difference] = Field(default_factory=list)
    values_to_mechanics: list[ConceptValuePreview] = Field(min_length=1)


class VariationPlanResponse(_Model):
    schema_version: str = SCHEMA_VERSION
    task: Literal["variation_plan"] = "variation_plan"
    concepts: list[ConceptPlan] = Field(min_length=1, max_length=3)


# Структуры этапа scenario_plan.

class GroupingRequest(_Model):
    mode: EngagementMode
    groups_count: int = Field(ge=1, le=35)
    block_ids: list[str] = Field(default_factory=list)


class PlanRole(_Model):
    role_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    participant_type: ParticipantType
    role_mode: RoleMode | None = None
    title: str
    count: int = Field(ge=1)


class PlanBlock(_Model):
    block_id: str = Field(pattern=r"^block_\d{2}$")
    title: str
    purpose: str
    proposed_minutes: int = Field(ge=1)
    role_ids: list[str] = Field(min_length=1)
    planned_material_ids: list[str] = Field(default_factory=list)


class PlannedMaterial(_Model):
    material_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: MaterialType
    title: str | None = None
    purpose: str


class ScenarioPlanResponse(_Model):
    schema_version: str = SCHEMA_VERSION
    task: Literal["scenario_plan"] = "scenario_plan"
    variant_id: str = Field(pattern=r"^v[1-3]$")
    title: str
    concept: Concept
    grouping_request: GroupingRequest
    roles: list[PlanRole] = Field(min_length=2)
    blocks: list[PlanBlock] = Field(min_length=2, max_length=12)
    planned_materials: list[PlannedMaterial] = Field(default_factory=list)


# Структуры этапов scenario_blocks и scenario_block.

class BlockDetail(_Model):
    block_id: str = Field(pattern=r"^block_\d{2}$")
    start_minute: int = Field(ge=0)
    duration_minutes: int = Field(gt=0)
    title: str
    purpose: str
    teacher_script: str = Field(min_length=20)
    pupil_actions: list[str] = Field(min_length=1)
    role_ids: list[str] = Field(min_length=1)
    material_ids: list[str] = Field(default_factory=list)


class ScenarioBlocksResponse(_Model):
    schema_version: str = SCHEMA_VERSION
    task: Literal["scenario_blocks"] = "scenario_blocks"
    variant_id: str
    blocks: list[BlockDetail] = Field(min_length=1)
    fact_claims: list[FactClaim] = Field(default_factory=list)


class ScenarioBlockResponse(_Model):
    schema_version: str = SCHEMA_VERSION
    task: Literal["scenario_block"] = "scenario_block"
    variant_id: str
    block: BlockDetail
    fact_claims: list[FactClaim] = Field(default_factory=list)


# Структуры этапа materials.

class VotingDraft(_Model):
    award_title: str | None = None
    criterion: str
    votes_per_person: int = Field(ge=1, default=1)
    tie_rule: str
    block_id: str
    material_ids: list[str] = Field(default_factory=list)


class MaterialsResponse(_Model):
    schema_version: str = SCHEMA_VERSION
    task: Literal["materials"] = "materials"
    variant_id: str
    materials: list[Material] = Field(default_factory=list)
    teacher_instructions: list[str] = Field(min_length=1)
    voting: VotingDraft | None = None
    teacher_fallback: str | None = None
    fact_claims: list[FactClaim] = Field(default_factory=list)


# Структуры этапа quality_review.

class QualityFinding(_Model):
    rule_code: str
    severity_suggested: Literal["info", "warning", "critical"]
    location: str
    message: str
    suggested_action: str


class FactClaimReview(_Model):
    claim_id: str
    matches_fragment: bool
    comment: str


class QualityReviewResponse(_Model):
    schema_version: str = SCHEMA_VERSION
    task: Literal["quality_review"] = "quality_review"
    variant_id: str = Field(pattern=r"^v[1-3]$")
    findings: list[QualityFinding] = Field(default_factory=list)
    fact_claims_review: list[FactClaimReview] = Field(default_factory=list)


STAGE_MODELS: dict[str, type[BaseModel]] = {
    "variation_plan": VariationPlanResponse,
    "scenario_plan": ScenarioPlanResponse,
    "scenario_blocks": ScenarioBlocksResponse,
    "scenario_block": ScenarioBlockResponse,
    "materials": MaterialsResponse,
    "quality_review": QualityReviewResponse,
    "variant_package": VariantPackage,
}