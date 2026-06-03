# IdeaLab

<p align="center">
  <a href="./README.md"><img alt="English" src="https://img.shields.io/badge/Language-English-2266DD"></a>
  <a href="./README.zh-CN.md"><img alt="中文" src="https://img.shields.io/badge/语言-中文-00A676"></a>
</p>

IdeaLab is a local AI research ideation workbench. It helps researchers turn an
open question, research direction, method idea, or early result into a traceable
reasoning graph, quantitative idea evaluation, and a structured research report.

IdeaLab is intentionally positioned before full experiment automation. Its main
job is to help answer: **which idea is worth pursuing next, and why?**

## Status

IdeaLab is a local single-user prototype with an end-to-end research ideation
loop:

```text
problem -> decomposition -> literature -> ideation
-> per-idea reasoning + critic -> evaluation
-> comparison -> cross_review -> report
```

The current system can generate candidate ideas, reason through their mechanisms,
criticize each branch, run multi-dimensional pairwise evaluation, rank ideas with
BTL/Elo-style scores, and produce a final Markdown report.

Real experiment execution is not implemented yet. Experiment plans are included
in the evaluation loop as `planned` / `skipped` validation stubs and are clearly
reported as not executed.

## Highlights

- **Traceable reasoning graph**: each workflow step becomes a node with input,
  output, model provenance, tool calls, and status.
- **Human-friendly node reader**: node pages explain what the step does, surface
  key findings first, and hide raw JSON behind collapsible details.
- **Multi-model evaluation**: configurable judge stages compare candidate ideas
  pairwise across dimensions such as novelty, necessity, feasibility, impact,
  testability, risk, evidence strength, and information gain.
- **Quantitative ranking**: pairwise judgments are aggregated into BTL and Elo
  scores, dimension tables, model disagreement summaries, and Pareto categories.
- **Evidence-aware literature search**: Semantic Scholar queries are planned by
  the literature prompt, executed as multiple searches, de-duplicated, and stored
  as local evidence metadata.
- **Experiment-plan stubs**: each idea can receive minimum validation plans,
  metrics, controls, ablations, expected results, and failure signals without
  executing experiments.
- **Human-in-the-loop control**: users can inject comments, approvals, rejections,
  score overrides, merge hints, and recompute requests during a run.
- **Breakpoint resume**: failed or stopped fixed runs can resume from supported
  downstream nodes such as evaluation, comparison, cross-review, or report.
- **Local-first configuration**: providers, stage models, prompts, and API keys
  are editable from the browser and persisted locally.

## User Interface

The web UI is served by the same FastAPI process. It includes:

- a graph canvas with drag-to-pan and draggable nodes;
- node cards that show node type, status, summary, and model label;
- full-screen node details with a left-side table of contents;
- research decision overview with ranking, heatmap, battle log, evidence map,
  assumption ledger, validation plan, and human decision log;
- settings, history, overview, and report dialogs that close on backdrop click;
- Markdown report viewer.

## Project Structure

```text
.
├── README.md
├── README.zh-CN.md
├── REPORT_TEMPLATE.md     # Chinese report template
├── requirements.txt       # Python dependencies
└── idealab/
    ├── app.py             # FastAPI app and REST endpoints
    ├── config.py          # local config, defaults, .env loading
    ├── engine.py          # fixed/free workflows, resume, report generation
    ├── evaluation.py      # pairwise judging, BTL/Elo, experiment stubs
    ├── llm.py             # OpenAI-compatible chat-completion client
    ├── models.py          # Pydantic graph, node, run, evaluation models
    ├── storage.py         # workspace and graph persistence
    ├── tools.py           # Semantic Scholar integration
    └── static/
        ├── index.html     # browser UI
        ├── styles.css     # styles
        └── app.js         # graph UI, settings, overview, report viewer
```

Runtime files are created outside the package:

```text
idealab_config/
├── .env                   # local API keys, gitignored
├── models.json            # providers and stage model config
├── prompts.json           # editable prompt templates
└── evaluation.json        # dimensions, judge stages, evaluation policy

idealab_workspaces/
└── <run_id>/
    ├── graph.json
    ├── events.jsonl
    ├── problem.json
    ├── ideas.json
    ├── evidence/
    ├── evaluations/
    │   ├── evaluation_run.json
    │   ├── pairwise_judgments.jsonl
    │   └── rankings.json
    ├── experiments/
    │   └── plan_stubs.json
    └── reports/report.md
```

## Installation

Python 3.10+ is recommended.

### uv

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

### pip

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Quick Start

