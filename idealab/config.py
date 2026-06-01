from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
WORKSPACES_DIR = PROJECT_ROOT / "idealab_workspaces"
CONFIG_DIR = PROJECT_ROOT / "idealab_config"
STATIC_DIR = APP_DIR / "static"
LOCAL_ENV_FILE = CONFIG_DIR / ".env"
EVALUATION_CONFIG_FILE = CONFIG_DIR / "evaluation.json"


DEFAULT_MODELS = {
    "providers": {
        "deepseek": {
            "label": "DeepSeek",
            "base_url": "https://api.deepseek.com",
            "api_key_env": "DEEPSEEK_API_KEY",
            "default_model": "deepseek-v4-pro",
            "timeout_seconds": 60,
        },
        "openai_compatible": {
            "label": "Custom OpenAI Compatible",
            "base_url": "https://api.openai.com",
            "api_key_env": "OPENAI_COMPATIBLE_API_KEY",
            "default_model": "gpt-4.1",
            "timeout_seconds": 60,
        },
        "cstcloud": {
            "label": "CSTCloud Uni API",
            "base_url": "https://uni-api.cstcloud.cn/v1",
            "api_key_env": "CSTCLOUD_API_KEY",
            "default_model": "minimax-m27",
            "timeout_seconds": 60,
        }
    },
    "stage_models": {
        "default": {
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "temperature": 0.4,
            "max_tokens": 8000,
        },
        "ideation": {
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "temperature": 0.8,
            "max_tokens": 12000,
        },
        "critic": {
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "temperature": 0.25,
            "max_tokens": 10000,
        },
        "judge_primary": {
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "temperature": 0.2,
            "max_tokens": 8000,
        },
        "judge_secondary": {
            "provider": "cstcloud",
            "model": "minimax-m27",
            "temperature": 0.25,
            "max_tokens": 8000,
        },
        "evaluation_meta": {
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "temperature": 0.25,
            "max_tokens": 8000,
        },
        "report": {
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "temperature": 0.35,
            "max_tokens": None,
        },
    },
}


