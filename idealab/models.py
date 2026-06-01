from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


RunMode = Literal["fixed", "free"]
NodeStatus = Literal["running", "completed", "failed", "queued", "waiting_user"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


class CreateRunRequest(BaseModel):
    input: str = Field(min_length=1)
    mode: RunMode = "fixed"


class HumanInputRequest(BaseModel):
    content: str = Field(min_length=1)
    target_node_id: str | None = None
    target_type: Literal["run", "idea", "evaluation", "experiment_plan", "node"] = "run"
    intervention_type: Literal["comment", "score_override", "approve", "reject", "merge", "request_recompute"] = "comment"
    idea_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HumanEvaluationJudgmentRequest(BaseModel):
    idea_a_id: str = Field(min_length=1)
    idea_b_id: str = Field(min_length=1)
    winner: Literal["A", "B", "tie"]
    reasoning: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0, le=1)


class ScoreDimension(BaseModel):
    id: str
    label: str
    description: str = ""
    scale: str = "0-10"
    higher_is_better: bool = True
    weight: float = 1.0
    enabled: bool = True


class EvaluationSpec(BaseModel):
    run_id: str
    target_type: str = "idea"
    idea_type: str = "unknown"
    dimensions: list[ScoreDimension] = Field(default_factory=list)
    judge_models: list[str] = Field(default_factory=list)
    pairing_strategy: str = "full_matrix_until_5_then_sample"
    experiment_policy: str = "plan_only"


class PairwiseJudgment(BaseModel):
    pair_id: str
    idea_a_id: str
    idea_b_id: str
    judge_model: str
    winner: Literal["A", "B", "tie"]
    dimension_scores: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.5, ge=0, le=1)
    reasoning: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    human_overrides: list[dict[str, Any]] = Field(default_factory=list)


class ExperimentPlanStub(BaseModel):
    idea_id: str
    status: Literal["planned", "skipped"] = "planned"
    reason_not_executed: str = "Phase 1 only plans validation experiments; execution is not implemented."
    minimum_validation: str = ""
    metrics: list[str] = Field(default_factory=list)
    controls: list[str] = Field(default_factory=list)
    ablation_plan: list[str] = Field(default_factory=list)
    expected_result: str = ""
    failure_signal: str = ""


class EvaluationRun(BaseModel):
    evaluation_id: str
    status: Literal["completed", "failed"] = "completed"
    spec: EvaluationSpec
    judgments: list[PairwiseJudgment] = Field(default_factory=list)
    btl_scores: dict[str, float] = Field(default_factory=dict)
    elo_scores: dict[str, float] = Field(default_factory=dict)
    dimension_aggregates: dict[str, dict[str, float]] = Field(default_factory=dict)
    model_disagreement: dict[str, Any] = Field(default_factory=dict)
    meta_review: dict[str, Any] = Field(default_factory=dict)
    pareto_categories: dict[str, str] = Field(default_factory=dict)
    experiment_plans: list[ExperimentPlanStub] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class Node(BaseModel):
    id: str
    parent_id: str | None = None
    type: str
    title: str
    status: NodeStatus = "queued"
    summary: str = ""
    input: Any = None
    output: Any = None
    model: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    prompt_version: int | None = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class Edge(BaseModel):
    source: str
    target: str


class Graph(BaseModel):
    run_id: str
    mode: RunMode
    status: Literal["running", "completed", "failed", "stopped", "waiting_user"] = "running"
    title: str = "Untitled IdeaLab Run"
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class RunSummary(BaseModel):
    id: str
    mode: RunMode
    status: str
    title: str
    workspace: str
    created_at: str
    updated_at: str