From the repository root:

```bash
python3 -m idealab.app
```

Open:

```text
http://127.0.0.1:8765
```

## API Keys

IdeaLab can run with deterministic fallbacks when keys are missing, but real
model calls and literature search require API keys.

Common keys:

- `DEEPSEEK_API_KEY`
- `CSTCLOUD_API_KEY`
- `S2_API_KEY`
- any custom provider key configured through `api_key_env`

Recommended setup: open the settings panel and save keys there. They are written
to:

```text
idealab_config/.env
```

Keys are not echoed back to the browser and are not stored in browser local
storage.

Manual setup is also supported:

```bash
mkdir -p idealab_config
printf 'DEEPSEEK_API_KEY="..."\nS2_API_KEY="..."\n' > idealab_config/.env
```

## Model and Prompt Configuration

IdeaLab uses OpenAI-compatible chat completion endpoints. Provider and stage
configuration is stored in:

```text
idealab_config/models.json
```

Important stage keys include:

- `default`
- `ideation`
- `critic`
- `report`
- `judge_primary`
- `judge_secondary`
- `evaluation_meta`

Prompt templates are stored in:

```text
idealab_config/prompts.json
```

Evaluation settings are stored in:

```text
idealab_config/evaluation.json
```

If a stage sets:

```json
"max_tokens": null
```

IdeaLab omits `max_tokens` from that model request.

## Evaluation Model

Evaluation is a first-class workflow stage, not a report appendix. The default
evaluation pipeline:

1. extracts up to `max_ideas` candidate ideas;
2. creates a pairwise comparison matrix;
3. sends each idea pair to every configured judge stage;
4. collects winners, confidence, reasoning, evidence references, and
   per-dimension scores;
5. aggregates results into BTL scores, Elo scores, dimension aggregates,
   model-disagreement summaries, and Pareto categories;
6. generates experiment-plan stubs;
7. runs an evaluation meta-review.

When a judge model call fails, IdeaLab records fallback judgments with lower
confidence. The UI and raw evaluation files preserve the `judge_model` and
fallback metadata so users can distinguish real model judgments from heuristic
fallbacks.

## REST API

Main endpoints:

- `GET /` - web app
- `GET /api/health` - backend and API key status
- `POST /api/runs` - create a run
- `GET /api/runs` - list runs
- `GET /api/runs/{run_id}/graph` - load a reasoning graph
- `POST /api/runs/{run_id}/human-input` - add human input
- `POST /api/runs/{run_id}/stop` - stop a run
- `POST /api/runs/{run_id}/resume` - breakpoint resume
- `GET /api/runs/{run_id}/report` - load the Markdown report
- `GET /api/runs/{run_id}/evaluation` - load evaluation output
- `POST /api/runs/{run_id}/evaluation/recompute` - recompute evaluation
- `POST /api/runs/{run_id}/evaluation/human-judgment` - append human judgment
- `GET /api/config/models` / `PUT /api/config/models`
- `GET /api/config/prompts` / `PUT /api/config/prompts`
- `GET /api/config/evaluation` / `PUT /api/config/evaluation`
- `GET /api/config/api-keys` / `PUT /api/config/api-keys`

## Safety and Privacy

- IdeaLab is designed as a local single-user prototype.
- Do not expose it to the public internet without authentication, authorization,
  sandboxing, and resource controls.
- API keys are stored locally in `idealab_config/.env`.
- Runtime workspaces can contain private prompts, ideas, reports, and model
  outputs. Review them before sharing.
- The current experiment stage only plans validation work; it does not execute
  code or run benchmarks.

## Current Limitations

- No sandboxed experiment execution yet.
- No benchmark runner, baseline runner, or ablation runner yet.
- Literature search depends on Semantic Scholar and local query quality.
- PDF downloading and full-text parsing are not implemented.
- No multi-user authentication or permission system.
- Evaluation quality depends on configured judge models, prompt quality, and
  whether calls fall back.

## Roadmap

Near term:

- stronger literature query planning and citation handling;
- richer evidence provenance and report citations;
- clearer fallback detection and judge health display;
- more granular human overrides for evaluation results.

Mid term:

- sandboxed minimal validation experiments;
- benchmark, baseline, ablation, and multi-seed runners;
- experiment results folded back into evaluation;
- export to review memo, paper outline, and presentation formats.

Long term:

- project-level workspaces;
- plugin-based tool layer;
- benchmark-based measurement of idea quality;
- integration with automated experiment systems.

## License

No license has been selected yet. Add a license before publishing or accepting
external contributions.