DEFAULT_PROMPTS = {
    "version": 1,
    "fixed": {
        "problem": """你是 IdeaLab 的问题识别与研究任务建模专家。你的任务不是复述用户输入，而是判断用户输入属于哪一类研究起点，并建立后续推演所需的客观任务画像。

必须区分：
1. question：用户主要提出一个开放问题，希望寻找解决方案。
2. method_idea：用户提出一个具体方法/机制/系统设计，希望评估与完善。
3. research_direction：用户给出宽泛研究方向，需要收敛成若干可推进问题。
4. experiment_result：用户给出已有结果，需要解释、归因或继续设计。

输出 JSON，字段包括：
title, input_type, domain, problem_stage, objective, core_claim_or_question, background, hidden_assumptions, success_criteria, clarification_questions, initial_objective_evaluation。
initial_objective_evaluation 必须从 feasibility, necessity, novelty 三方面客观评价，每项给 score(0-10) 与 rationale。
如果 input_type=method_idea，clarification_questions 应提出 3-6 个确认用户意图的问题。""",
        "decompose": """你是 IdeaLab 的问题拆解专家。基于 ProblemSpec，将任务拆解成可以推演和验证的子结构。

输出 JSON，字段包括：
summary, problem_frame, sub_questions, variables, assumptions, unknowns, evaluation_dimensions, possible_failure_modes, minimum_useful_evidence。

要求：
- 对 question 输入，重点拆出解决此问题需要回答的关键子问题。
- 对 method_idea 输入，重点拆出该方法成立所需的机制假设、边界条件、与替代方法的比较维度。
- 每个 assumption 要说明如果它是错的，会怎样影响最终结论。""",
        "literature": """你是 IdeaLab 的文献检索规划专家。基于当前问题画像和拆解结果，设计文献检索策略并解释证据缺口。

输出 JSON，字段包括：
summary, search_queries, expected_evidence, novelty_risks, known_baseline_categories, evidence_gaps。

要求：
- search_queries 应覆盖直接相关工作、替代方法、失败/负结果、评测方法。
- 不要只生成一个宽泛 query。
- 文献证据的作用是判断必要性、创新性、可行性，而不是装饰报告。""",
        "ideation": """你是 IdeaLab 的研究想法生成专家。根据问题画像、拆解、文献证据和人类补充输入，生成高质量研究路线。

输出 JSON，字段包括 summary 和 ideas。ideas 中每个元素包括：
id, title, target_problem, hypothesis, proposed_mechanism, why_it_might_work, implementation_variants, required_evidence, key_assumptions, expected_results, risks, cheapest_validation, novelty_position。

要求：
- 如果用户输入是 question：生成若干可解决该问题的方案。
- 如果用户输入是 method_idea：先完善该 idea，再给出几个实现变体与可能替代方案。
- idea 必须足够具体，能推导到实现方法或验证实验。""",
        "reason": """你是 IdeaLab 的深层推演专家。围绕每个候选 idea 展开机制推理，而不是泛泛评价。

输出 JSON，字段包括 summary 和 reasoning_paths。每条 reasoning_path 包括：
idea_id, causal_chain, implementation_details, expected_observations, validation_design, possible_counterexamples, what_would_change_our_mind。

要求：
- implementation_details 必须写到可执行层级，包括算法步骤、系统模块、关键数据结构或伪代码。
- 如果适合实验验证，提出最小验证实验与指标。
- 明确哪些结论只是推测，哪些有文献或逻辑支持。""",
        "critic": """你是 IdeaLab 的严苛审稿人与反方科学家。你必须主动寻找当前 idea 和推演的弱点。

输出 JSON，字段包括 summary, objective_evaluation, critical_risks, alternative_explanations, missing_controls, likely_failure_cases, required_revisions。

objective_evaluation 必须从 feasibility, necessity, novelty 三方面重新打分，并说明与初始评价相比是否变化。
不要为了平衡而温和表达；如果 idea 不可行，应明确指出。""",
        "compare": """你是 IdeaLab 的研究路线决策专家。基于想法、推演、反方批判和证据，对候选路线排序。

输出 JSON，字段包括 summary, ranked_ideas, recommended_route, rejected_or_deprioritized_routes, validation_roadmap。

ranked_ideas 每项必须包括：
rank, idea_id, title, scores(novelty, feasibility, necessity, impact, testability, evidence_strength), rationale, recommended_next_experiment。

不要只按平均分排序；要说明 tradeoff：高风险高收益、低成本 quick win、应放弃路线。""",
        "review": """你是 IdeaLab 的交叉审查者。检查整条推演链是否自洽、是否遗漏关键证据、是否把想象当成结论。

输出 JSON，字段包括 summary, consistency_check, unsupported_claims, overconfident_claims, missing_experiments, final_report_warnings。

要求：
- 标记报告中必须保留的不确定性。
- 标记最需要用户或实验确认的地方。
- 如果用户输入是 method_idea，指出还没有得到用户确认的假设。""",
        "evaluation_dimension_design": """你是 IdeaLab 的评估维度设计专家。你的任务是基于输入类型、领域、问题拆解和文献证据，检查默认 Evaluation 维度是否足够。

默认维度包括 novelty, necessity, feasibility, impact, testability, risk, evidence_strength, information_gain。

输出 JSON，字段包括：
summary, adjusted_dimensions, disabled_dimensions, added_dimensions, rationale, caution。

要求：
- 不要随意删除默认维度；只有明显不适用时才禁用。
- added_dimensions 必须给出 id, label, description, weight, higher_is_better。
- 维度必须可被 0-10 量化，并适合成对比较。""",
        "pairwise_judge": """你是 IdeaLab 的证据约束型科研想法评估裁判。你要比较两个候选 idea，而不是分别给好听的评价。

必须严格基于：
1. 问题目标与成功标准；
2. 当前文献和证据；
3. 机制清晰度、创新性、必要性、可行性、影响力、可验证性、风险、证据强度、信息增益；
4. 真实实验尚未执行这一事实。

输出 JSON，字段包括：
winner(A/B/tie), confidence(0-1), dimension_scores, reasoning, evidence_refs, critical_uncertainties, experiment_needed。

dimension_scores 必须以维度 id 为 key，每个维度包含 A, B, rationale。A/B 分数为 0-10，Risk 维度分数越高表示风险越低。
reasoning 必须说明胜者为什么在当前证据下更值得推进。如果无法判断，winner 输出 tie。
不要根据文字流畅度、篇幅或表述自信程度选择胜者。""",
        "meta_review": """你是 IdeaLab 的评估汇总与系统反馈专家。你不再评估单个 idea，而是综合所有模型 judge 的成对比较、BTL/Elo 排名、维度分、分歧对、证据缺口和人工输入，生成系统级 meta-review。

输出 JSON，字段包括：
summary, stable_recommendations, model_disagreements, evidence_gaps, human_review_needed, prompt_feedback, next_evaluation_actions。

要求：
- stable_recommendations 说明哪些推荐在多模型下稳定。
- model_disagreements 说明哪些 pair 或维度分歧最大。
- human_review_needed 必须列出最需要人工确认的问题。
- prompt_feedback 给出下一轮生成、critic 或 judge prompt 应补强的系统级反馈。
- 必须明确区分文献证据、模型推理、人工输入和未执行实验。""",
        "evaluation_meta": """你是 IdeaLab 的评估汇总专家。基于多个模型的成对比较、维度分和证据，生成系统级评估摘要。

输出 JSON，字段包括：
summary, stable_recommendations, model_disagreements, evidence_gaps, human_review_needed, next_evaluation_actions。

必须明确区分文献证据、模型推理、人工输入和未执行实验。""",
        "idea_evolution": """你是 IdeaLab 的 idea evolution agent。你要基于 Evaluation 反馈改进候选 idea，而不是简单重写原文。

输入会包含原始 idea、critic、pairwise judge 理由、维度短板和 meta-review。

输出 JSON，字段包括：
summary, evolved_ideas, retired_ideas, retained_assumptions, new_validation_priorities。

evolved_ideas 每项必须包含 source_idea_id, title, hypothesis, what_changed, why_changed, expected_gain, new_risks, cheapest_validation。

要求：
- 保留原 idea 的可追踪来源。
- 只针对明确短板修改，例如新颖性不足、机制不清、验证成本高、证据弱。
- 不要因为评估结果差就自动美化；不可救的 idea 应进入 retired_ideas。""",
        "experiment_planning_stub": """你是 IdeaLab 的验证规划专家。你只规划最小验证实验，不执行实验、不声称已有真实实验结果。

输出 JSON，字段包括：
idea_id, status, reason_not_executed, minimum_validation, metrics, controls, ablation_plan, expected_result, failure_signal。

status 只能是 planned 或 skipped。reason_not_executed 必须说明当前 Phase 1 尚未实现实验执行。""",
        "report": """你是 IdeaLab 的最终研究报告作者。你要生成的是面向研究者的完整研究推演报告，而不是摘要、流程日志或节点完成情况列表。

输出 JSON：{"report_markdown": "..."}。

报告必须是详细 Markdown，必须有目录、标题、小标题和正文段落，固定使用以下 15 节结构：

## 目录

1. Executive Summary
2. 输入解析与任务定位
3. 问题背景与研究价值
4. 初始客观评价
5. 关键问题拆解
6. 文献与证据分析
7. 候选想法与分支推演
8. 路径比较与最终推荐
9. 实现方案
10. 验证与实验
11. 结果分析
12. 风险、反例与失败模式
13. 结论
14. 下一步计划
15. 附录

每节写作要求：
1. Executive Summary：用 3-6 段说明最终判断、推荐主路线/备选路线、证据状态、最关键下一步。不能只写几条 bullet。
2. 输入解析与任务定位：保留原始输入核心内容，判断输入类型(question/method_idea/research_direction/experiment_result)，判断研究阶段，列出需要用户确认的问题及是否已确认。
3. 问题背景与研究价值：说明领域背景、痛点、必要性、成功标准。
4. 初始客观评价：从可行性、必要性、创新性三方面给分和理由，并给总体判断。
5. 关键问题拆解：写子问题、关键变量、隐含假设、如果假设为假会怎样、如何验证、最低证据需求。
6. 文献与证据分析：说明检索策略、相关工作分组、关键支持证据、削弱证据、证据缺口、创新性风险。不要逐篇堆砌摘要。
7. 候选想法与分支推演：每个候选想法作为独立分支，包含核心假设、机制推演、实现变体、最小验证、风险与反例。
8. 路径比较与最终推荐：按创新性、可行性、必要性、影响力、可验证性、证据强度、实现成本、风险比较，给排序表、推荐路线、暂缓/放弃路线。
9. 实现方案：写系统设计、模块、数据流、接口、算法步骤、关键代码或伪代码、工程约束。
10. 验证与实验：区分已完成验证与未完成验证。如果没有真实实验，必须明确写“尚未进行真实实验验证”，并给最小验证实验、对照组、指标、消融实验。
11. 结果分析：如果有实验结果，解释主要结果、失败样例和可信度；如果没有实验结果，分析预期结果、证据强度和当前不能下结论的部分。
12. 风险、反例与失败模式：覆盖技术风险、研究风险、工程风险、反例、必须保留的不确定性。
13. 结论：用完整段落总结当前 idea 是否成立、最值得推进方向、证据是否足以支持继续投入、哪些仍是待验证假设。
14. 下一步计划：分“立即执行”“短期迭代”“长期路线”给可执行计划。
15. 附录：列推演节点索引、文献列表、配置与模型、必要原始结构化数据引用。

禁止把报告写成“节点完成情况列表”。节点只能作为附录或证据来源，不是报告主体。""",
    },
    "free": {
        "policy": """你是 IdeaLab 自由探索 agent。目标是最大化最终研究结论质量，而不是机械执行固定阶段。

每一步从以下动作中选择一个：decompose, literature, ideate, reason, critic, compare, validate, report。
输出 JSON：action, reason, expected_information_gain, stop_condition。

选择原则：
- 如果问题不清，先 decompose。
- 如果创新性不明，先 literature。
- 如果方案太少，ideate。
- 如果已有方案但机制不清，reason。
- 如果方案听起来过于顺利，critic。
- 如果已有多个路线，compare。
- 如果关键假设可低成本验证，validate。
- 如果已经足够形成结论，report。""",
        "step": """基于当前图谱、人类输入和你选择的动作，执行一步高质量自由探索。

输出 JSON，字段包括 summary, findings, evidence_or_reasoning, implications, next_step。
内容必须面向最终研究判断推进，不能只描述“我完成了某一步”。""",
    },
}


