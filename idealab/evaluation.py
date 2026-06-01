from __future__ import annotations

import json
import math
from itertools import combinations
from pathlib import Path
from typing import Any

from .config import get_evaluation_config, get_prompts_config, write_json
from .llm import LLMClient
from .models import (
    EvaluationRun,
    EvaluationSpec,
    ExperimentPlanStub,
    HumanEvaluationJudgmentRequest,
    PairwiseJudgment,
    ScoreDimension,
    new_id,
    now_iso,
)
from .storage import append_event, load_graph


def load_evaluation(workspace: Path) -> dict[str, Any] | None:
    path = workspace / "evaluations" / "evaluation_run.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def append_human_judgment(workspace: Path, request: HumanEvaluationJudgmentRequest) -> dict[str, Any]:
    evaluation = load_evaluation(workspace)
    if not evaluation:
        raise FileNotFoundError("Evaluation has not been generated for this run.")

    override = {
        "timestamp": now_iso(),
        "judge_model": "human",
        "idea_a_id": request.idea_a_id,
        "idea_b_id": request.idea_b_id,
        "winner": request.winner,
        "confidence": request.confidence,
        "reasoning": request.reasoning,
    }
    evaluation.setdefault("human_judgments", []).append(override)
    matched = False
    for judgment in evaluation.get("judgments", []):
        same_order = judgment.get("idea_a_id") == request.idea_a_id and judgment.get("idea_b_id") == request.idea_b_id
        reverse_order = judgment.get("idea_a_id") == request.idea_b_id and judgment.get("idea_b_id") == request.idea_a_id
        if same_order or reverse_order:
            judgment.setdefault("human_overrides", []).append(override)
            matched = True
    if not matched:
        evaluation.setdefault("judgments", []).append(
            PairwiseJudgment(
                pair_id=f"human_{request.idea_a_id}_{request.idea_b_id}",
                idea_a_id=request.idea_a_id,
                idea_b_id=request.idea_b_id,
                judge_model="human",
                winner=request.winner,
                confidence=request.confidence,
                reasoning=request.reasoning,
            ).model_dump()
        )
    evaluation["updated_at"] = now_iso()
    write_json(workspace / "evaluations" / "evaluation_run.json", evaluation)
    append_event(workspace, {"type": "human_evaluation_judgment", "judgment": override})
    return evaluation


