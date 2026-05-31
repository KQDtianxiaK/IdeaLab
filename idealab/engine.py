from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from .config import get_prompts_config, write_json
from .evaluation import EvaluationService, append_human_judgment, load_evaluation
from .llm import LLMClient
from .models import CreateRunRequest, Graph, HumanEvaluationJudgmentRequest, HumanInputRequest, Node, new_id
from .storage import (
    add_edge,
    add_node,
    append_event,
    create_workspace,
    load_graph,
    run_dir,
    save_graph,
    set_run_status,
    update_node,
    write_text,
)
from .tools import SemanticScholarTool


class IdeaLabEngine:
    def __init__(self) -> None:
        self._threads: dict[str, threading.Thread] = {}
        self._stop_flags: set[str] = set()

    def create_run(self, request: CreateRunRequest) -> Graph:
        run_id, workspace, graph = create_workspace(request.mode, request.input)
        thread = threading.Thread(
            target=self._run_background,
            args=(run_id, workspace, request.input, request.mode),
            daemon=True,
        )
        self._threads[run_id] = thread
        thread.start()
        return graph

    def stop_run(self, run_id: str) -> Graph:
        self._stop_flags.add(run_id)
        workspace = run_dir(run_id)
        return set_run_status(workspace, "stopped")

    def ensure_display_branches(self, workspace: Path) -> Graph:
        graph = load_graph(workspace)
        if graph.status == "running" or any(node.type == "idea" for node in graph.nodes):
            return graph

        ideation_node = next((node for node in graph.nodes if node.type == "ideation" and node.output), None)
        comparison_node = next((node for node in graph.nodes if node.type == "comparison"), None)
        if not ideation_node:
            return graph

        idea_items = self._idea_items(ideation_node.output)
        if len(idea_items) <= 1:
            return graph

        for index, idea in enumerate(idea_items[:5], start=1):
            idea_title = str(idea.get("title") or idea.get("id") or f"候选想法 {index}")[:80]
            idea_node = Node(
                id=new_id("node"),
                parent_id=ideation_node.id,
                type="idea",
                title=f"候选想法 {index}: {idea_title}",
                status="completed",
                summary=self._summary_from(idea, "hypothesis"),
                input={"source": "ideation", "index": index, "display_reconstructed": True},
                output=idea,
                prompt_version=ideation_node.prompt_version,
                confidence=ideation_node.confidence,
            )
            add_node(workspace, idea_node)
            if comparison_node:
                add_edge(workspace, idea_node.id, comparison_node.id)
        return load_graph(workspace)

    def add_human_input(self, run_id: str, request: HumanInputRequest) -> Graph:
        workspace = run_dir(run_id)
        graph = load_graph(workspace)
        parent_id = graph.nodes[-1].id if graph.nodes else None
        node = Node(
            id=new_id("node"),
            parent_id=parent_id,
            type="human_input",
            title="人类补充想法",
            status="completed",
            summary=request.content[:160],
            input={"content": request.content},
            output={"injection_policy": "将在当前 loop 结束后作为强上下文注入下一轮。"},
            confidence=1.0,
        )
        add_node(workspace, node)
        return load_graph(workspace)

    def load_evaluation(self, run_id: str) -> dict[str, Any] | None:
        return load_evaluation(run_dir(run_id))

    def recompute_evaluation(self, run_id: str) -> dict[str, Any]:
        workspace = run_dir(run_id)
        graph = load_graph(workspace)
        by_type = {node.type: node.output for node in graph.nodes if node.output is not None}
        branches = self._branch_results_from_graph(graph)
        return EvaluationService().run(
            workspace=workspace,
            problem=by_type.get("problem"),
            ideas=by_type.get("ideation"),
            branches=branches,
            evidence=by_type.get("literature"),
        )

    def add_human_evaluation_judgment(self, run_id: str, request: HumanEvaluationJudgmentRequest) -> dict[str, Any]:
        return append_human_judgment(run_dir(run_id), request)

    def _run_background(self, run_id: str, workspace: Path, raw_input: str, mode: str) -> None:
        try:
            prompts = get_prompts_config()
            graph = load_graph(workspace)
            init_id = graph.nodes[0].id
            update_node(
                workspace,
                init_id,
                status="completed",
                summary="工作区、配置和推演图已初始化。",
                output={"workspace": str(workspace), "mode": mode},
            )
            if mode == "fixed":
                self._run_fixed(run_id, workspace, raw_input, prompts)
            else:
                self._run_free(run_id, workspace, raw_input, prompts)
            if run_id not in self._stop_flags:
                set_run_status(workspace, "completed")
        except Exception as exc:
            append_event(workspace, {"type": "engine_error", "error": str(exc)})
            set_run_status(workspace, "failed")

    def _add_running_node(
        self,
        workspace: Path,
        parent_id: str | None,
        node_type: str,
        title: str,
        payload: Any,
        prompt_version: int,
    ) -> Node:
        node = Node(
            id=new_id("node"),
            parent_id=parent_id,
            type=node_type,
            title=title,
            status="running",
            summary="运行中...",
            input=payload,
            prompt_version=prompt_version,
        )
        add_node(workspace, node)
        return node

    def _complete_llm_node(
        self,
        workspace: Path,
        node: Node,
        stage: str,
        prompt: str,
        user_payload: dict[str, Any],
        fallback: Any,
        summary_key: str = "summary",
    ) -> Any:
        llm = LLMClient()
        data, meta = llm.complete_json(
            stage=stage,
            system=prompt,
            user=json.dumps(user_payload, ensure_ascii=False, indent=2),
            fallback=fallback,
        )
        summary = self._summary_from(data, summary_key)
        update_node(
            workspace,
            node.id,
            status="completed",
            summary=summary,
            output=data,
            model=f"{meta['provider']}:{meta['model']}",
            tool_calls=[{"tool": "llm", **meta}],
            confidence=0.72 if meta.get("used_fallback") else 0.86,
        )
        return data

    def _run_fixed(self, run_id: str, workspace: Path, raw_input: str, prompts: dict[str, Any]) -> None:
        fixed_prompts = prompts.get("fixed", {})
        version = int(prompts.get("version", 1))
        parent_id = load_graph(workspace).nodes[-1].id

        problem_node = self._add_running_node(workspace, parent_id, "problem", "问题规范化", raw_input, version)
        problem = self._complete_llm_node(
            workspace,
            problem_node,
            "default",
            fixed_prompts.get("problem", ""),
            {"raw_input": raw_input},
            self._fallback_problem(raw_input),
            "title",
        )
        parent_id = problem_node.id
        write_json(workspace / "problem.json", problem)

        parent_id = self._maybe_wait_for_clarification(run_id, workspace, parent_id, problem, version)

        decompose_node = self._add_running_node(workspace, parent_id, "decomposition", "问题拆解", problem, version)
        decomposition = self._complete_llm_node(
            workspace,
            decompose_node,
            "default",
            fixed_prompts.get("decompose", ""),
            {"problem": problem, "human_inputs": self._human_inputs(workspace)},
            self._fallback_decomposition(raw_input),
        )
        parent_id = decompose_node.id

        literature_node = self._add_running_node(workspace, parent_id, "literature", "文献与证据检索", decomposition, version)
        literature = self._literature_step(workspace, literature_node, raw_input, decomposition)
        parent_id = literature_node.id

        ideation_node = self._add_running_node(workspace, parent_id, "ideation", "候选想法生成", literature, version)
        ideas = self._complete_llm_node(
            workspace,
            ideation_node,
            "ideation",
            fixed_prompts.get("ideation", ""),
            {"problem": problem, "decomposition": decomposition, "evidence": literature, "human_inputs": self._human_inputs(workspace)},
            self._fallback_ideas(raw_input),
            "summary",
        )
        parent_id = ideation_node.id
        write_json(workspace / "ideas.json", ideas)

        branch_results = self._run_idea_branches(
            workspace,
            parent_id,
            problem,
            decomposition,
            literature,
            ideas,
            fixed_prompts,
            version,
        )
        parent_id = branch_results[0]["leaf_node_id"] if branch_results else ideation_node.id

        evaluation_node = self._add_running_node(
            workspace,
            parent_id,
            "evaluation",
            "Idea 多模型成对评估",
            {"ideas": ideas, "branches": branch_results, "experiment_policy": "plan_only"},
            version,
        )
        for branch in branch_results[1:]:
            add_edge(workspace, branch["leaf_node_id"], evaluation_node.id)
        evaluation = EvaluationService().run(
            workspace=workspace,
            problem=problem,
            ideas=ideas,
            branches=branch_results,
            evidence=literature,
        )
        update_node(
            workspace,
            evaluation_node.id,
            status="completed",
            summary=self._evaluation_summary(evaluation),
            output=evaluation,
            model=", ".join(evaluation.get("spec", {}).get("judge_models", [])),
            tool_calls=[{"tool": "idealab_evaluation", "policy": "pairwise_btl_elo", "experiment_policy": "plan_only"}],
            scores=evaluation.get("btl_scores", {}),
            confidence=0.78,
        )
        parent_id = evaluation_node.id

        compare_node = self._add_running_node(workspace, parent_id, "comparison", "路径比较与排序", {"branches": branch_results, "evaluation": evaluation}, version)
        comparison = self._complete_llm_node(
            workspace,
            compare_node,
            "critic",
            fixed_prompts.get("compare", ""),
            {
                "ideas": ideas,
                "branches": branch_results,
                "evaluation": evaluation,
                "evidence": literature,
                "human_inputs": self._human_inputs(workspace),
                "instruction": "优先消费 evaluation 的 BTL/Elo 排名、维度评分、模型分歧和实验占位信息，再给出研究路线决策。",
            },
            self._fallback_comparison(ideas),
        )
        parent_id = compare_node.id

        review_node = self._add_running_node(workspace, parent_id, "cross_review", "交叉审查", comparison, version)
        review = self._complete_llm_node(
            workspace,
            review_node,
            "critic",
            fixed_prompts.get("review", ""),
            {"comparison": comparison, "full_graph": load_graph(workspace).model_dump()},
            {"summary": "推演链已完成基础一致性检查。", "issues": [], "recommendations": []},
        )
        parent_id = review_node.id

        report_node = self._add_running_node(workspace, parent_id, "report", "生成研究推演报告", review, version)
        report = self._generate_report(workspace, fixed_prompts.get("report", ""))
        update_node(
            workspace,
            report_node.id,
            status="completed",
            summary="研究推演报告已生成。",
            output={"path": "reports/report.md", "preview": report[:1200]},
            model=LLMClient().model_label("report"),
            confidence=0.9,
        )

    def _run_idea_branches(
        self,
        workspace: Path,
        parent_id: str,
        problem: Any,
        decomposition: Any,
        literature: Any,
        ideas: Any,
        fixed_prompts: dict[str, str],
        prompt_version: int,
    ) -> list[dict[str, Any]]:
        idea_items = self._idea_items(ideas)
        if not idea_items:
            return []

        branches = []
        for index, idea in enumerate(idea_items[:5], start=1):
            idea_title = str(idea.get("title") or idea.get("id") or f"候选想法 {index}")[:80]
            idea_node = Node(
                id=new_id("node"),
                parent_id=parent_id,
                type="idea",
                title=f"候选想法 {index}: {idea_title}",
                status="completed",
                summary=self._summary_from(idea, "hypothesis"),
                input={"source": "ideation", "index": index},
                output=idea,
                prompt_version=prompt_version,
                confidence=0.82,
            )
            add_node(workspace, idea_node)

            reason_node = self._add_running_node(
                workspace,
                idea_node.id,
                "reasoning",
                f"机制推演: {idea_title}",
                idea,
                prompt_version,
            )
            reasoning = self._complete_llm_node(
                workspace,
                reason_node,
                "default",
                fixed_prompts.get("reason", ""),
                {
                    "problem": problem,
                    "decomposition": decomposition,
                    "idea": idea,
                    "evidence": literature,
                    "human_inputs": self._human_inputs(workspace),
                    "instruction": "只推演当前这一条 idea，输出中保留 idea_id。",
                },
                self._fallback_reasoning({"ideas": [idea]}),
            )

            critic_node = self._add_running_node(
                workspace,
                reason_node.id,
                "critic",
                f"反方批判: {idea_title}",
                reasoning,
                prompt_version,
            )
            critic = self._complete_llm_node(
                workspace,
                critic_node,
                "critic",
                fixed_prompts.get("critic", ""),
                {
                    "problem": problem,
                    "idea": idea,
                    "reasoning": reasoning,
                    "evidence": literature,
                    "instruction": "只批判当前这一条 idea，并给出是否应继续推进。",
                },
                self._fallback_critic(),
            )

            branches.append(
                {
                    "idea_node_id": idea_node.id,
                    "reasoning_node_id": reason_node.id,
                    "critic_node_id": critic_node.id,
                    "leaf_node_id": critic_node.id,
                    "idea": idea,
                    "reasoning": reasoning,
                    "critic": critic,
                }
            )
        return branches

    def _run_free(self, run_id: str, workspace: Path, raw_input: str, prompts: dict[str, Any]) -> None:
        free_prompts = prompts.get("free", {})
        version = int(prompts.get("version", 1))
        parent_id = load_graph(workspace).nodes[-1].id
        llm = LLMClient()
        max_steps = 10
        for step in range(max_steps):
            if run_id in self._stop_flags:
                return
            graph = load_graph(workspace).model_dump()
            action_fallback = self._fallback_free_action(step)
            action, meta = llm.complete_json(
                "default",
                free_prompts.get("policy", ""),
                json.dumps({"step": step + 1, "raw_input": raw_input, "graph": graph, "human_inputs": self._human_inputs(workspace)}, ensure_ascii=False),
                action_fallback,
            )
            action_name = action.get("action", action_fallback["action"])
            node = self._add_running_node(
                workspace,
                parent_id,
                f"free_{action_name}",
                f"自由探索：{action_name}",
                {"action_decision": action, "step": step + 1},
                version,
            )
            if action_name == "literature":
                output = self._literature_step(workspace, node, raw_input, action)
            elif action_name == "report" or step == max_steps - 1:
                output = {"summary": "自由探索已收敛，生成最终报告。", "report": self._generate_report(workspace, free_prompts.get("step", ""))}
            else:
                output, meta2 = llm.complete_json(
                    "ideation" if action_name == "ideate" else "default",
                    free_prompts.get("step", ""),
                    json.dumps({"action": action, "graph": graph, "human_inputs": self._human_inputs(workspace)}, ensure_ascii=False),
                    self._fallback_free_output(action_name, raw_input),
                )
                meta = {**meta, "execution": meta2}
            update_node(
                workspace,
                node.id,
                status="completed",
                summary=self._summary_from(output),
                output=output,
                model=f"{meta.get('provider', 'mock')}:{meta.get('model', 'mock')}",
                tool_calls=[{"tool": "free_agent", **meta}],
                confidence=0.78,
            )
            parent_id = node.id
            if action_name == "report":
                return
            time.sleep(0.2)

    def _literature_step(self, workspace: Path, node: Node, raw_input: str, context: Any) -> dict[str, Any]:
        query = self._query_from(raw_input, context)
        tool = SemanticScholarTool()
        result = tool.search(query)
        evidence_refs: list[str] = []
        evidence_items: list[dict[str, Any]] = []
        for paper in result.get("papers", [])[:6]:
            eid = new_id("ev")
            item = {
                "id": eid,
                "source_type": "paper",
                "title": paper.get("title"),
                "url": paper.get("url"),
                "year": paper.get("year"),
                "venue": paper.get("venue"),
                "citation_count": paper.get("citationCount"),
                "abstract": paper.get("abstract"),
                "relevance": "Semantic Scholar query result",
                "reliability": "medium",
            }
            write_json(workspace / "evidence" / f"{eid}.json", item)
            evidence_refs.append(eid)
            evidence_items.append(item)
        output = {
            "summary": f"完成文献检索：{query}",
            "query": query,
            "ok": result.get("ok"),
            "error": result.get("error"),
            "evidence_count": len(evidence_items),
            "evidence": evidence_items,
        }
        update_node(
            workspace,
            node.id,
            status="completed",
            summary=output["summary"],
            output=output,
            tool_calls=[{"tool": "semantic_scholar", "query": query, "ok": result.get("ok")}],
            evidence_refs=evidence_refs,
            confidence=0.8 if result.get("ok") else 0.45,
        )
        return output

    def _maybe_wait_for_clarification(
        self,
        run_id: str,
        workspace: Path,
        parent_id: str,
        problem: Any,
        prompt_version: int,
    ) -> str:
        if not isinstance(problem, dict):
            return parent_id
        questions = problem.get("clarification_questions") or []
        if problem.get("input_type") != "method_idea" or not questions:
            return parent_id

        wait_node = Node(
            id=new_id("node"),
            parent_id=parent_id,
            type="clarification",
            title="用户意图确认",
            status="waiting_user",
            summary="IdeaLab 需要先确认你对这个方法 idea 的关键意图。请在底部输入补充或确认。",
            input={"problem": problem},
            output={
                "questions": questions,
                "instruction": "请回答这些问题，或直接说明“按当前理解继续”。IdeaLab 收到输入后会进入文献检索与后续固定流程。",
            },
            prompt_version=prompt_version,
        )
        add_node(workspace, wait_node)
        initial_human_count = len(self._human_inputs(workspace))
        set_run_status(workspace, "waiting_user")

        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            if run_id in self._stop_flags:
                return wait_node.id
            if len(self._human_inputs(workspace)) > initial_human_count:
                latest = load_graph(workspace).nodes[-1]
                update_node(
                    workspace,
                    wait_node.id,
                    status="completed",
                    summary="已收到用户确认，继续进入文献检索与推演流程。",
                    output={**wait_node.output, "received_confirmation": True},
                )
                set_run_status(workspace, "running")
                return latest.id
            time.sleep(1)

        update_node(
            workspace,
            wait_node.id,
            status="completed",
            summary="等待确认超时，按当前理解继续推演；报告会保留未确认假设。",
            output={**wait_node.output, "received_confirmation": False, "timeout_seconds": 1800},
        )
        set_run_status(workspace, "running")
        return wait_node.id

    def _generate_report(self, workspace: Path, prompt: str) -> str:
        graph = load_graph(workspace)
        human_inputs = self._human_inputs(workspace)
        context = self._report_context(graph, human_inputs)
        fallback = {"report_markdown": self._fallback_report(graph)}
        data, _ = LLMClient().complete_json(
            "report",
            prompt or "根据 IdeaLab 推演图生成 Markdown 报告。输出 {\"report_markdown\": \"...\"}",
            json.dumps(context, ensure_ascii=False),
            fallback,
        )
        report = data.get("report_markdown") if isinstance(data, dict) else None
        if not report:
            report = self._fallback_report(graph)
        write_text(workspace / "reports" / "report.md", report)
        return report

    def _report_context(self, graph: Graph, human_inputs: list[dict[str, Any]]) -> dict[str, Any]:
        nodes = [node.model_dump() for node in graph.nodes]
        by_type = {node.type: node.output for node in graph.nodes if node.output is not None}
        by_type_list: dict[str, list[Any]] = {}
        for node in graph.nodes:
            if node.output is not None:
                by_type_list.setdefault(node.type, []).append(node.output)
        raw_input = ""
        if graph.nodes and isinstance(graph.nodes[0].input, dict):
            raw_input = str(graph.nodes[0].input.get("raw_user_input", ""))
        return {
            "run": {
                "run_id": graph.run_id,
                "mode": graph.mode,
                "status": graph.status,
                "raw_user_input": raw_input,
            },
            "problem_spec": by_type.get("problem"),
            "decomposition": by_type.get("decomposition"),
            "literature": by_type.get("literature"),
            "ideas": by_type.get("ideation"),
            "idea_branch_nodes": by_type_list.get("idea", []),
            "reasoning": by_type_list.get("reasoning", []),
            "critic": by_type_list.get("critic", []),
            "comparison": by_type.get("comparison"),
            "evaluation": by_type.get("evaluation"),
            "experiment_plans": (by_type.get("evaluation") or {}).get("experiment_plans", []) if isinstance(by_type.get("evaluation"), dict) else [],
            "cross_review": by_type.get("cross_review"),
            "human_inputs": human_inputs,
            "trace_nodes": nodes,
            "report_instruction": "生成研究结论报告，不要生成节点完成日志。必须明确区分真实实验结果、文献证据、模型推理和待验证假设。",
        }

    def _human_inputs(self, workspace: Path) -> list[dict[str, Any]]:
        graph = load_graph(workspace)
        return [n.model_dump() for n in graph.nodes if n.type == "human_input"]

    def _summary_from(self, data: Any, key: str = "summary") -> str:
        if isinstance(data, dict):
            if data.get(key):
                return str(data[key])[:240]
            if data.get("short_hypothesis"):
                return str(data["short_hypothesis"])[:240]
            if data.get("mechanism"):
                return str(data["mechanism"])[:240]
            if data.get("title"):
                return str(data["title"])[:240]
            if data.get("recommendation"):
                return str(data["recommendation"])[:240]
        if isinstance(data, list):
            return f"生成 {len(data)} 条结构化结果。"
        return str(data)[:240]

    def _idea_items(self, ideas: Any) -> list[dict[str, Any]]:
        if isinstance(ideas, dict):
            items = ideas.get("ideas", [])
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        if isinstance(ideas, list):
            return [item for item in ideas if isinstance(item, dict)]
        return []

    def _branch_results_from_graph(self, graph: Graph) -> list[dict[str, Any]]:
        idea_nodes = [node for node in graph.nodes if node.type == "idea" and isinstance(node.output, dict)]
        branches = []
        for idea_node in idea_nodes:
            reason_node = next((node for node in graph.nodes if node.parent_id == idea_node.id and node.type == "reasoning"), None)
            critic_node = next((node for node in graph.nodes if reason_node and node.parent_id == reason_node.id and node.type == "critic"), None)
            branches.append(
                {
                    "idea_node_id": idea_node.id,
                    "reasoning_node_id": reason_node.id if reason_node else None,
                    "critic_node_id": critic_node.id if critic_node else None,
                    "leaf_node_id": critic_node.id if critic_node else reason_node.id if reason_node else idea_node.id,
                    "idea": idea_node.output,
                    "reasoning": reason_node.output if reason_node else None,
                    "critic": critic_node.output if critic_node else None,
                }
            )
        return branches

    def _evaluation_summary(self, evaluation: dict[str, Any]) -> str:
        scores = evaluation.get("btl_scores", {})
        categories = evaluation.get("pareto_categories", {})
        if not scores:
            return "完成 Evaluation：未发现可排序候选 idea。"
        top_id = max(scores, key=scores.get)
        category = categories.get(top_id, "未分类")
        disagreement = evaluation.get("model_disagreement", {}).get("disagreement_rate", 0)
        return f"完成多模型成对评估：推荐 {top_id}（{category}），模型分歧率 {disagreement}。"

    def _query_from(self, raw_input: str, context: Any) -> str:
        candidates: list[str] = [raw_input]
        if isinstance(context, dict):
            for key in [
                "title",
                "domain",
                "core_claim_or_question",
                "objective",
                "summary",
                "target_problem",
                "hypothesis",
            ]:
                value = context.get(key)
                if isinstance(value, str) and value.strip():
                    candidates.append(value.strip()[:90])
            sub_questions = context.get("sub_questions")
            if isinstance(sub_questions, list):
                candidates.extend(str(item).strip()[:70] for item in sub_questions[:2] if str(item).strip())
        elif isinstance(context, str):
            candidates.append(context[:90])
        text = " ".join(candidates)
        text = " ".join(text.replace("\n", " ").split())
        text = text.replace("Harness", "agent harness")
        if len(text) > 180:
            text = text[:180]
        if isinstance(context, dict):
            domain = context.get("domain")
            if isinstance(domain, str) and domain.strip():
                text = f"{domain.strip()} {text}"
        words = [w.strip("，。,.!?:；;()[]{}'\"") for w in text.split()]
        query = " ".join(words[:24]).strip()
        return query[:220] or raw_input[:120]

    def _fallback_problem(self, raw_input: str) -> dict[str, Any]:
        title = raw_input.strip().split("\n")[0][:80] or "未命名研究问题"
        return {"title": title, "domain": "general", "background": raw_input, "target_outcome": "形成可验证研究路线", "constraints": {}, "success_criteria": ["生成候选想法", "识别风险", "提出验证计划"]}

    def _fallback_decomposition(self, raw_input: str) -> dict[str, Any]:
        return {"summary": "已完成启发式问题拆解。", "sub_questions": ["核心机制是什么？", "已有工作做到哪里？", "最小验证路径是什么？"], "assumptions": ["输入问题存在可研究空间"], "evaluation_dimensions": ["novelty", "feasibility", "impact", "testability"]}

    def _fallback_ideas(self, raw_input: str) -> dict[str, Any]:
        ideas = []
        for idx in range(1, 6):
            ideas.append({
                "id": f"I{idx}",
                "title": f"候选研究想法 {idx}",
                "short_hypothesis": f"围绕用户问题的第 {idx} 条可检验假设。",
                "mechanism": "通过拆解关键变量并设计低成本验证来发现可推进方向。",
                "risks": ["证据不足", "与已有工作重叠"],
                "validation": "先做文献确认，再做小规模验证。",
            })
        return {"summary": "生成 5 个候选研究想法。", "ideas": ideas}

    def _fallback_reasoning(self, ideas: Any) -> dict[str, Any]:
        return {"summary": "完成候选想法的启发式机制推演。", "paths": [{"idea": item.get("title", "idea"), "chain": ["假设", "机制", "可观测结果", "验证"]} for item in (ideas.get("ideas", []) if isinstance(ideas, dict) else [])]}

    def _fallback_critic(self) -> dict[str, Any]:
        return {"summary": "完成风险与反方批判。", "risks": ["新颖性可能不足", "验证成本可能被低估", "因果机制可能存在替代解释"], "recommendations": ["优先补充文献证据", "先做低成本验证"]}

    def _fallback_comparison(self, ideas: Any) -> dict[str, Any]:
        ranked = []
        for idx, item in enumerate((ideas.get("ideas", []) if isinstance(ideas, dict) else []), start=1):
            ranked.append({"rank": idx, "idea": item.get("title", f"I{idx}"), "novelty": 6, "feasibility": 7, "impact": 6, "testability": 7})
        return {"summary": "完成候选想法排序。", "ranked_ideas": ranked, "recommendation": ranked[0]["idea"] if ranked else "继续补充信息"}

    def _fallback_free_action(self, step: int) -> dict[str, Any]:
        actions = ["decompose", "literature", "ideate", "reason", "critic", "compare", "report"]
        return {"action": actions[min(step, len(actions) - 1)], "reason": "按自由探索默认策略推进。"}

    def _fallback_free_output(self, action: str, raw_input: str) -> dict[str, Any]:
        return {"summary": f"自由探索执行 {action}。", "findings": [f"围绕输入问题继续推进：{raw_input[:120]}"], "next_step": "继续扩展或收敛报告"}

    def _fallback_report(self, graph: Graph) -> str:
        by_type = {node.type: node.output for node in graph.nodes if node.output is not None}
        raw_input = ""
        if graph.nodes and isinstance(graph.nodes[0].input, dict):
            raw_input = str(graph.nodes[0].input.get("raw_user_input", ""))
        problem = by_type.get("problem") if isinstance(by_type.get("problem"), dict) else {}
        decomposition = by_type.get("decomposition") if isinstance(by_type.get("decomposition"), dict) else {}
        literature = by_type.get("literature") if isinstance(by_type.get("literature"), dict) else {}
        ideas = by_type.get("ideation") if isinstance(by_type.get("ideation"), dict) else {}
        reasoning = by_type.get("reasoning") if isinstance(by_type.get("reasoning"), dict) else {}
        critic = by_type.get("critic") if isinstance(by_type.get("critic"), dict) else {}
        comparison = by_type.get("comparison") if isinstance(by_type.get("comparison"), dict) else {}
        review = by_type.get("cross_review") if isinstance(by_type.get("cross_review"), dict) else {}

        title = problem.get("title") or raw_input.strip().split("\n")[0][:80] or "IdeaLab 研究推演报告"
        input_type = problem.get("input_type", "unknown")
        stage = problem.get("problem_stage", "unknown")
        objective_eval = problem.get("initial_objective_evaluation", {})
        ranked = comparison.get("ranked_ideas", [])
        recommended = comparison.get("recommended_route") or comparison.get("recommendation")
        idea_items = ideas.get("ideas", [])
        evidence_items = literature.get("evidence", [])

        lines = [
            f"# {title}",
            "",
            "## Executive Summary",
            "",
            f"IdeaLab 将本输入判定为 `{input_type}`，当前阶段为 `{stage}`。本报告基于已完成的文献检索、候选方案生成、机制推演和批判审查整理最终研究判断。",
            "",
            f"推荐路线：{self._format_inline(recommended) if recommended else '需要结合候选方案继续确认。'}",
            "",
            "重要边界：当前系统尚未执行真实代码实验或外部实验；文中“结果”如未特别注明，均指基于文献与模型推理得到的初步判断。",
            "",
            "## 输入类型与问题阶段判定",
            "",
            f"- 原始输入：{self._format_inline(raw_input[:500])}",
            f"- 任务类型：`{input_type}`",
            f"- 问题阶段：`{stage}`",
            f"- 研究目标：{self._format_inline(problem.get('objective') or problem.get('target_outcome') or '形成可验证研究路线')}",
            "",
            "## 客观评价",
            "",
        ]
        if isinstance(objective_eval, dict) and objective_eval:
            for key in ["feasibility", "necessity", "novelty"]:
                item = objective_eval.get(key, {})
                if isinstance(item, dict):
                    lines.append(f"- **{key}**：{item.get('score', 'N/A')}/10。{item.get('rationale', '')}")
        else:
            lines.extend([
                "- **feasibility**：需要通过最小验证实验评估工程可行性。",
                "- **necessity**：需要用文献与实际痛点确认该问题是否值得投入。",
                "- **novelty**：需要检索相近方法，避免只是已有工作的重新表述。",
            ])

        lines.extend([
            "",
            "## 文献与证据分析",
            "",
            f"检索摘要：{self._format_inline(literature.get('summary', '尚无可用文献摘要。'))}",
            "",
        ])
        if evidence_items:
            for item in evidence_items[:8]:
                title_text = item.get("title") or "Untitled"
                year = item.get("year") or "n.d."
                venue = item.get("venue") or "unknown venue"
                citation = item.get("citation_count", 0)
                lines.append(f"- **{title_text}** ({year}, {venue}, citations={citation})：{self._format_inline(item.get('abstract', '无摘要')[:260])}")
        else:
            lines.append("- 尚未获得 Semantic Scholar 检索结果；创新性判断必须在补充文献后重新校准。")

        lines.extend([
            "",
            "## IdeaLab 最终方案",
            "",
        ])
        if recommended:
            lines.append(f"当前推荐优先推进：**{self._format_inline(recommended)}**。")
        if ranked:
            lines.append("")
            lines.append("候选路线排序：")
            for item in ranked[:6]:
                if isinstance(item, dict):
                    scores = item.get("scores", {})
                    score_text = f" scores={scores}" if scores else ""
                    lines.append(f"- Rank {item.get('rank', '?')}：{item.get('title') or item.get('idea') or item.get('idea_id')}{score_text}。{item.get('rationale', '')}")
        elif idea_items:
            for item in idea_items[:5]:
                lines.append(f"- **{item.get('title', item.get('id', '候选方案'))}**：{item.get('hypothesis') or item.get('short_hypothesis') or item.get('mechanism', '')}")

        lines.extend([
            "",
            "## 具体实现方法",
            "",
        ])
        reasoning_paths = reasoning.get("reasoning_paths") or reasoning.get("paths") or []
        if reasoning_paths:
            for path in reasoning_paths[:4]:
                if not isinstance(path, dict):
                    continue
                lines.append(f"### {path.get('idea_id') or path.get('idea') or '实现路径'}")
                if path.get("implementation_details"):
                    lines.append(self._format_block(path["implementation_details"]))
                if path.get("causal_chain"):
                    lines.append("")
                    lines.append("关键推理链：")
                    chain = path["causal_chain"]
                    for step in chain if isinstance(chain, list) else [chain]:
                        lines.append(f"- {self._format_inline(step)}")
                if path.get("validation_design"):
                    lines.append("")
                    lines.append(f"最小验证设计：{self._format_inline(path['validation_design'])}")
                lines.append("")
        else:
            lines.extend([
                "建议先实现最小原型：",
                "",
                "```text",
                "1. 固定输入/数据集，建立最小可复现实验环境。",
                "2. 实现核心方法与一个强基线。",
                "3. 记录主指标、消融指标、失败样例与运行成本。",
                "4. 用结果回填 IdeaLab 图谱，重新执行 critic 与 compare。",
                "```",
                "",
            ])

        lines.extend([
            "## 验证/实验设计与初步结果",
            "",
            "尚未发现真实代码执行或实验节点，因此当前没有可声明的实验结果。以下是建议的最小验证路线：",
            "",
        ])
        roadmap = comparison.get("validation_roadmap", [])
        if isinstance(roadmap, list) and roadmap:
            for item in roadmap:
                lines.append(f"- {self._format_inline(item)}")
        else:
            lines.extend([
                "- 定义主指标与失败判据，避免只看正向示例。",
                "- 构造 20-50 个代表性样例或选取公开基准。",
                "- 与最直接 baseline 比较，至少做一次 ablation。",
                "- 把失败样例输入下一轮 IdeaLab，检查假设是否需要修改。",
            ])

        lines.extend([
            "",
            "## 风险、失败模式与反例",
            "",
        ])
        risks = critic.get("critical_risks") or critic.get("risks") or decomposition.get("possible_failure_modes") or []
        if isinstance(risks, list) and risks:
            for risk in risks[:10]:
                lines.append(f"- {self._format_inline(risk)}")
        else:
            lines.append("- 风险信息不足；需要在下一轮加入更强的反方审查。")
        warnings = review.get("final_report_warnings") or review.get("unsupported_claims") or []
        if isinstance(warnings, list) and warnings:
            lines.append("")
            lines.append("必须保留的不确定性：")
            for warning in warnings[:8]:
                lines.append(f"- {self._format_inline(warning)}")

        lines.extend([
            "",
            "## 结论与下一步建议",
            "",
            "1. 先补齐文献检索与最小实验，避免把概念推理误当成验证结论。",
            "2. 优先推进排序最高且最容易低成本验证的路线；高风险高收益路线作为第二分支保留。",
            "3. 将实验失败样例、人类确认信息和关键代码回填 IdeaLab，重新执行批判与路径比较。",
            "",
            "## 附录：推演来源",
            "",
            f"- Run ID: `{graph.run_id}`",
            f"- 模式: `{graph.mode}`",
            f"- 节点数: {len(graph.nodes)}",
        ])
        return "\n".join(lines)

    def _fallback_report(self, graph: Graph) -> str:
        by_type = {node.type: node.output for node in graph.nodes if node.output is not None}
        by_type_list: dict[str, list[Any]] = {}
        for node in graph.nodes:
            if node.output is not None:
                by_type_list.setdefault(node.type, []).append(node.output)

        raw_input = ""
        if graph.nodes and isinstance(graph.nodes[0].input, dict):
            raw_input = str(graph.nodes[0].input.get("raw_user_input", ""))

        problem = by_type.get("problem") if isinstance(by_type.get("problem"), dict) else {}
        decomposition = by_type.get("decomposition") if isinstance(by_type.get("decomposition"), dict) else {}
        literature = by_type.get("literature") if isinstance(by_type.get("literature"), dict) else {}
        ideas = by_type.get("ideation") if isinstance(by_type.get("ideation"), dict) else {}
        comparison = by_type.get("comparison") if isinstance(by_type.get("comparison"), dict) else {}
        evaluation = by_type.get("evaluation") if isinstance(by_type.get("evaluation"), dict) else {}
        review = by_type.get("cross_review") if isinstance(by_type.get("cross_review"), dict) else {}
        reasoning_list = [item for item in by_type_list.get("reasoning", []) if isinstance(item, dict)]
        critic_list = [item for item in by_type_list.get("critic", []) if isinstance(item, dict)]

        title = problem.get("title") or raw_input.strip().split("\n")[0][:80] or "IdeaLab 研究推演报告"
        input_type = problem.get("input_type", "unknown")
        stage = problem.get("problem_stage", "unknown")
        objective = problem.get("objective") or problem.get("target_outcome") or "形成可验证研究路线"
        objective_eval = problem.get("initial_objective_evaluation", {})
        idea_items = self._idea_items(ideas)
        evidence_items = literature.get("evidence", []) if isinstance(literature.get("evidence"), list) else []
        ranked = comparison.get("ranked_ideas", [])
        recommended = comparison.get("recommended_route") or comparison.get("recommendation") or "需要继续比较候选路线"
        btl_scores = evaluation.get("btl_scores", {})
        elo_scores = evaluation.get("elo_scores", {})
        dimension_aggregates = evaluation.get("dimension_aggregates", {})
        pareto_categories = evaluation.get("pareto_categories", {})
        experiment_plans = evaluation.get("experiment_plans", [])

        lines = [
            f"# {title}",
            "",
            "## 目录",
            "",
            "1. Executive Summary",
            "2. 输入解析与任务定位",
            "3. 问题背景与研究价值",
            "4. 初始客观评价",
            "5. 关键问题拆解",
            "6. 文献与证据分析",
            "7. 候选想法与分支推演",
            "8. Evaluation：多模型成对评估与量化排序",
            "9. 路径比较与最终推荐",
            "10. 实现方案",
            "11. 验证与实验",
            "12. 结果分析",
            "13. 风险、反例与失败模式",
            "14. 结论与下一步计划",
            "15. 附录",
            "",
            "## 1. Executive Summary",
            "",
            f"IdeaLab 将本输入判定为 `{input_type}`，当前研究阶段为 `{stage}`。报告的核心目标是从问题或 idea 出发，给出可推进研究路线、关键验证实验和风险边界，而不是记录节点是否完成。",
            "",
            f"当前推荐路线是：**{self._format_inline(recommended)}**。这个推荐来自候选想法生成、机制推演、批判审查和路径比较；如果尚未执行真实实验，它只能视为优先级判断，而不是已经验证的研究结论。",
            "",
            "当前最关键的下一步是补齐最低成本验证：明确 baseline、主指标、失败判据和可复现实验脚本。任何没有实验支持的正向判断都应保留为待验证假设。",
            "",
            "## 2. 输入解析与任务定位",
            "",
            "### 2.1 原始输入",
            "",
            self._format_inline(raw_input[:1200]),
            "",
            "### 2.2 输入类型判定",
            "",
            f"- 任务类型：`{input_type}`",
            f"- 当前阶段：`{stage}`",
            f"- 研究目标：{self._format_inline(objective)}",
            "",
            "### 2.3 需要用户确认的问题",
            "",
        ]
        questions = problem.get("clarification_questions", [])
        if isinstance(questions, list) and questions:
            lines.extend([f"- {self._format_inline(question)}" for question in questions])
        else:
            lines.append("- 当前没有生成必须暂停流程等待确认的问题。")

        lines.extend([
            "",
            "## 3. 问题背景与研究价值",
            "",
            "### 3.1 背景",
            "",
            self._format_inline(problem.get("background") or decomposition.get("problem_frame") or "背景信息不足，需要继续补充领域上下文。"),
            "",
            "### 3.2 必要性",
            "",
            "该问题是否值得推进，取决于它是否对应真实瓶颈、是否影响足够重要的任务场景、以及现有方法是否仍有明确未解决空间。IdeaLab 会在文献证据和实验结果进入后重新校准此判断。",
            "",
            "### 3.3 成功标准",
            "",
            self._format_block(problem.get("success_criteria") or ["定义可量化主指标", "设计最小验证实验", "与强基线比较", "记录失败样例"]),
            "",
            "## 4. 初始客观评价",
            "",
        ])
        if isinstance(objective_eval, dict) and objective_eval:
            labels = {"feasibility": "可行性", "necessity": "必要性", "novelty": "创新性"}
            for key, label in labels.items():
                item = objective_eval.get(key, {})
                lines.extend([f"### {label}", ""])
                if isinstance(item, dict):
                    lines.append(f"评分：**{item.get('score', 'N/A')}/10**。{item.get('rationale', '')}")
                else:
                    lines.append("尚未形成结构化评分。")
                lines.append("")
        else:
            lines.extend([
                "### 可行性",
                "",
                "需要通过最小验证实验评估工程可行性。",
                "",
                "### 必要性",
                "",
                "需要用文献与实际痛点确认该问题是否值得投入。",
                "",
                "### 创新性",
                "",
                "需要检索相近方法，避免只是已有工作的重新表述。",
                "",
            ])
        lines.extend(["### 总体判断", "", f"当前总体判断：{self._format_inline(recommended)}。", ""])

        lines.extend(["## 5. 关键问题拆解", "", "### 5.1 子问题", ""])
        sub_questions = decomposition.get("sub_questions", [])
        lines.extend([f"- {self._format_inline(item)}" for item in sub_questions] if isinstance(sub_questions, list) and sub_questions else ["- 尚未形成结构化子问题。"])
        lines.extend(["", "### 5.2 关键变量", ""])
        variables = decomposition.get("variables", [])
        lines.extend([f"- {self._format_inline(item)}" for item in variables] if isinstance(variables, list) and variables else ["- 尚未形成结构化变量列表。"])
        lines.extend(["", "### 5.3 隐含假设", ""])
        assumptions = decomposition.get("assumptions") or problem.get("hidden_assumptions") or []
        lines.extend([f"- {self._format_inline(item)}" for item in assumptions] if isinstance(assumptions, list) and assumptions else ["- 尚未形成显式假设列表。"])
        lines.extend(["", "### 5.4 最小证据需求", ""])
        minimum_evidence = decomposition.get("minimum_useful_evidence", [])
        lines.extend([f"- {self._format_inline(item)}" for item in minimum_evidence] if isinstance(minimum_evidence, list) and minimum_evidence else ["- 至少需要相关工作、强基线、最小实验和失败样例。"])

        lines.extend([
            "",
            "## 6. 文献与证据分析",
            "",
            "### 6.1 检索策略",
            "",
            f"当前检索式：`{self._format_inline(literature.get('query', 'N/A'))}`。",
            "",
            "### 6.2 相关工作与关键证据",
            "",
        ])
        if evidence_items:
            for item in evidence_items[:8]:
                lines.append(f"- **{item.get('title', 'Untitled')}** ({item.get('year', 'n.d.')}, {item.get('venue', 'unknown')})：{self._format_inline(str(item.get('abstract') or '无摘要')[:280])}")
        else:
            lines.append("- 尚未获得有效文献结果；创新性判断必须在补充文献后重新校准。")
        lines.extend(["", "### 6.3 证据缺口与创新性风险", "", self._format_inline(literature.get("error") or "需要继续补充直接相关工作、替代方法、失败案例和评测方法。"), ""])

        lines.extend(["## 7. 候选想法与分支推演", ""])
        if idea_items:
            for idx, item in enumerate(idea_items[:8], start=1):
                lines.extend([
                    f"### 7.{idx} {item.get('title', item.get('id', '候选方案'))}",
                    "",
                    f"**核心假设**：{self._format_inline(item.get('hypothesis') or item.get('short_hypothesis') or 'N/A')}",
                    "",
                    f"**机制推演**：{self._format_inline(item.get('proposed_mechanism') or item.get('mechanism') or '需要进一步展开。')}",
                    "",
                    "**实现变体**：",
                ])
                variants = item.get("implementation_variants", [])
                lines.extend([f"- {self._format_inline(v)}" for v in variants] if isinstance(variants, list) and variants else ["- 尚未形成实现变体。"])
                lines.extend(["", f"**最小验证**：{self._format_inline(item.get('cheapest_validation') or item.get('validation') or '需要设计最小验证实验。')}", "", "**风险与反例**："])
                risks = item.get("risks", [])
                lines.extend([f"- {self._format_inline(r)}" for r in risks] if isinstance(risks, list) and risks else ["- 尚未形成风险列表。"])
                lines.append("")
        else:
            lines.append("尚未生成候选想法。")

        lines.extend(["## 8. Evaluation：多模型成对评估与量化排序", ""])
        lines.append("当前 Evaluation 基于多模型成对比较、维度评分、BTL 主排序和 Elo 辅助排序。真实实验尚未执行，因此所有实验相关内容均为计划占位。")
        lines.append("")
        if btl_scores:
            lines.append("| Idea | BTL | Elo | Pareto 类别 | 维度评分摘要 |")
            lines.append("| --- | ---: | ---: | --- | --- |")
            for idea_id, score in sorted(btl_scores.items(), key=lambda item: item[1], reverse=True):
                dims = dimension_aggregates.get(idea_id, {})
                dim_text = ", ".join(f"{key}={value}" for key, value in dims.items())
                lines.append(f"| {idea_id} | {score} | {elo_scores.get(idea_id, 'N/A')} | {self._format_inline(pareto_categories.get(idea_id, '未分类'))} | {self._format_inline(dim_text)} |")
            disagreement = evaluation.get("model_disagreement", {}).get("disagreement_rate", 0)
            lines.extend(["", f"模型分歧率：**{disagreement}**。分歧较高的成对比较需要人工复核或补充证据。", ""])
        else:
            lines.extend(["尚未形成 Evaluation 排名；通常需要至少两个候选 idea 才能进行成对比较。", ""])

        lines.extend(["## 9. 路径比较与最终推荐", ""])
        if ranked:
            lines.append("| 排名 | 路线 | 评分/理由 |")
            lines.append("| --- | --- | --- |")
            for item in ranked[:8]:
                if isinstance(item, dict):
                    route = item.get("title") or item.get("idea") or item.get("idea_id") or "N/A"
                    rationale = item.get("rationale") or item.get("scores") or ""
                    lines.append(f"| {item.get('rank', '?')} | {self._format_inline(route)} | {self._format_inline(rationale)} |")
        else:
            lines.append("尚未形成结构化排序表。")
        lines.extend(["", f"最终推荐：**{self._format_inline(recommended)}**。", ""])

        lines.extend([
            "## 10. 实现方案",
            "",
            "### 9.1 系统设计与算法流程",
            "",
            "```text",
            "1. 固定输入/数据集，建立最小可复现实验环境。",
            "2. 实现候选路线的核心模块与一个强基线。",
            "3. 记录主指标、消融指标、失败样例与运行成本。",
            "4. 用结果回填 IdeaLab 图谱，重新执行 critic 与 compare。",
            "```",
            "",
            "### 9.2 来自推演节点的实现细节",
            "",
        ])
        for idx, reasoning in enumerate(reasoning_list[:6], start=1):
            paths = reasoning.get("reasoning_paths") or reasoning.get("paths") or []
            if isinstance(paths, list):
                for path in paths[:3]:
                    if isinstance(path, dict):
                        lines.append(f"- {self._format_inline(path.get('idea_id') or path.get('idea') or f'推演 {idx}')}：{self._format_inline(path.get('implementation_details') or path.get('chain') or path.get('causal_chain') or 'N/A')}")

        lines.extend(["", "## 11. 验证与实验", "", "### 11.1 已完成验证", "", "尚未进行真实实验验证。Phase 1 只将实验纳入评估闭环，当前不会执行代码、benchmark 或外部实验。", "", "### 11.2 最小验证实验", ""])
        if experiment_plans:
            for plan in experiment_plans[:8]:
                lines.append(f"- **{plan.get('idea_id')}**（{plan.get('status')}）：{self._format_inline(plan.get('minimum_validation'))}")
        else:
            roadmap = comparison.get("validation_roadmap", [])
            lines.extend([f"- {self._format_inline(item)}" for item in roadmap] if isinstance(roadmap, list) and roadmap else [
                "- 定义主指标与失败判据，避免只看正向示例。",
                "- 构造代表性样例或选取公开基准。",
                "- 与最直接 baseline 比较，至少做一次 ablation。",
                "- 把失败样例输入下一轮 IdeaLab，检查假设是否需要修改。",
            ])
        lines.extend(["", "### 11.3 对照组、指标与消融", ""])
        if experiment_plans:
            for plan in experiment_plans[:5]:
                lines.append(f"- **{plan.get('idea_id')}**：指标 {self._format_inline(plan.get('metrics'))}；对照 {self._format_inline(plan.get('controls'))}；消融 {self._format_inline(plan.get('ablation_plan'))}。")
        else:
            lines.extend(["- 对照组：最直接 baseline、已有方法或当前系统默认实现。", "- 主指标：任务成功率、质量指标、成本、延迟或资源占用。", "- 消融：逐一移除关键模块，确认每个模块的独立贡献。"])
        lines.append("")

        lines.extend(["## 12. 结果分析", "", "当前没有真实实验结果，因此本节只分析预期结果和证据强度。所有正向结论都必须在实验后重新校准。若后续实验失败，应将失败样例写回下一轮 IdeaLab，并重新执行反方批判、Evaluation 与路径比较。", ""])

        lines.extend(["## 13. 风险、反例与失败模式", ""])
        risks: list[Any] = []
        for critic in critic_list:
            value = critic.get("critical_risks") or critic.get("risks") or []
            if isinstance(value, list):
                risks.extend(value)
        if not risks:
            risks = decomposition.get("possible_failure_modes") or []
        lines.extend([f"- {self._format_inline(risk)}" for risk in risks[:12]] if isinstance(risks, list) and risks else ["- 风险信息不足；需要在下一轮加入更强的反方审查。"])
        warnings = review.get("final_report_warnings") or review.get("unsupported_claims") or []
        if isinstance(warnings, list) and warnings:
            lines.extend(["", "必须保留的不确定性："])
            lines.extend([f"- {self._format_inline(warning)}" for warning in warnings[:8]])

        lines.extend([
            "",
            "## 14. 结论与下一步计划",
            "",
            f"当前结论是：{self._format_inline(recommended)}。这个结论来自 IdeaLab 的文献检索、分支推演、批判审查与路径比较，但尚未经过真实实验验证。",
            "",
            "### 14.1 立即执行",
            "",
            "1. 补齐文献检索与强基线，避免把概念推理误当成验证结论。",
            "",
            "### 14.2 短期迭代",
            "",
            "2. 优先推进排序最高且最容易低成本验证的路线；高风险高收益路线作为第二分支保留。",
            "",
            "### 14.3 长期路线",
            "",
            "3. 将实验失败样例、人类确认信息和关键代码回填 IdeaLab，重新执行批判与路径比较。",
            "",
            "## 15. 附录",
            "",
            "### 15.1 推演节点索引",
            "",
            f"- Run ID: `{graph.run_id}`",
            f"- 模式: `{graph.mode}`",
            f"- 节点数: {len(graph.nodes)}",
        ])
        for node in graph.nodes:
            lines.append(f"- `{node.type}`：{node.title}，状态 `{node.status}`。")
        lines.extend(["", "### 15.2 文献列表", ""])
        if evidence_items:
            lines.extend([f"- {item.get('title', 'Untitled')} ({item.get('year', 'n.d.')}) {item.get('url', '')}" for item in evidence_items[:20]])
        else:
            lines.append("- 暂无可用文献列表。")
        lines.extend(["", "### 15.3 配置与模型", "", "模型、prompt 版本和工具调用信息可在对应节点详情中查看。", "", "### 15.4 Evaluation 原始数据", "", "Evaluation 数据保存在 `evaluations/evaluation_run.json`、`evaluations/pairwise_judgments.jsonl`、`evaluations/rankings.json`；实验计划占位保存在 `experiments/plan_stubs.json`。", "", "### 15.5 原始结构化数据", "", "完整结构化数据保存在本次 workspace 的 `graph.json`、`problem.json`、`ideas.json`、`evidence/` 与 `reports/` 下。"])
        return "\n".join(lines)

    def _format_inline(self, value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        text = str(value).replace("\n", " ").strip()
        return text or "N/A"

    def _format_block(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"


engine = IdeaLabEngine()
