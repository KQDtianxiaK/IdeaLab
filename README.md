# IdeaLab

<p align="center">
  <a href="./README.md"><img alt="English" src="https://img.shields.io/badge/Language-English-2266DD"></a>
  <a href="./README.zh-CN.md"><img alt="中文" src="https://img.shields.io/badge/语言-中文-00A676"></a>
</p>

IdeaLab is a local, single-user AI research ideation system focused on
problem-driven idea generation, deep reasoning, evidence tracking, and
structured research reports.

Unlike AI Scientist-style systems that primarily optimize automated experiment
execution, IdeaLab starts earlier in the research workflow. Its goal is to help
researchers decide **what is worth pursuing** before investing heavily in
experiments.

IdeaLab turns a user-provided research question, direction, method idea, or
early result into a traceable reasoning graph:

```text
Problem -> Ideas -> Reasoning -> Validation -> Conclusion
```

The final output is not a short answer. It is a structured research reasoning
report with objective evaluation, literature evidence, candidate idea branches,
implementation plans, validation designs, risks, conclusions, and next steps.

## Current Status

IdeaLab is currently a local prototype. It is suitable for:

- exploring research directions;
- refining method ideas before experiments;
- comparing alternative solution paths;
- creating a traceable reasoning graph for discussion;
- generating a detailed staged research report.

It is not yet a full automated experiment platform. Code execution, sandboxed
experiments, benchmark evaluation, and paper-writing extensions are planned
future modules.

## Key Features

- Minimal web interface: a large IdeaLab title, one input box, and mode
  selection.
- Fixed workflow mode: follows a structured research reasoning pipeline.
- Free exploration mode: lets the AI agent choose the next best action.
- Reasoning graph UI: every stage becomes a node in a visual graph.
- Branching idea graph: multiple candidate ideas become independent branches
  before being merged into path comparison.
- Full-screen node reader: node details are rendered as readable cards with a
  table of contents, collapsible sections, bilingual field labels, and direct
  node switching.
- Human-in-the-loop injection: users can add thoughts during a run; the system
  injects them into later reasoning.
- Local configuration UI: prompts, model settings, and output token behavior
  can be edited from the browser.
- Local API key storage: API keys are stored in `idealab_config/.env`, never in
  browser local storage.
- Semantic Scholar integration: literature search is used as an evidence layer.
- Multi-stage model configuration: different stages can use different models,
  temperatures, and max-token settings.
- No-token-limit switch: `max_tokens: null` omits `max_tokens` from the model
  request.
- Historical runs: previous reasoning workspaces can be reopened.
- Fixed report template: final reports follow a 15-section research report
  format.

## Workflow

### Fixed Mode

The fixed workflow currently runs:

1. Problem normalization
2. Optional clarification for method ideas
3. Problem decomposition
4. Literature and evidence search
5. Candidate idea generation
6. Per-idea branch creation
7. Mechanism reasoning per branch
8. Critic and risk analysis per branch
9. Path comparison and ranking
10. Cross-review
11. Final research report generation

### Free Mode

In free mode, the AI agent can choose from actions such as:

- `decompose`
- `literature`
- `ideate`
- `reason`
- `critic`
- `compare`
- `validate`
- `report`

The goal is to maximize final research judgment quality rather than follow a
fixed sequence.

## Final Report Format

Final reports are generated as Markdown and stored at:

```text
idealab_workspaces/<run_id>/reports/report.md
```

The report follows this fixed 15-section structure:

1. Executive Summary
2. Input Parsing and Task Positioning
3. Background and Research Value
4. Initial Objective Evaluation
5. Key Problem Decomposition
6. Literature and Evidence Analysis
7. Candidate Ideas and Branch Reasoning
8. Path Comparison and Final Recommendation
9. Implementation Plan
10. Validation and Experiments
11. Result Analysis
12. Risks, Counterexamples, and Failure Modes
13. Conclusion
14. Next-Step Plan
15. Appendix

See [REPORT_TEMPLATE.md](REPORT_TEMPLATE.md) for the detailed Chinese template.

## Project Structure