class EvaluationService:
    def __init__(self) -> None:
        self.llm = LLMClient()

    def run(
        self,
        workspace: Path,
        problem: Any,
        ideas: Any,
        branches: list[dict[str, Any]],
        evidence: Any,
    ) -> dict[str, Any]:
        config = get_evaluation_config()
        prompts = get_prompts_config()
        fixed_prompts = prompts.get("fixed", {})
        dimensions = self._dimensions(config)
        idea_items = self._idea_items(ideas)[: int(config.get("max_ideas", 5))]
        idea_items = self._normalize_idea_ids(idea_items)
        judge_stages = [str(stage) for stage in config.get("judge_stages", ["judge_primary", "judge_secondary"]) if str(stage).strip()]
        spec = EvaluationSpec(
            run_id=load_graph(workspace).run_id,
            target_type="idea",
            idea_type=self._idea_type(problem),
            dimensions=dimensions,
            judge_models=[self.llm.model_label(stage) for stage in judge_stages],
            pairing_strategy=str(config.get("pairing_strategy", "full_matrix_until_5_then_sample")),
            experiment_policy=str(config.get("experiment_policy", "plan_only")),
        )

        judgments: list[PairwiseJudgment] = []
        pairs = list(combinations(idea_items, 2))
        for pair_index, (idea_a, idea_b) in enumerate(pairs, start=1):
            pair_id = f"pair_{pair_index:03d}_{idea_a['id']}_{idea_b['id']}"
            for stage in judge_stages:
                fallback = self._fallback_pairwise(pair_id, idea_a, idea_b, dimensions, stage)
                data, meta = self.llm.complete_json(
                    stage=stage,
                    system=fixed_prompts.get("pairwise_judge", ""),
                    user=json.dumps(
                        {
                            "problem": problem,
                            "idea_a": idea_a,
                            "idea_b": idea_b,
                            "branches": self._branches_for_pair(branches, idea_a["id"], idea_b["id"]),
                            "evidence": evidence,
                            "dimensions": [dimension.model_dump() for dimension in dimensions],
                            "experiment_policy": "plan_only",
                            "instruction": "真实实验尚未执行；只能比较当前证据、推理和验证计划。",
                        },
                        ensure_ascii=False,
                    ),
                    fallback=fallback,
                )
                judgments.append(self._judgment_from_llm(pair_id, idea_a["id"], idea_b["id"], stage, data, meta, dimensions))

        btl_scores = self._btl_scores(idea_items, judgments)
        elo_scores = self._elo_scores(idea_items, judgments)
        dimension_aggregates = self._dimension_aggregates(idea_items, judgments, dimensions)
        model_disagreement = self._model_disagreement(judgments)
        pareto_categories = self._pareto_categories(idea_items, btl_scores, dimension_aggregates)
        experiment_plans = self._experiment_plans(workspace, idea_items, fixed_prompts.get("experiment_planning_stub", ""))
        meta_review = self._meta_review(
            problem=problem,
            ideas=idea_items,
            judgments=judgments,
            btl_scores=btl_scores,
            elo_scores=elo_scores,
            dimension_aggregates=dimension_aggregates,
            model_disagreement=model_disagreement,
            pareto_categories=pareto_categories,
            evidence=evidence,
            prompt=fixed_prompts.get("meta_review") or fixed_prompts.get("evaluation_meta", ""),
        )

        run = EvaluationRun(
            evaluation_id=new_id("eval"),
            status="completed",
            spec=spec,
            judgments=judgments,
            btl_scores=btl_scores,
            elo_scores=elo_scores,
            dimension_aggregates=dimension_aggregates,
            model_disagreement=model_disagreement,
            meta_review=meta_review,
            pareto_categories=pareto_categories,
            experiment_plans=experiment_plans,
        )
        payload = run.model_dump()
        self._write_outputs(workspace, payload)
        return payload

    def _write_outputs(self, workspace: Path, payload: dict[str, Any]) -> None:
        eval_dir = workspace / "evaluations"
        exp_dir = workspace / "experiments"
        eval_dir.mkdir(parents=True, exist_ok=True)
        exp_dir.mkdir(parents=True, exist_ok=True)
        write_json(eval_dir / "evaluation_run.json", payload)
        with (eval_dir / "pairwise_judgments.jsonl").open("w", encoding="utf-8") as f:
            for judgment in payload.get("judgments", []):
                f.write(json.dumps(judgment, ensure_ascii=False) + "\n")
        write_json(
            eval_dir / "rankings.json",
            {
                "btl_scores": payload.get("btl_scores", {}),
                "elo_scores": payload.get("elo_scores", {}),
                "dimension_aggregates": payload.get("dimension_aggregates", {}),
                "pareto_categories": payload.get("pareto_categories", {}),
                "model_disagreement": payload.get("model_disagreement", {}),
                "meta_review": payload.get("meta_review", {}),
            },
        )
        write_json(exp_dir / "plan_stubs.json", payload.get("experiment_plans", []))
        append_event(workspace, {"type": "evaluation_completed", "evaluation_id": payload.get("evaluation_id")})

    def _dimensions(self, config: dict[str, Any]) -> list[ScoreDimension]:
        items = config.get("dimensions", [])
        dimensions = []
        for item in items:
            if isinstance(item, dict) and item.get("enabled", True):
                dimensions.append(ScoreDimension.model_validate(item))
        return dimensions

    def _idea_type(self, problem: Any) -> str:
        if isinstance(problem, dict):
            return str(problem.get("input_type") or "unknown")
        return "unknown"

    def _idea_items(self, ideas: Any) -> list[dict[str, Any]]:
        if isinstance(ideas, dict) and isinstance(ideas.get("ideas"), list):
            return [item for item in ideas["ideas"] if isinstance(item, dict)]
        if isinstance(ideas, list):
            return [item for item in ideas if isinstance(item, dict)]
        return []

    def _normalize_idea_ids(self, ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = []
        seen: set[str] = set()
        for index, idea in enumerate(ideas, start=1):
            item = dict(idea)
            raw_id = str(item.get("id") or item.get("idea_id") or f"I{index}")
            idea_id = raw_id if raw_id not in seen else f"{raw_id}_{index}"
            item["id"] = idea_id
            seen.add(idea_id)
            normalized.append(item)
        return normalized

    def _branches_for_pair(self, branches: list[dict[str, Any]], idea_a_id: str, idea_b_id: str) -> list[dict[str, Any]]:
        selected = []
        for branch in branches:
            idea = branch.get("idea", {})
            if not isinstance(idea, dict):
                continue
            if str(idea.get("id") or idea.get("idea_id")) in {idea_a_id, idea_b_id}:
                selected.append(branch)
        return selected

    def _fallback_pairwise(
        self,
        pair_id: str,
        idea_a: dict[str, Any],
        idea_b: dict[str, Any],
        dimensions: list[ScoreDimension],
        stage: str,
    ) -> dict[str, Any]:
        scores = {}
        total_a = 0.0
        total_b = 0.0
        for idx, dimension in enumerate(dimensions):
            score_a = self._heuristic_score(idea_a, dimension.id, idx)
            score_b = self._heuristic_score(idea_b, dimension.id, idx + 1)
            total_a += score_a * dimension.weight
            total_b += score_b * dimension.weight
            scores[dimension.id] = {
                "A": score_a,
                "B": score_b,
                "rationale": "Fallback heuristic score because the configured judge model was unavailable.",
            }
        if abs(total_a - total_b) < 0.5:
            winner = "tie"
        else:
            winner = "A" if total_a > total_b else "B"
        return {
            "pair_id": pair_id,
            "winner": winner,
            "confidence": 0.45,
            "dimension_scores": scores,
            "reasoning": f"Fallback evaluation from {stage}; no real experiment has been executed.",
            "evidence_refs": [],
            "critical_uncertainties": ["需要真实模型裁判和实验验证校准该比较。"],
            "experiment_needed": True,
        }

    def _heuristic_score(self, idea: dict[str, Any], dimension_id: str, offset: int) -> float:
        text = json.dumps(idea, ensure_ascii=False).lower()
        base = 5.0 + min(len(text), 1200) / 600.0
        signals = {
            "novelty": ["novel", "创新", "new", "different", "gap"],
            "necessity": ["need", "必要", "痛点", "problem", "目标"],
            "feasibility": ["implementation", "实现", "simple", "low-cost", "baseline"],
            "impact": ["impact", "贡献", "significant", "important"],
            "testability": ["validation", "验证", "experiment", "metric", "cheapest"],
            "risk": ["risk", "风险", "failure", "blocker"],
            "evidence_strength": ["evidence", "文献", "paper", "support"],
            "information_gain": ["learn", "信息", "gain", "uncertain"],
        }
        for token in signals.get(dimension_id, []):
            if token in text:
                base += 0.45
        if dimension_id == "risk" and any(token in text for token in ["risk", "风险", "failure"]):
            base -= 0.4
        base += ((offset % 3) - 1) * 0.15
        return round(max(0.0, min(10.0, base)), 2)

    def _judgment_from_llm(
        self,
        pair_id: str,
        idea_a_id: str,
        idea_b_id: str,
        stage: str,
        data: Any,
        meta: dict[str, Any],
        dimensions: list[ScoreDimension],
    ) -> PairwiseJudgment:
        if not isinstance(data, dict):
            data = {}
        winner = data.get("winner")
        if winner not in {"A", "B", "tie"}:
            winner = "tie"
        scores = data.get("dimension_scores")
        if not isinstance(scores, dict):
            scores = {dimension.id: {"A": 5, "B": 5, "rationale": "Judge did not return structured scores."} for dimension in dimensions}
        evidence_refs = data.get("evidence_refs") if isinstance(data.get("evidence_refs"), list) else []
        confidence = data.get("confidence", 0.5)
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.5
        return PairwiseJudgment(
            pair_id=pair_id,
            idea_a_id=idea_a_id,
            idea_b_id=idea_b_id,
            judge_model=f"{stage}:{meta.get('provider', 'mock')}:{meta.get('model', 'mock')}",
            winner=winner,
            dimension_scores=scores,
            confidence=max(0.0, min(1.0, confidence)),
            reasoning=str(data.get("reasoning") or data.get("analysis") or ""),
            evidence_refs=[str(item) for item in evidence_refs],
        )

    def _btl_scores(self, ideas: list[dict[str, Any]], judgments: list[PairwiseJudgment]) -> dict[str, float]:
        ids = [idea["id"] for idea in ideas]
        if not ids:
            return {}
        strengths = {idea_id: 1.0 for idea_id in ids}
        wins = {idea_id: 0.0 for idea_id in ids}
        comparisons = {idea_id: 0.0 for idea_id in ids}
        for judgment in judgments:
            if judgment.winner == "A":
                wins[judgment.idea_a_id] += judgment.confidence
            elif judgment.winner == "B":
                wins[judgment.idea_b_id] += judgment.confidence
            else:
                wins[judgment.idea_a_id] += 0.5 * judgment.confidence
                wins[judgment.idea_b_id] += 0.5 * judgment.confidence
            comparisons[judgment.idea_a_id] += judgment.confidence
            comparisons[judgment.idea_b_id] += judgment.confidence
        for _ in range(50):
            next_strengths = {}
            for idea_id in ids:
                denom = 0.0
                for judgment in judgments:
                    if idea_id not in {judgment.idea_a_id, judgment.idea_b_id}:
                        continue
                    other_id = judgment.idea_b_id if judgment.idea_a_id == idea_id else judgment.idea_a_id
                    denom += judgment.confidence / max(strengths[idea_id] + strengths.get(other_id, 1.0), 1e-6)
                next_strengths[idea_id] = max((wins[idea_id] + 0.5) / max(denom + 0.5, 1e-6), 1e-6)
            total = sum(next_strengths.values()) or 1.0
            strengths = {idea_id: value / total for idea_id, value in next_strengths.items()}
        return {idea_id: round(strengths[idea_id], 4) for idea_id in ids}

    def _elo_scores(self, ideas: list[dict[str, Any]], judgments: list[PairwiseJudgment]) -> dict[str, float]:
        ratings = {idea["id"]: 1000.0 for idea in ideas}
        k_factor = 24
        for judgment in judgments:
            a = judgment.idea_a_id
            b = judgment.idea_b_id
            expected_a = 1 / (1 + math.pow(10, (ratings[b] - ratings[a]) / 400))
            if judgment.winner == "A":
                actual_a = 1.0
            elif judgment.winner == "B":
                actual_a = 0.0
            else:
                actual_a = 0.5
            delta = k_factor * judgment.confidence * (actual_a - expected_a)
            ratings[a] += delta
            ratings[b] -= delta
        return {idea_id: round(score, 1) for idea_id, score in ratings.items()}

    def _dimension_aggregates(
        self,
        ideas: list[dict[str, Any]],
        judgments: list[PairwiseJudgment],
        dimensions: list[ScoreDimension],
    ) -> dict[str, dict[str, float]]:
        totals = {idea["id"]: {dimension.id: [] for dimension in dimensions} for idea in ideas}
        for judgment in judgments:
            for dimension in dimensions:
                score = judgment.dimension_scores.get(dimension.id, {})
                if isinstance(score, dict):
                    for side, idea_id in [("A", judgment.idea_a_id), ("B", judgment.idea_b_id)]:
                        try:
                            totals[idea_id][dimension.id].append(float(score.get(side)))
                        except (TypeError, ValueError):
                            continue
        aggregates: dict[str, dict[str, float]] = {}
        for idea_id, per_dimension in totals.items():
            aggregates[idea_id] = {}
            for dimension_id, values in per_dimension.items():
                aggregates[idea_id][dimension_id] = round(sum(values) / len(values), 2) if values else 0.0
        return aggregates

    def _model_disagreement(self, judgments: list[PairwiseJudgment]) -> dict[str, Any]:
        by_pair: dict[str, list[str]] = {}
        for judgment in judgments:
            by_pair.setdefault(judgment.pair_id, []).append(judgment.winner)
        pair_disagreement = {}
        for pair_id, winners in by_pair.items():
            pair_disagreement[pair_id] = len(set(winners)) > 1
        total = len(pair_disagreement)
        disagree = sum(1 for value in pair_disagreement.values() if value)
        return {
            "pair_disagreement": pair_disagreement,
            "disagreement_rate": round(disagree / total, 3) if total else 0.0,
            "disagreement_pairs": [pair_id for pair_id, value in pair_disagreement.items() if value],
        }

    def _pareto_categories(
        self,
        ideas: list[dict[str, Any]],
        btl_scores: dict[str, float],
        dimension_aggregates: dict[str, dict[str, float]],
    ) -> dict[str, str]:
        categories = {}
        if not ideas:
            return categories
        sorted_ids = sorted([idea["id"] for idea in ideas], key=lambda idea_id: btl_scores.get(idea_id, 0), reverse=True)
        top_id = sorted_ids[0]
        for idea in ideas:
            idea_id = idea["id"]
            scores = dimension_aggregates.get(idea_id, {})
            impact = scores.get("impact", 0)
            risk = scores.get("risk", 0)
            novelty = scores.get("novelty", 0)
            testability = scores.get("testability", 0)
            evidence = scores.get("evidence_strength", 0)
            if idea_id == top_id and impact >= 6:
                category = "适合作为论文主线"
            elif impact >= 7 and risk < 6:
                category = "高影响高风险"
            elif testability >= 7 and risk >= 6:
                category = "低成本 quick win"
            elif novelty >= 7 and evidence < 6:
                category = "高新颖但需文献确认"
            elif btl_scores.get(idea_id, 0) < 0.12:
                category = "建议暂缓或放弃"
            else:
                category = "适合作为 ablation / side project"
            categories[idea_id] = category
        return categories

    def _experiment_plans(self, workspace: Path, ideas: list[dict[str, Any]], prompt: str) -> list[ExperimentPlanStub]:
        plans = []
        for idea in ideas:
            idea_id = idea["id"]
            validation = idea.get("cheapest_validation") or idea.get("validation") or idea.get("required_evidence") or ""
            fallback = {
                "idea_id": idea_id,
                "status": "planned",
                "reason_not_executed": "Phase 1 只将实验纳入评估闭环；sandbox 与真实实验执行尚未实现。",
                "minimum_validation": str(validation or "先进行文献复核，再设计最小对照实验。"),
                "metrics": ["novelty_check", "feasibility_check", "target_metric_to_define"],
                "controls": ["baseline_or_current_best_method", "negative_control_if_applicable"],
                "ablation_plan": ["remove_core_mechanism_or_key_component"],
                "expected_result": str(idea.get("expected_results") or "如果 idea 成立，应观察到目标指标优于合理 baseline。"),
                "failure_signal": "无法优于 baseline，或关键假设被文献/初步验证否定。",
            }
            data, _ = self.llm.complete_json(
                "evaluation_meta",
                prompt,
                json.dumps({"idea": idea, "experiment_policy": "plan_only"}, ensure_ascii=False),
                fallback,
            )
            if not isinstance(data, dict):
                data = fallback
            data["idea_id"] = str(data.get("idea_id") or idea_id)
            if data.get("status") not in {"planned", "skipped"}:
                data["status"] = "planned"
            for key in ["metrics", "controls", "ablation_plan"]:
                if isinstance(data.get(key), str):
                    data[key] = [data[key]]
                elif not isinstance(data.get(key), list):
                    data[key] = fallback[key]
            plans.append(ExperimentPlanStub.model_validate(data))
        return plans

    def _meta_review(
        self,
        problem: Any,
        ideas: list[dict[str, Any]],
        judgments: list[PairwiseJudgment],
        btl_scores: dict[str, float],
        elo_scores: dict[str, float],
        dimension_aggregates: dict[str, dict[str, float]],
        model_disagreement: dict[str, Any],
        pareto_categories: dict[str, str],
        evidence: Any,
        prompt: str,
    ) -> dict[str, Any]:
        ranked_ids = sorted(btl_scores, key=btl_scores.get, reverse=True)
        fallback = {
            "summary": "Evaluation 已完成多模型成对比较；需要结合分歧对、证据缺口和人工复核决定最终推进路线。",
            "stable_recommendations": [
                {
                    "idea_id": ranked_ids[0],
                    "reason": "BTL 排名最高；仍需真实实验验证。",
                }
            ] if ranked_ids else [],
            "model_disagreements": model_disagreement.get("disagreement_pairs", []),
            "evidence_gaps": ["需要把关键 claim 绑定到更强文献证据或最小验证结果。"],
            "human_review_needed": [
                "复核模型分歧较高的成对比较。",
                "确认最高排名 idea 的最小验证是否符合实际资源约束。",
            ],
            "prompt_feedback": [
                "下一轮 ideation 应强制说明 novelty position 和 cheapest_validation。",
                "下一轮 critic 应更明确列出替代解释和失败判据。",
            ],
            "next_evaluation_actions": [
                "补充证据后重新运行 Evaluation。",
                "对 top idea 与高分歧 pair 添加人工 judgment。",
            ],
        }
        data, meta = self.llm.complete_json(
            "evaluation_meta",
            prompt,
            json.dumps(
                {
                    "problem": problem,
                    "ideas": ideas,
                    "judgments": [judgment.model_dump() for judgment in judgments],
                    "btl_scores": btl_scores,
                    "elo_scores": elo_scores,
                    "dimension_aggregates": dimension_aggregates,
                    "model_disagreement": model_disagreement,
                    "pareto_categories": pareto_categories,
                    "evidence": evidence,
                    "instruction": "生成系统级 meta-review，不要重新评估单个 idea。真实实验尚未执行。",
                },
                ensure_ascii=False,
            ),
            fallback,
        )
        if not isinstance(data, dict):
            data = fallback
        data.setdefault("summary", fallback["summary"])
        data.setdefault("stable_recommendations", fallback["stable_recommendations"])
        data.setdefault("model_disagreements", fallback["model_disagreements"])
        data.setdefault("evidence_gaps", fallback["evidence_gaps"])
        data.setdefault("human_review_needed", fallback["human_review_needed"])
        data.setdefault("prompt_feedback", fallback["prompt_feedback"])
        data.setdefault("next_evaluation_actions", fallback["next_evaluation_actions"])
        data["model"] = f"{meta.get('provider', 'mock')}:{meta.get('model', 'mock')}"
        data["used_fallback"] = bool(meta.get("used_fallback"))
        return data
