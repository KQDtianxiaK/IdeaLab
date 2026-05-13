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
