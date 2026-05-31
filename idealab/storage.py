from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import WORKSPACES_DIR, ensure_dirs, write_json
from .models import Edge, Graph, Node, RunMode, new_id, now_iso


def run_dir(run_id: str) -> Path:
    return WORKSPACES_DIR / run_id


def create_workspace(mode: RunMode, raw_input: str) -> tuple[str, Path, Graph]:
    ensure_dirs()
    run_id = new_id("run")
    workspace = run_dir(run_id)
    for child in ["evidence", "reports", "configs", "logs", "evaluations", "experiments"]:
        (workspace / child).mkdir(parents=True, exist_ok=True)

    init = Node(
        id=new_id("node"),
        type="init",
        title="初始化",
        status="running",
        summary="IdeaLab 正在初始化推演工作区。",
        input={"raw_user_input": raw_input},
    )
    graph = Graph(run_id=run_id, mode=mode, nodes=[init], title="IdeaLab Run")
    save_graph(workspace, graph)
    append_event(workspace, {"type": "run_created", "run_id": run_id, "mode": mode})
    write_text(workspace / "problem_input.md", raw_input)
    return run_id, workspace, graph


def load_graph(workspace: Path) -> Graph:
    with (workspace / "graph.json").open("r", encoding="utf-8") as f:
        return Graph.model_validate(json.load(f))


def save_graph(workspace: Path, graph: Graph) -> None:
    graph.updated_at = now_iso()
    write_json(workspace / "graph.json", graph.model_dump())


def append_event(workspace: Path, event: dict[str, Any]) -> None:
    event = {"timestamp": now_iso(), **event}
    with (workspace / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def add_node(workspace: Path, node: Node) -> Graph:
    graph = load_graph(workspace)
    graph.nodes.append(node)
    if node.parent_id:
        graph.edges.append(Edge(source=node.parent_id, target=node.id))
    save_graph(workspace, graph)
    append_event(workspace, {"type": "node_added", "node": node.model_dump()})
    return graph


def add_edge(workspace: Path, source: str, target: str) -> Graph:
    graph = load_graph(workspace)
    if not any(edge.source == source and edge.target == target for edge in graph.edges):
        graph.edges.append(Edge(source=source, target=target))
        save_graph(workspace, graph)
        append_event(workspace, {"type": "edge_added", "source": source, "target": target})
    return graph


def update_node(workspace: Path, node_id: str, **updates: Any) -> Graph:
    graph = load_graph(workspace)
    for node in graph.nodes:
        if node.id == node_id:
            for key, value in updates.items():
                setattr(node, key, value)
            node.updated_at = now_iso()
            break
    save_graph(workspace, graph)
    append_event(workspace, {"type": "node_updated", "node_id": node_id, "updates": updates})
    return graph


def set_run_status(workspace: Path, status: str) -> Graph:
    graph = load_graph(workspace)
    graph.status = status  # type: ignore[assignment]
    save_graph(workspace, graph)
    append_event(workspace, {"type": "run_status", "status": status})
    return graph


def list_workspaces() -> list[Path]:
    ensure_dirs()
    return sorted(
        [p for p in WORKSPACES_DIR.iterdir() if p.is_dir() and (p / "graph.json").exists()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
