from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .config import (
    STATIC_DIR,
    env_is_set,
    get_api_key_status,
    get_evaluation_config,
    get_models_config,
    get_prompts_config,
    save_local_env,
    save_evaluation_config,
    save_models_config,
    save_prompts_config,
    provider_api_key_updates,
)
from .engine import engine
from .models import CreateRunRequest, HumanEvaluationJudgmentRequest, HumanInputRequest, RunSummary
from .storage import list_workspaces, load_graph, run_dir


app = FastAPI(title="IdeaLab", version="0.1.0")


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict:
    api_keys = get_api_key_status()
    return {
        "ok": True,
        "api_keys": api_keys,
        "api_status": "normal" if api_keys["all_required"] else "missing",
    }


@app.post("/api/runs")
async def create_run(request: CreateRunRequest) -> dict:
    graph = engine.create_run(request)
    return graph.model_dump()


@app.get("/api/runs")
async def list_runs() -> list[dict]:
    summaries = []
    for workspace in list_workspaces():
        graph = load_graph(workspace)
        summaries.append(
            RunSummary(
                id=graph.run_id,
                mode=graph.mode,
                status=graph.status,
                title=graph.title,
                workspace=str(workspace),
                created_at=graph.created_at,
                updated_at=graph.updated_at,
            ).model_dump()
        )
    return summaries


@app.get("/api/runs/{run_id}/graph")
async def get_graph(run_id: str) -> dict:
    workspace = run_dir(run_id)
    if not (workspace / "graph.json").exists():
        raise HTTPException(status_code=404, detail="Run not found")
    return engine.ensure_display_branches(workspace).model_dump()


@app.post("/api/runs/{run_id}/human-input")
async def add_human_input(run_id: str, request: HumanInputRequest) -> dict:
    workspace = run_dir(run_id)
    if not (workspace / "graph.json").exists():
        raise HTTPException(status_code=404, detail="Run not found")
    return engine.add_human_input(run_id, request).model_dump()


@app.post("/api/runs/{run_id}/stop")
async def stop_run(run_id: str) -> dict:
    workspace = run_dir(run_id)
    if not (workspace / "graph.json").exists():
        raise HTTPException(status_code=404, detail="Run not found")
    return engine.stop_run(run_id).model_dump()


@app.get("/api/runs/{run_id}/report")
async def get_report(run_id: str) -> PlainTextResponse:
    path = run_dir(run_id) / "reports" / "report.md"
    if not path.exists():
        return PlainTextResponse("", status_code=200)
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@app.get("/api/runs/{run_id}/evaluation")
async def get_evaluation(run_id: str) -> dict:
    workspace = run_dir(run_id)
    if not (workspace / "graph.json").exists():
        raise HTTPException(status_code=404, detail="Run not found")
    evaluation = engine.load_evaluation(run_id)
    return evaluation or {}


@app.post("/api/runs/{run_id}/evaluation/recompute")
async def recompute_evaluation(run_id: str) -> dict:
    workspace = run_dir(run_id)
    if not (workspace / "graph.json").exists():
        raise HTTPException(status_code=404, detail="Run not found")
    return engine.recompute_evaluation(run_id)


@app.post("/api/runs/{run_id}/evaluation/human-judgment")
async def add_human_evaluation_judgment(run_id: str, request: HumanEvaluationJudgmentRequest) -> dict:
    workspace = run_dir(run_id)
    if not (workspace / "graph.json").exists():
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        return engine.add_human_evaluation_judgment(run_id, request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/config/models")
async def get_models() -> dict:
    data = get_models_config()
    redacted = data.copy()
    return redacted


@app.put("/api/config/models")
async def put_models(data: dict) -> dict:
    return save_models_config(data)


@app.get("/api/config/prompts")
async def get_prompts() -> dict:
    return get_prompts_config()


@app.put("/api/config/prompts")
async def put_prompts(data: dict) -> dict:
    return save_prompts_config(data)


@app.get("/api/config/evaluation")
async def get_evaluation_settings() -> dict:
    return get_evaluation_config()


@app.put("/api/config/evaluation")
async def put_evaluation_settings(data: dict) -> dict:
    return save_evaluation_config(data)


@app.get("/api/config/api-keys")
async def get_api_keys() -> dict:
    return get_api_key_status()


@app.put("/api/config/api-keys")
async def put_api_keys(data: dict) -> dict:
    updates = provider_api_key_updates(data)
    return save_local_env(updates)


def main() -> None:
    import uvicorn

    uvicorn.run("idealab.app:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    main()