```text
idealab/
├── app.py                 # FastAPI app and REST endpoints
├── config.py              # local config, prompt defaults, .env loading
├── engine.py              # fixed/free reasoning runners and report generation
├── llm.py                 # OpenAI-compatible chat-completion adapter
├── models.py              # Pydantic graph/run/node models
├── storage.py             # workspace and graph persistence
├── tools.py               # Semantic Scholar integration
├── requirements.txt       # Python dependencies
├── REPORT_TEMPLATE.md     # fixed research report template
└── static/
    ├── index.html         # web UI
    ├── styles.css         # visual styles
    └── app.js             # graph UI, settings, history, report viewer
```

Runtime files are created outside the package:

```text
idealab_config/
├── .env                   # local API keys, gitignored
├── models.json            # model/provider/stage configuration
└── prompts.json           # editable prompt templates

idealab_workspaces/
└── <run_id>/
    ├── graph.json         # reasoning graph
    ├── events.jsonl       # audit event stream
    ├── problem.json
    ├── ideas.json
    ├── evidence/
    └── reports/report.md
```

## Installation

Python 3.10+ is recommended.

### Option A: uv

From the repository root:

```bash
uv venv
source .venv/bin/activate
uv pip install -r idealab/requirements.txt
```

### Option B: pip

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r idealab/requirements.txt
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

The frontend and backend are served by the same FastAPI process.

## API Keys

IdeaLab can run with deterministic fallbacks when API keys are missing, but real
LLM reasoning and literature search require API keys.

Currently supported keys:

- `DEEPSEEK_API_KEY`
- `S2_API_KEY`

Recommended: open the settings panel in the web UI and save keys there. They
are written to:

```text
idealab_config/.env
```

This file is gitignored and keys are never echoed back to the browser.

You can also create it manually:

```bash
mkdir -p idealab_config
cat > idealab_config/.env <<'EOF'
DEEPSEEK_API_KEY="..."
S2_API_KEY="..."
EOF
```

Or export keys before starting:

```bash
export DEEPSEEK_API_KEY="..."
export S2_API_KEY="..."
python3 -m idealab.app
```

## Model and Prompt Configuration

Model configuration is stored in:

```text
idealab_config/models.json
```

Prompt configuration is stored in:

```text
idealab_config/prompts.json
```

Both can be edited from the settings panel.

Each stage can use its own model settings, for example:

- `default`
- `ideation`
- `critic`
- `report`

If a stage has:

```json
"max_tokens": null
```

IdeaLab omits `max_tokens` from the model API request.

## REST API

Main endpoints:

- `GET /` - web app
- `GET /api/health` - backend and API key status
- `POST /api/runs` - create a new reasoning run
- `GET /api/runs` - list historical runs
- `GET /api/runs/{run_id}/graph` - load a reasoning graph
- `POST /api/runs/{run_id}/human-input` - inject user input
- `POST /api/runs/{run_id}/stop` - stop a run
- `GET /api/runs/{run_id}/report` - load the final report
- `GET /api/config/models` / `PUT /api/config/models`
- `GET /api/config/prompts` / `PUT /api/config/prompts`
- `GET /api/config/api-keys` / `PUT /api/config/api-keys`

## Safety and Privacy

- API keys are stored locally in `idealab_config/.env`.
- API keys are not stored in browser local storage.
- Runtime workspaces are local under `idealab_workspaces/`.
- This is a single-user local prototype; do not expose it directly to the
  public internet without authentication, authorization, and sandboxing.

## Current Limitations

- No sandboxed code execution module yet.
- No automatic benchmark runner yet.
- No multi-user authentication.
- Report quality still depends on model quality and prompt design.
- Literature search is currently Semantic Scholar based and may miss relevant
  non-indexed sources.
- Evidence reliability scoring is still basic.

## Roadmap

Near-term:

- stronger input classification and clarification;
- richer evidence schema and citation handling;
- report references tied to evidence nodes;
- quality scoring for ideas and reports;
- better run comparison and review UI.

Mid-term:

- sandboxed code execution for minimal validation experiments;
- baseline and ablation runners;
- failure-case feedback into later reasoning loops;
- multi-model cross-review;
- export to paper, review memo, and presentation formats.

Long-term:

- plugin-based tool layer;
- project-level workspaces;
- benchmark-based evaluation of idea quality;
- integration with automated experiment systems.

## License

No license has been selected yet. Add a license before publishing or accepting
external contributions.