DEFAULT_EVALUATION = {
    "pairing_strategy": "full_matrix_until_5_then_sample",
    "max_ideas": 5,
    "judge_stages": ["judge_primary", "judge_secondary"],
    "experiment_policy": "plan_only",
    "dimensions": [
        {
            "id": "novelty",
            "label": "Novelty",
            "description": "是否区别于已有工作。",
            "scale": "0-10",
            "higher_is_better": True,
            "weight": 1.0,
            "enabled": True,
        },
        {
            "id": "necessity",
            "label": "Necessity",
            "description": "是否解决真实且重要的问题。",
            "scale": "0-10",
            "higher_is_better": True,
            "weight": 1.0,
            "enabled": True,
        },
        {
            "id": "feasibility",
            "label": "Feasibility",
            "description": "当前资源和技术条件下是否可推进。",
            "scale": "0-10",
            "higher_is_better": True,
            "weight": 1.0,
            "enabled": True,
        },
        {
            "id": "impact",
            "label": "Impact",
            "description": "成功后理论、方法或应用贡献。",
            "scale": "0-10",
            "higher_is_better": True,
            "weight": 1.0,
            "enabled": True,
        },
        {
            "id": "testability",
            "label": "Testability",
            "description": "是否存在低成本验证路径。",
            "scale": "0-10",
            "higher_is_better": True,
            "weight": 1.0,
            "enabled": True,
        },
        {
            "id": "risk",
            "label": "Risk",
            "description": "失败概率、失败代价和关键 blocker；分数越高表示风险越低。",
            "scale": "0-10",
            "higher_is_better": True,
            "weight": 1.0,
            "enabled": True,
        },
        {
            "id": "evidence_strength",
            "label": "Evidence Strength",
            "description": "当前文献、逻辑和已有结果支持强度。",
            "scale": "0-10",
            "higher_is_better": True,
            "weight": 1.0,
            "enabled": True,
        },
        {
            "id": "information_gain",
            "label": "Information Gain",
            "description": "验证后能学到多少，是否值得试。",
            "scale": "0-10",
            "higher_is_better": True,
            "weight": 1.0,
            "enabled": True,
        },
    ],
}


LEGACY_PROMPT_MARKERS = {
    "fixed.problem": "把用户输入规范化为研究问题，提取目标、领域、约束和成功标准。输出 JSON。",
    "fixed.report": "根据完整推演图生成结构化 Markdown 研究推演报告。",
    "free.step": "基于当前节点图和人类输入，执行你选择的探索动作。输出可追踪节点内容 JSON。",
}


def ensure_dirs() -> None:
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    if not key:
        return None
    return key, value


def load_local_env() -> dict[str, str]:
    ensure_dirs()
    values: dict[str, str] = {}
    if not LOCAL_ENV_FILE.exists():
        return values
    for line in LOCAL_ENV_FILE.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(line)
        if not parsed:
            continue
        key, value = parsed
        values[key] = value
        os.environ[key] = value
    return values


def _write_local_env_values(updates: dict[str, str]) -> None:
    ensure_dirs()
    current = load_local_env()
    for key, value in updates.items():
        clean_key = key.strip()
        clean_value = value.strip()
        if not clean_key or not clean_value:
            continue
        current[clean_key] = clean_value
        os.environ[clean_key] = clean_value

    lines = ["# IdeaLab local API keys. This file is gitignored."]
    for key in sorted(current):
        escaped = current[key].replace('"', '\\"')
        lines.append(f'{key}="{escaped}"')
    LOCAL_ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_local_env(updates: dict[str, str]) -> dict[str, Any]:
    _write_local_env_values(updates)
    return get_api_key_status()


def _looks_like_secret(value: str | None) -> bool:
    if not value:
        return False
    if value.startswith(("sk-", "sk_", "hf_", "AIza")):
        return True
    return not value.replace("_", "").isalnum() or value.upper() != value


def _sanitize_models_config(data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    changed = False
    providers = data.setdefault("providers", {})
    for provider_name, provider in providers.items():
        if not isinstance(provider, dict):
            continue
        default_env = f"{str(provider_name).upper()}_API_KEY"
        api_key_env = provider.get("api_key_env")
        if isinstance(api_key_env, str) and _looks_like_secret(api_key_env):
            _write_local_env_values({default_env: api_key_env})
            provider["api_key_env"] = default_env
            changed = True
        elif not api_key_env:
            provider["api_key_env"] = default_env
            changed = True
    return data, changed


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def _merge_missing(default: Any, data: Any) -> tuple[Any, bool]:
    if isinstance(default, dict) and isinstance(data, dict):
        changed = False
        merged = dict(data)
        for key, value in default.items():
            if key not in merged:
                merged[key] = value
                changed = True
                continue
            merged_value, child_changed = _merge_missing(value, merged[key])
            merged[key] = merged_value
            changed = changed or child_changed
        return merged, changed
    return data, False


def get_models_config() -> dict[str, Any]:
    ensure_dirs()
    path = CONFIG_DIR / "models.json"
    if not path.exists():
        write_json(path, DEFAULT_MODELS)
    data = read_json(path, DEFAULT_MODELS)
    data, merged = _merge_missing(DEFAULT_MODELS, data)
    data, changed = _sanitize_models_config(data)
    changed = _upgrade_legacy_model_limits(data) or _upgrade_phase2_judge_defaults(data) or changed or merged
    if changed:
        write_json(path, data)
    return data


def save_models_config(data: dict[str, Any]) -> dict[str, Any]:
    data, _ = _sanitize_models_config(data)
    write_json(CONFIG_DIR / "models.json", data)
    return data


def get_prompts_config() -> dict[str, Any]:
    ensure_dirs()
    path = CONFIG_DIR / "prompts.json"
    if not path.exists():
        write_json(path, DEFAULT_PROMPTS)
    data = read_json(path, DEFAULT_PROMPTS)
    if _is_legacy_prompts(data):
        data = DEFAULT_PROMPTS
        write_json(path, data)
    else:
        data, merged = _merge_missing(DEFAULT_PROMPTS, data)
        if _upgrade_old_report_prompt(data) or merged:
            write_json(path, data)
    return data


def get_evaluation_config() -> dict[str, Any]:
    ensure_dirs()
    if not EVALUATION_CONFIG_FILE.exists():
        write_json(EVALUATION_CONFIG_FILE, DEFAULT_EVALUATION)
    data = read_json(EVALUATION_CONFIG_FILE, DEFAULT_EVALUATION)
    data, changed = _merge_missing(DEFAULT_EVALUATION, data)
    if changed:
        write_json(EVALUATION_CONFIG_FILE, data)
    return data


def save_evaluation_config(data: dict[str, Any]) -> dict[str, Any]:
    data, _ = _merge_missing(DEFAULT_EVALUATION, data)
    write_json(EVALUATION_CONFIG_FILE, data)
    return data


def save_prompts_config(data: dict[str, Any]) -> dict[str, Any]:
    current_version = int(data.get("version", 1))
    data["version"] = current_version + 1
    write_json(CONFIG_DIR / "prompts.json", data)
    return data


def _upgrade_legacy_model_limits(data: dict[str, Any]) -> bool:
    changed = False
    stage_models = data.setdefault("stage_models", {})
    legacy_to_current = {
        "default": (2200, 8000),
        "ideation": (3200, 12000),
        "critic": (2600, 10000),
        "report": (5000, None),
    }
    for stage, (legacy_value, current_value) in legacy_to_current.items():
        cfg = stage_models.get(stage)
        if isinstance(cfg, dict) and cfg.get("max_tokens") == legacy_value:
            cfg["max_tokens"] = current_value
            changed = True
    return changed


def _upgrade_phase2_judge_defaults(data: dict[str, Any]) -> bool:
    stage_models = data.setdefault("stage_models", {})
    cfg = stage_models.get("judge_secondary")
    if (
        isinstance(cfg, dict)
        and cfg.get("provider") == "deepseek"
        and cfg.get("model") in {"deepseek-v4-pro", "deepseek-reasoner"}
        and cfg.get("max_tokens") == 8000
    ):
        cfg["provider"] = "cstcloud"
        cfg["model"] = "minimax-m27"
        cfg["temperature"] = 0.25
        return True
    return False


def _is_legacy_prompts(data: dict[str, Any]) -> bool:
    for dotted_key, legacy_value in LEGACY_PROMPT_MARKERS.items():
        section, key = dotted_key.split(".", 1)
        if data.get(section, {}).get(key) != legacy_value:
            return False
    return True


def _upgrade_old_report_prompt(data: dict[str, Any]) -> bool:
    fixed = data.setdefault("fixed", {})
    report = fixed.get("report", "")
    if (
        isinstance(report, str)
        and "1. Executive Summary：直接说明 IdeaLab 最终判断和推荐路线。" in report
        and "9. 结论与下一步建议：给出可执行路线图。" in report
        and "15. 附录" not in report
    ):
        fixed["report"] = DEFAULT_PROMPTS["fixed"]["report"]
        return True
    return False


def env_is_set(name: str | None) -> bool:
    load_local_env()
    return bool(name and os.getenv(name))


def provider_api_key_updates(data: dict[str, Any]) -> dict[str, str]:
    models = get_models_config()
    providers = models.get("providers", {})
    updates: dict[str, str] = {}

    legacy = {
        "deepseek_api_key": "deepseek",
        "semantic_scholar_api_key": None,
    }
    for payload_key, provider_name in legacy.items():
        value = str(data.get(payload_key) or "").strip()
        if not value:
            continue
        if provider_name is None:
            updates["S2_API_KEY"] = value
            continue
        provider = providers.get(provider_name, {})
        env_name = provider.get("api_key_env") or f"{provider_name.upper()}_API_KEY"
        updates[str(env_name)] = value

    provider_keys = data.get("provider_api_keys", {})
    if isinstance(provider_keys, dict):
        for provider_name, value in provider_keys.items():
            clean_value = str(value or "").strip()
            if not clean_value:
                continue
            provider = providers.get(str(provider_name), {})
            env_name = provider.get("api_key_env") or f"{str(provider_name).upper()}_API_KEY"
            updates[str(env_name)] = clean_value

    env_values = data.get("env_values", {})
    if isinstance(env_values, dict):
        for env_name, value in env_values.items():
            clean_env = str(env_name or "").strip()
            clean_value = str(value or "").strip()
            if clean_env and clean_value:
                updates[clean_env] = clean_value
    return updates


def get_api_key_status() -> dict[str, Any]:
    load_local_env()
    models = get_models_config()
    providers = models.get("providers", {})
    stage_models = models.get("stage_models", {})
    used_providers = {
        cfg.get("provider")
        for cfg in stage_models.values()
        if isinstance(cfg, dict) and cfg.get("provider")
    }
    provider_status: dict[str, dict[str, Any]] = {}
    for name, provider in providers.items():
        if not isinstance(provider, dict):
            continue
        env_name = provider.get("api_key_env") or f"{str(name).upper()}_API_KEY"
        provider_status[str(name)] = {
            "label": provider.get("label") or name,
            "api_key_env": env_name,
            "configured": bool(os.getenv(str(env_name))),
            "required": name in used_providers,
        }
    status: dict[str, Any] = {
        "providers": provider_status,
        "semantic_scholar": bool(os.getenv("S2_API_KEY")),
    }
    status["deepseek"] = provider_status.get("deepseek", {}).get("configured", False)
    required_ok = all(
        item["configured"]
        for item in provider_status.values()
        if item.get("required")
    )
    status["all_required"] = required_ok and status["semantic_scholar"]
    return status


load_local_env()
