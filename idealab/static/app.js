let currentRunId = null;
let currentGraph = null;
let pollTimer = null;
let currentModelsConfig = null;
let currentPromptsConfig = null;
let currentDetailsNodeId = null;
let currentNodePositions = {};
let dragState = null;

const $ = (id) => document.getElementById(id);

const FIELD_LABELS = {
  summary: "摘要 / summary",
  title: "标题 / title",
  status: "状态 / status",
  type: "类型 / type",
  model: "模型 / model",
  confidence: "置信度 / confidence",
  prompt_version: "Prompt 版本 / prompt_version",
  input: "输入 / input",
  output: "输出 / output",
  tool_calls: "工具调用 / tool_calls",
  reasoning_paths: "推演路径 / reasoning_paths",
  paths: "路径 / paths",
  implementation_details: "实现细节 / implementation_details",
  modules: "模块 / modules",
  name: "名称 / name",
  function: "功能 / function",
  causal_chain: "因果链 / causal_chain",
  chain: "链路 / chain",
  validation_design: "验证设计 / validation_design",
  possible_counterexamples: "可能反例 / possible_counterexamples",
  what_would_change_our_mind: "改变判断的证据 / what_would_change_our_mind",
  objective_evaluation: "客观评价 / objective_evaluation",
  critical_risks: "关键风险 / critical_risks",
  alternative_explanations: "替代解释 / alternative_explanations",
  missing_controls: "缺失控制 / missing_controls",
  likely_failure_cases: "可能失败场景 / likely_failure_cases",
  required_revisions: "需要修改 / required_revisions",
  ideas: "候选想法 / ideas",
  id: "ID / id",
  domain: "领域 / domain",
  background: "背景 / background",
  objective: "目标 / objective",
  problem_stage: "问题阶段 / problem_stage",
  core_claim_or_question: "核心主张或问题 / core_claim_or_question",
  hidden_assumptions: "隐含假设 / hidden_assumptions",
  success_criteria: "成功标准 / success_criteria",
  clarification_questions: "澄清问题 / clarification_questions",
  initial_objective_evaluation: "初始客观评价 / initial_objective_evaluation",
  score: "分数 / score",
  problem_frame: "问题框架 / problem_frame",
  sub_questions: "子问题 / sub_questions",
  variables: "变量 / variables",
  unknowns: "未知项 / unknowns",
  evaluation_dimensions: "评价维度 / evaluation_dimensions",
  possible_failure_modes: "可能失败模式 / possible_failure_modes",
  minimum_useful_evidence: "最低有效证据 / minimum_useful_evidence",
  if_false: "如果为假 / if_false",
  idea_id: "想法 ID / idea_id",
  hypothesis: "假设 / hypothesis",
  short_hypothesis: "短假设 / short_hypothesis",
  target_problem: "目标问题 / target_problem",
  proposed_mechanism: "提出机制 / proposed_mechanism",
  mechanism: "机制 / mechanism",
  why_it_might_work: "为何可能有效 / why_it_might_work",
  implementation_variants: "实现变体 / implementation_variants",
  required_evidence: "所需证据 / required_evidence",
  key_assumptions: "关键假设 / key_assumptions",
  assumptions: "假设 / assumptions",
  expected_results: "预期结果 / expected_results",
  risks: "风险 / risks",
  validation: "验证 / validation",
  cheapest_validation: "最低成本验证 / cheapest_validation",
  novelty_position: "创新性定位 / novelty_position",
  query: "检索式 / query",
  ok: "是否成功 / ok",
  error: "错误 / error",
  evidence_count: "证据数量 / evidence_count",
  evidence: "证据 / evidence",
  source_type: "来源类型 / source_type",
  year: "年份 / year",
  venue: "会议/期刊 / venue",
  citation_count: "引用数 / citation_count",
  abstract: "摘要 / abstract",
  relevance: "相关性 / relevance",
  reliability: "可靠性 / reliability",
  problem: "问题 / problem",
  decomposition: "问题拆解 / decomposition",
  idea: "想法 / idea",
  human_inputs: "人类输入 / human_inputs",
  instruction: "指令 / instruction",
  branches: "分支 / branches",
  ranked_ideas: "想法排序 / ranked_ideas",
  recommendation: "推荐 / recommendation",
  recommended_route: "推荐路线 / recommended_route",
  scores: "评分 / scores",
  rationale: "理由 / rationale",
  btl_scores: "BTL 分数 / btl_scores",
  elo_scores: "Elo 分数 / elo_scores",
  dimension_aggregates: "维度聚合 / dimension_aggregates",
  model_disagreement: "模型分歧 / model_disagreement",
  meta_review: "元评审 / meta_review",
  pareto_categories: "Pareto 分类 / pareto_categories",
  experiment_plans: "实验计划占位 / experiment_plans",
  judgments: "成对比较 / judgments",
};

const TOKEN_LABELS = {
  raw: "原始",
  user: "用户",
  source: "来源",
  index: "序号",
  display: "展示",
  reconstructed: "重构",
  provider: "服务商",
  used: "使用",
  fallback: "兜底",
  reason: "原因",
  workspace: "工作区",
  mode: "模式",
  content: "内容",
  path: "路径",
  preview: "预览",
  rank: "排名",
  novelty: "创新性",
  feasibility: "可行性",
  necessity: "必要性",
  impact: "影响力",
  testability: "可验证性",
  strength: "强度",
};

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) throw new Error(await res.text());
  const contentType = res.headers.get("content-type") || "";
  return contentType.includes("application/json") ? res.json() : res.text();
}

function showLanding() {
  $("landing").classList.remove("hidden");
  $("workspace").classList.add("hidden");
  $("details").classList.add("hidden");
  currentRunId = null;
  if (pollTimer) clearInterval(pollTimer);
}

function showWorkspace() {
  $("landing").classList.add("hidden");
  $("workspace").classList.remove("hidden");
}

async function loadHealth() {
  try {
    const data = await api("/api/health");
    const keys = data.api_keys || {};
    if (keys.all_required) {
      $("health").textContent = "API 状态正常";
    } else {
      const missing = [];
      if (!keys.deepseek) missing.push("DeepSeek");
      if (!keys.semantic_scholar) missing.push("Semantic Scholar");
      $("health").textContent = `API 未完全配置：${missing.join("、")}`;
    }
  } catch (err) {
    $("health").textContent = "后端未就绪";
  }
}

async function startRun() {
  const input = $("ideaInput").value.trim();
  if (!input) return alert("请先输入研究问题或 idea。");
  const mode = document.querySelector("input[name='mode']:checked").value;
  const graph = await api("/api/runs", {
    method: "POST",
    body: JSON.stringify({ input, mode }),
  });
  currentRunId = graph.run_id;
  currentNodePositions = loadNodePositions(currentRunId);
  showWorkspace();
  renderGraph(graph);
  pollTimer = setInterval(refreshGraph, 1200);
}

async function refreshGraph() {
  if (!currentRunId) return;
  try {
    const graph = await api(`/api/runs/${currentRunId}/graph`);
    renderGraph(graph);
    if (["completed", "failed", "stopped"].includes(graph.status) && pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  } catch (err) {
    console.error(err);
  }
}

function layoutNodes(graph) {
  const nodes = graph.nodes || [];
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const incoming = new Map();
  const outgoing = new Map();
  nodes.forEach((n) => {
    incoming.set(n.id, []);
    outgoing.set(n.id, []);
  });
  (graph.edges || []).forEach((e) => {
    if (outgoing.has(e.source)) outgoing.get(e.source).push(e.target);
    if (incoming.has(e.target)) incoming.get(e.target).push(e.source);
  });

  const positions = new Map();
  const depths = new Map();
  const order = new Map(nodes.map((node, index) => [node.id, index]));
  const xGap = 310;
  const yGap = 146;

  function depthOf(id, stack = new Set()) {
    if (depths.has(id)) return depths.get(id);
    if (stack.has(id)) return 0;
    stack.add(id);
    const parents = incoming.get(id) || [];
    const depth = parents.length ? Math.max(...parents.map((parentId) => depthOf(parentId, stack) + 1)) : 0;
    stack.delete(id);
    depths.set(id, depth);
    return depth;
  }

  nodes.forEach((node) => depthOf(node.id));
  const columns = new Map();
  nodes.forEach((node) => {
    const depth = depths.get(node.id) || 0;
    if (!columns.has(depth)) columns.set(depth, []);
    columns.get(depth).push(node);
  });

  const sortedDepths = [...columns.keys()].sort((a, b) => a - b);
  sortedDepths.forEach((depth) => {
    const column = columns.get(depth);
    column.sort((a, b) => {
      const aParents = incoming.get(a.id) || [];
      const bParents = incoming.get(b.id) || [];
      const aAnchor = aParents.length
        ? aParents.reduce((sum, id) => sum + (positions.get(id)?.y ?? order.get(id) ?? 0), 0) / aParents.length
        : order.get(a.id);
      const bAnchor = bParents.length
        ? bParents.reduce((sum, id) => sum + (positions.get(id)?.y ?? order.get(id) ?? 0), 0) / bParents.length
        : order.get(b.id);
      return aAnchor - bAnchor;
    });
    const count = column.length;
    const startY = Math.max(70, 70 + (Math.max(0, 5 - count) * yGap) / 2);
    column.forEach((node, index) => {
      positions.set(node.id, { x: 80 + depth * xGap, y: startY + index * yGap });
    });
  });

  for (const depth of sortedDepths.slice().reverse()) {
    const column = columns.get(depth);
    for (const node of column) {
      const kids = outgoing.get(node.id) || [];
      if (kids.length > 1) {
        const childYs = kids.map((id) => positions.get(id)?.y).filter((y) => typeof y === "number");
        if (childYs.length) {
          const avgY = childYs.reduce((a, b) => a + b, 0) / childYs.length;
          positions.set(node.id, { ...positions.get(node.id), y: avgY });
        }
      }
    }
  }
  const saved = loadNodePositions(graph.run_id);
  Object.entries(saved).forEach(([nodeId, pos]) => {
    if (positions.has(nodeId) && Number.isFinite(pos.x) && Number.isFinite(pos.y)) {
      positions.set(nodeId, { x: pos.x, y: pos.y });
    }
  });
  return { positions, byId };
}

function renderGraph(graph) {
  currentGraph = graph;
  currentNodePositions = loadNodePositions(graph.run_id);
  $("runMeta").textContent = `${graph.run_id} · ${graph.mode} · ${graph.status} · ${graph.nodes.length} nodes`;

  const { positions } = layoutNodes(graph);
  const nodeLayer = $("nodeLayer");
  const edgeLayer = $("edgeLayer");
  nodeLayer.innerHTML = "";
  edgeLayer.innerHTML = "";

  let maxX = 1600;
  let maxY = 900;
  positions.forEach((p) => {
    maxX = Math.max(maxX, p.x + 320);
    maxY = Math.max(maxY, p.y + 180);
  });
  nodeLayer.style.width = `${maxX}px`;
  nodeLayer.style.height = `${maxY}px`;
  edgeLayer.setAttribute("width", maxX);
  edgeLayer.setAttribute("height", maxY);
  edgeLayer.style.width = `${maxX}px`;
  edgeLayer.style.height = `${maxY}px`;

  (graph.edges || []).forEach((edge) => {
    const a = positions.get(edge.source);
    const b = positions.get(edge.target);
    if (!a || !b) return;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const x1 = a.x + 230;
    const y1 = a.y + 43;
    const x2 = b.x;
    const y2 = b.y + 43;
    const mid = (x1 + x2) / 2;
    path.setAttribute("d", `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "#b9c3d8");
    path.setAttribute("stroke-width", "2");
    edgeLayer.appendChild(path);
  });

  (graph.nodes || []).forEach((node) => {
    const p = positions.get(node.id);
    const el = document.createElement("article");
    el.className = `node ${node.status}`;
    el.style.left = `${p.x}px`;
    el.style.top = `${p.y}px`;
    el.innerHTML = `
      <div class="type">${escapeHtml(node.type)} · ${escapeHtml(node.status)}</div>
      <h3>${escapeHtml(node.title)}</h3>
      <p>${escapeHtml(node.summary || "")}</p>
    `;
    bindNodeDrag(el, node, p);
    nodeLayer.appendChild(el);
  });
  if (!$("details").classList.contains("hidden") && currentDetailsNodeId) {
    renderDetailsNodeNav(currentDetailsNodeId);
  }
}

function bindNodeDrag(el, node, initialPos) {
  el.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    dragState = {
      node,
      el,
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startX: initialPos.x,
      startY: initialPos.y,
      moved: false,
    };
    el.setPointerCapture(event.pointerId);
  });
  el.addEventListener("pointermove", (event) => {
    if (!dragState || dragState.node.id !== node.id) return;
    const dx = event.clientX - dragState.startClientX;
    const dy = event.clientY - dragState.startClientY;
    if (Math.abs(dx) + Math.abs(dy) > 4) dragState.moved = true;
    if (!dragState.moved) return;
    const x = Math.max(20, dragState.startX + dx);
    const y = Math.max(20, dragState.startY + dy);
    el.style.left = `${x}px`;
    el.style.top = `${y}px`;
    currentNodePositions[node.id] = { x, y };
    event.preventDefault();
  });
  el.addEventListener("pointerup", (event) => {
    if (!dragState || dragState.node.id !== node.id) return;
    const shouldOpen = !dragState.moved;
    el.releasePointerCapture(event.pointerId);
    dragState = null;
    if (shouldOpen) {
      openDetails(node);
    } else {
      saveNodePositions();
      renderGraph(currentGraph);
    }
  });
}

function loadNodePositions(runId) {
  if (!runId) return {};
  try {
    return JSON.parse(localStorage.getItem(`idealab-node-positions:${runId}`) || "{}");
  } catch (err) {
    return {};
  }
}

function saveNodePositions() {
  if (!currentRunId) return;
  localStorage.setItem(`idealab-node-positions:${currentRunId}`, JSON.stringify(currentNodePositions));
}

function openDetails(node) {
  currentDetailsNodeId = node.id;
  $("details").classList.remove("hidden");
  $("detailsBadge").textContent = `${node.type} · ${node.status}`;
  $("detailsTitle").textContent = node.title;
  $("detailsMeta").textContent = `${node.type} · ${node.status} · ${node.model || "no model"} · ${node.id}`;
  $("detailsBody").innerHTML = renderNodeDetails(node);
  renderDetailsNodeNav(node.id);
  $("details").scrollTo({ top: 0 });
}

function renderNodeDetails(node) {
  if (node.type === "evaluation" && node.output) {
    return renderEvaluationNodeDetails(node);
  }
  const sections = [
    { id: "summary", title: "节点摘要", value: { summary: node.summary || "暂无摘要" }, open: true },
    {
      id: "meta",
      title: "基础信息",
      value: {
        status: node.status,
        type: node.type,
        model: node.model || "未使用模型",
        confidence: node.confidence == null ? "N/A" : node.confidence,
        prompt_version: node.prompt_version || "N/A",
      },
      open: true,
    },
    { id: "input", title: "输入", value: node.input, open: valueSize(node.input) < 900 },
    { id: "output", title: "输出", value: node.output, open: true },
    { id: "tools", title: "工具调用", value: node.tool_calls || [], open: false },
    { id: "raw", title: "原始 JSON", value: node, open: false, raw: true },
  ];
  const toc = sections
    .map((section) => `<a href="#detail-${section.id}">${escapeHtml(section.title)}</a>`)
    .join("");
  const cards = sections.map((section) => renderValueCard(section.title, section.value, section)).join("");
  return `
    <aside class="detail-toc">
      <strong>目录</strong>
      ${toc}
    </aside>
    <section class="details-content">${cards}</section>
  `;
}

function renderEvaluationNodeDetails(node) {
  const output = node.output || {};
  const sections = [
    { id: "summary", title: "评估摘要", value: { summary: node.summary || "暂无摘要" }, open: true, custom: renderEvaluationSummary(output) },
    { id: "ranking", title: "BTL / Elo 排名", value: output, open: true, custom: renderEvaluationRanking(output) },
    { id: "dimensions", title: "多维评分", value: output.dimension_aggregates || {}, open: true, custom: renderDimensionTable(output.dimension_aggregates || {}) },
    { id: "meta", title: "Meta-review", value: output.meta_review || {}, open: true, custom: renderMetaReview(output.meta_review || {}) },
    { id: "judgments", title: "成对比较日志", value: output.judgments || [], open: true, custom: renderPairwiseJudgments(output.judgments || []) },
    { id: "experiments", title: "实验计划占位", value: output.experiment_plans || [], open: true, custom: renderExperimentPlans(output.experiment_plans || []) },
    { id: "raw", title: "原始 JSON", value: node, open: false, raw: true },
  ];
  const toc = sections.map((section) => `<a href="#detail-${section.id}">${escapeHtml(section.title)}</a>`).join("");
  const cards = sections.map((section) => renderValueCard(section.title, section.value, section)).join("");
  return `
    <aside class="detail-toc">
      <strong>目录</strong>
      ${toc}
    </aside>
    <section class="details-content">${cards}</section>
  `;
}

function renderDetailsNodeNav(activeId) {
  if (!currentGraph) return;
  const nodes = currentGraph.nodes || [];
  $("detailsNodeNav").innerHTML = nodes.map((node) => `
    <button class="node-nav-item ${node.id === activeId ? "active" : ""}" data-node-id="${escapeHtml(node.id)}" title="${escapeHtml(node.title)}">
      <span>${escapeHtml(node.title)}</span>
      <small>${escapeHtml(node.type)}</small>
    </button>
  `).join("");
  $("detailsNodeNav").querySelectorAll("[data-node-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const node = nodes.find((item) => item.id === button.dataset.nodeId);
      if (node) openDetails(node);
    });
  });
}

function renderValueCard(title, value, options = {}) {
  const open = options.open ? "open" : "";
  const body = options.raw
    ? `<pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre>`
    : options.custom || renderValue(value);
  return `
    <details id="detail-${escapeHtml(options.id || title)}" class="info-card" ${open}>
      <summary>
        <span>${escapeHtml(title)}</span>
        <small>${options.open ? "点击收起" : "点击展开"}</small>
      </summary>
      <div class="card-body">${body}</div>
    </details>
  `;
}

function renderEvaluationSummary(output) {
  const spec = output.spec || {};
  const disagreement = output.model_disagreement || {};
  const models = spec.judge_models || [];
  return `
    <div class="eval-summary">
      <div><span>评估对象</span><strong>${escapeHtml(spec.target_type || "idea")}</strong></div>
      <div><span>Idea 类型</span><strong>${escapeHtml(spec.idea_type || "unknown")}</strong></div>
      <div><span>Judge 数量</span><strong>${escapeHtml(String(models.length))}</strong></div>
      <div><span>模型分歧率</span><strong>${escapeHtml(String(disagreement.disagreement_rate ?? 0))}</strong></div>
      <div><span>实验策略</span><strong>${escapeHtml(spec.experiment_policy || "plan_only")}</strong></div>
    </div>
    <p class="muted">当前阶段只规划实验，不执行真实代码、benchmark 或外部实验。</p>
  `;
}

function renderEvaluationRanking(output) {
  const btl = output.btl_scores || {};
  const elo = output.elo_scores || {};
  const categories = output.pareto_categories || {};
  const ids = Object.keys(btl).sort((a, b) => (btl[b] || 0) - (btl[a] || 0));
  if (!ids.length) return `<p class="muted">暂无可用排名。</p>`;
  return `
    <div class="table-scroll">
      <table class="data-table">
        <thead><tr><th>Rank</th><th>Idea</th><th>BTL</th><th>Elo</th><th>Pareto 分类</th></tr></thead>
        <tbody>
          ${ids.map((id, index) => `
            <tr>
              <td>${index + 1}</td>
              <td><code>${escapeHtml(id)}</code></td>
              <td>${escapeHtml(String(btl[id]))}</td>
              <td>${escapeHtml(String(elo[id] ?? "N/A"))}</td>
              <td>${escapeHtml(categories[id] || "未分类")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderDimensionTable(aggregates) {
  const ids = Object.keys(aggregates || {});
  const dimensions = [...new Set(ids.flatMap((id) => Object.keys(aggregates[id] || {})))];
  if (!ids.length || !dimensions.length) return `<p class="muted">暂无多维评分。</p>`;
  return `
    <div class="table-scroll">
      <table class="data-table score-table">
        <thead><tr><th>Idea</th>${dimensions.map((dimension) => `<th>${escapeHtml(humanizeKey(dimension))}</th>`).join("")}</tr></thead>
        <tbody>
          ${ids.map((id) => `
            <tr>
              <td><code>${escapeHtml(id)}</code></td>
              ${dimensions.map((dimension) => {
                const value = Number(aggregates[id]?.[dimension] || 0);
                const tone = value >= 7 ? "high" : value >= 5 ? "mid" : "low";
                return `<td><span class="score-chip ${tone}">${escapeHtml(value.toFixed(2))}</span></td>`;
              }).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderPairwiseJudgments(judgments) {
  if (!judgments.length) return `<p class="muted">暂无成对比较记录。</p>`;
  return `<div class="judgment-list">${judgments.slice(0, 24).map((judgment) => `
    <article class="judgment-item">
      <header>
        <strong>${escapeHtml(judgment.idea_a_id)} vs ${escapeHtml(judgment.idea_b_id)}</strong>
        <span>Winner: ${escapeHtml(judgment.winner)}</span>
      </header>
      <p>${escapeHtml(judgment.reasoning || "暂无理由。")}</p>
      <small>${escapeHtml(judgment.judge_model || "unknown judge")} · confidence ${escapeHtml(String(judgment.confidence ?? "N/A"))}</small>
    </article>
  `).join("")}</div>`;
}

function renderMetaReview(meta) {
  if (!meta || !Object.keys(meta).length) return `<p class="muted">暂无 meta-review。</p>`;
  const blocks = [
    ["稳定推荐", meta.stable_recommendations],
    ["模型分歧", meta.model_disagreements],
    ["证据缺口", meta.evidence_gaps],
    ["需要人工复核", meta.human_review_needed],
    ["Prompt 反馈", meta.prompt_feedback],
    ["下一步评估动作", meta.next_evaluation_actions],
  ];
  return `
    <div class="meta-review">
      <p>${escapeHtml(meta.summary || "暂无摘要。")}</p>
      ${blocks.map(([title, value]) => `
        <section>
          <h4>${escapeHtml(title)}</h4>
          ${renderValue(value || [])}
        </section>
      `).join("")}
    </div>
  `;
}

function renderExperimentPlans(plans) {
  if (!plans.length) return `<p class="muted">暂无实验计划占位。</p>`;
  return `<div class="plan-list">${plans.map((plan) => `
    <article class="plan-item">
      <header>
        <strong>${escapeHtml(plan.idea_id || "unknown")}</strong>
        <span>${escapeHtml(plan.status || "planned")}</span>
      </header>
      <p>${escapeHtml(plan.minimum_validation || "未定义最小验证。")}</p>
      <dl>
        <dt>指标</dt><dd>${escapeHtml((plan.metrics || []).join("、") || "待定义")}</dd>
        <dt>对照</dt><dd>${escapeHtml((plan.controls || []).join("、") || "待定义")}</dd>
        <dt>失败信号</dt><dd>${escapeHtml(plan.failure_signal || "待定义")}</dd>
      </dl>
      <small>${escapeHtml(plan.reason_not_executed || "Phase 1 不执行实验。")}</small>
    </article>
  `).join("")}</div>`;
}

function renderValue(value, depth = 0, keyName = "") {
  if (value == null || value === "") return `<p class="muted">暂无内容</p>`;
  if (typeof value === "string") {
    if (value.length > 520) return renderLongText(value, keyName);
    return value.includes("\n") || value.startsWith("#")
      ? `<div class="markdown-body compact">${markdownToHtml(value)}</div>`
      : `<p>${escapeHtml(value)}</p>`;
  }
  if (typeof value === "number" || typeof value === "boolean") return `<code>${escapeHtml(String(value))}</code>`;
  if (Array.isArray(value)) {
    if (!value.length) return `<p class="muted">暂无内容</p>`;
    return `<div class="value-list">${value.map((item, index) => `
      <details class="value-item" ${depth < 2 ? "open" : ""}>
        <summary><span>${escapeHtml(itemLabel(item, index))}</span></summary>
        <div>${renderValue(item, depth + 1, keyName)}</div>
      </details>
    `).join("")}</div>`;
  }
  if (typeof value === "object") {
    return `<div class="object-grid">${Object.entries(value).map(([key, val]) => `
      <div class="object-row">
        <div class="object-key">${escapeHtml(humanizeKey(key))}</div>
        <div class="object-value">${renderValue(val, depth + 1, key)}</div>
      </div>
    `).join("")}</div>`;
  }
  return `<p>${escapeHtml(String(value))}</p>`;
}

function renderLongText(value, keyName = "") {
  const preview = value.slice(0, 260);
  const label = keyName ? humanizeKey(keyName) : "长文本 / long text";
  return `
    <details class="long-text">
      <summary><strong>${escapeHtml(label)}</strong><span>${escapeHtml(preview)}...</span></summary>
      <pre>${escapeHtml(value)}</pre>
    </details>
  `;
}

function itemLabel(item, index) {
  if (item && typeof item === "object") {
    return item.title || item.name || item.id || `条目 ${index + 1}`;
  }
  return `条目 ${index + 1}`;
}

function humanizeKey(key) {
  if (FIELD_LABELS[key]) return FIELD_LABELS[key];
  const original = String(key);
  const translated = original
    .split("_")
    .map((token) => TOKEN_LABELS[token] || token)
    .join(" ");
  return `${translated} / ${original}`;
}

function valueSize(value) {
  try {
    return JSON.stringify(value || "").length;
  } catch (err) {
    return 0;
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[ch]));
}

function formatScalar(value) {
  if (value == null) return "N/A";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function inlineMarkdown(text) {
  let html = escapeHtml(text);
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  return html;
}

function markdownToHtml(markdown) {
  const lines = String(markdown || "").split(/\r?\n/);
  const html = [];
  let inCode = false;
  let code = [];
  let listType = null;

  function closeList() {
    if (listType) {
      html.push(`</${listType}>`);
      listType = null;
    }
  }

  for (const line of lines) {
    if (line.trim().startsWith("```")) {
      if (inCode) {
        html.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
        code = [];
        inCode = false;
      } else {
        closeList();
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      code.push(line);
      continue;
    }
    if (!line.trim()) {
      closeList();
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      closeList();
      const level = heading[1].length;
      html.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }
    const bullet = line.match(/^\s*[-*]\s+(.+)$/);
    if (bullet) {
      if (listType !== "ul") {
        closeList();
        html.push("<ul>");
        listType = "ul";
      }
      html.push(`<li>${inlineMarkdown(bullet[1])}</li>`);
      continue;
    }
    const ordered = line.match(/^\s*\d+\.\s+(.+)$/);
    if (ordered) {
      if (listType !== "ol") {
        closeList();
        html.push("<ol>");
        listType = "ol";
      }
      html.push(`<li>${inlineMarkdown(ordered[1])}</li>`);
      continue;
    }
    closeList();
    html.push(`<p>${inlineMarkdown(line)}</p>`);
  }
  closeList();
  if (inCode) html.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
  return html.join("");
}

async function sendHumanInput() {
  const content = $("humanInput").value.trim();
  if (!content || !currentRunId) return;
  await api(`/api/runs/${currentRunId}/human-input`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
  $("humanInput").value = "";
  await refreshGraph();
}

async function stopRun() {
  if (!currentRunId) return;
  await api(`/api/runs/${currentRunId}/stop`, { method: "POST", body: "{}" });
  await refreshGraph();
}

async function openSettings() {
  $("settings").classList.remove("hidden");
  const [models, prompts, apiKeys] = await Promise.all([
    api("/api/config/models"),
    api("/api/config/prompts"),
    api("/api/config/api-keys"),
  ]);
  currentModelsConfig = models;
  currentPromptsConfig = prompts;
  $("modelsConfig").value = JSON.stringify(models, null, 2);
  $("promptsConfig").value = JSON.stringify(prompts, null, 2);
  $("s2Key").value = "";
  renderProvidersEditor(models);
  renderProviderKeyInputs(models, apiKeys);
  renderModelsEditor(models);
  renderPromptsEditor(prompts);
  renderApiKeyStatus(apiKeys);
}

function renderProvidersEditor(models) {
  const providers = models.providers || {};
  $("providersEditor").innerHTML = Object.entries(providers).map(([name, cfg]) => `
    <section class="settings-card provider-card" data-provider="${escapeHtml(name)}">
      <h4>${escapeHtml(cfg.label || name)}</h4>
      <label>Provider ID <input data-provider-field="id" value="${escapeHtml(name)}" disabled /></label>
      <label>Label <input data-provider-field="label" value="${escapeHtml(cfg.label || "")}" /></label>
      <label>Base URL <input data-provider-field="base_url" value="${escapeHtml(cfg.base_url || "")}" placeholder="https://api.example.com" /></label>
      <label>API key env <input data-provider-field="api_key_env" value="${escapeHtml(cfg.api_key_env || "")}" placeholder="CUSTOM_API_KEY" /></label>
      <label>Default model <input data-provider-field="default_model" value="${escapeHtml(cfg.default_model || "")}" /></label>
      <label>Timeout seconds <input data-provider-field="timeout_seconds" type="number" min="1" value="${escapeHtml(cfg.timeout_seconds ?? 60)}" /></label>
    </section>
  `).join("");
}

function renderProviderKeyInputs(models, apiKeys) {
  const providers = models.providers || {};
  const statuses = apiKeys.providers || {};
  $("providerKeyInputs").innerHTML = Object.entries(providers).map(([name, cfg]) => {
    const envName = cfg.api_key_env || `${name.toUpperCase()}_API_KEY`;
    const status = statuses[name] || {};
    const configured = status.configured ? "已配置" : "未配置";
    const required = status.required ? " · 当前使用" : "";
    return `
      <label>
        ${escapeHtml(cfg.label || name)} API Key <small>${escapeHtml(envName)} · ${configured}${required}</small>
        <input data-provider-key="${escapeHtml(name)}" type="password" autocomplete="off" placeholder="留空表示不修改" />
      </label>
    `;
  }).join("");
}

function renderModelsEditor(models) {
  const stages = models.stage_models || {};
  $("modelsEditor").innerHTML = Object.entries(stages).map(([stage, cfg]) => {
    const noLimit = cfg.max_tokens == null;
    return `
      <section class="settings-card" data-model-stage="${escapeHtml(stage)}">
        <h4>${escapeHtml(stage)}</h4>
        <label>Provider <input data-field="provider" value="${escapeHtml(cfg.provider || "")}" /></label>
        <label>Model <input data-field="model" value="${escapeHtml(cfg.model || "")}" /></label>
        <label>Temperature <input data-field="temperature" type="number" step="0.05" min="0" max="2" value="${escapeHtml(cfg.temperature ?? 0.4)}" /></label>
        <label class="inline-check"><input data-field="unlimited" type="checkbox" ${noLimit ? "checked" : ""} /> 不限制输出 token</label>
        <label>Max tokens <input data-field="max_tokens" type="number" min="1" value="${escapeHtml(noLimit ? "" : cfg.max_tokens)}" ${noLimit ? "disabled" : ""} /></label>
      </section>
    `;
  }).join("");
  $("modelsEditor").querySelectorAll("[data-field='unlimited']").forEach((checkbox) => {
    checkbox.addEventListener("change", (e) => {
      const card = e.target.closest("[data-model-stage]");
      const input = card.querySelector("[data-field='max_tokens']");
      input.disabled = e.target.checked;
      if (e.target.checked) input.value = "";
    });
  });
}

function renderPromptsEditor(prompts) {
  const blocks = [];
  for (const section of ["fixed", "free"]) {
    const group = prompts[section] || {};
    blocks.push(`<section class="settings-card prompt-group"><h4>${escapeHtml(section)}</h4>`);
    for (const [key, value] of Object.entries(group)) {
      blocks.push(`
        <label>
          ${escapeHtml(key)}
          <textarea data-prompt-section="${escapeHtml(section)}" data-prompt-key="${escapeHtml(key)}">${escapeHtml(value || "")}</textarea>
        </label>
      `);
    }
    blocks.push("</section>");
  }
  $("promptsEditor").innerHTML = blocks.join("");
}

function syncConfigFromEditors() {
  const models = JSON.parse($("modelsConfig").value);
  const prompts = JSON.parse($("promptsConfig").value);
  models.providers = models.providers || {};
  $("providersEditor").querySelectorAll("[data-provider]").forEach((card) => {
    const provider = card.dataset.provider;
    const cfg = { ...(models.providers[provider] || {}) };
    cfg.label = card.querySelector("[data-provider-field='label']").value.trim();
    cfg.base_url = card.querySelector("[data-provider-field='base_url']").value.trim();
    cfg.api_key_env = card.querySelector("[data-provider-field='api_key_env']").value.trim();
    cfg.default_model = card.querySelector("[data-provider-field='default_model']").value.trim();
    cfg.timeout_seconds = Number(card.querySelector("[data-provider-field='timeout_seconds']").value || 60);
    models.providers[provider] = cfg;
  });
  models.stage_models = models.stage_models || {};
  $("modelsEditor").querySelectorAll("[data-model-stage]").forEach((card) => {
    const stage = card.dataset.modelStage;
    const cfg = { ...(models.stage_models[stage] || {}) };
    cfg.provider = card.querySelector("[data-field='provider']").value.trim();
    cfg.model = card.querySelector("[data-field='model']").value.trim();
    cfg.temperature = Number(card.querySelector("[data-field='temperature']").value || 0.4);
    const unlimited = card.querySelector("[data-field='unlimited']").checked;
    cfg.max_tokens = unlimited ? null : Number(card.querySelector("[data-field='max_tokens']").value || 8000);
    models.stage_models[stage] = cfg;
  });
  $("promptsEditor").querySelectorAll("textarea[data-prompt-section]").forEach((textarea) => {
    const section = textarea.dataset.promptSection;
    const key = textarea.dataset.promptKey;
    prompts[section] = prompts[section] || {};
    prompts[section][key] = textarea.value;
  });
  $("modelsConfig").value = JSON.stringify(models, null, 2);
  $("promptsConfig").value = JSON.stringify(prompts, null, 2);
  return { models, prompts };
}

async function saveConfig() {
  try {
    const { models, prompts } = syncConfigFromEditors();
    const providerApiKeys = {};
    $("providerKeyInputs").querySelectorAll("[data-provider-key]").forEach((input) => {
      const value = input.value.trim();
      if (value) providerApiKeys[input.dataset.providerKey] = value;
    });
    const keyPayload = {
      provider_api_keys: providerApiKeys,
      semantic_scholar_api_key: $("s2Key").value.trim(),
    };
    await api("/api/config/models", { method: "PUT", body: JSON.stringify(models) });
    const apiKeys = await api("/api/config/api-keys", { method: "PUT", body: JSON.stringify(keyPayload) });
    const savedPrompts = await api("/api/config/prompts", { method: "PUT", body: JSON.stringify(prompts) });
    currentModelsConfig = models;
    currentPromptsConfig = savedPrompts;
    $("promptsConfig").value = JSON.stringify(savedPrompts, null, 2);
    $("configStatus").textContent = "已保存";
    $("s2Key").value = "";
    renderProviderKeyInputs(models, apiKeys);
    renderApiKeyStatus(apiKeys);
    await loadHealth();
  } catch (err) {
    $("configStatus").textContent = `保存失败：${err.message}`;
  }
}

function renderApiKeyStatus(keys) {
  const providers = keys.providers || {};
  const providerText = Object.entries(providers).map(([name, status]) => {
    const marker = status.configured ? "正常" : "未配置";
    const required = status.required ? "使用中" : "未使用";
    return `${status.label || name} ${marker}(${required})`;
  }).join(" · ");
  const s2 = keys.semantic_scholar ? "Semantic Scholar 正常" : "Semantic Scholar 未配置";
  $("apiKeyStatus").textContent = [providerText, s2].filter(Boolean).join(" · ");
}

async function openReport() {
  if (!currentRunId) return;
  $("report").classList.remove("hidden");
  const markdown = await api(`/api/runs/${currentRunId}/report`);
  $("reportBody").innerHTML = markdown ? markdownToHtml(markdown) : `<p class="muted">报告尚未生成。</p>`;
}

async function openHistory() {
  $("history").classList.remove("hidden");
  $("historyList").innerHTML = `<p class="muted">正在加载...</p>`;
  try {
    const runs = await api("/api/runs");
    if (!runs.length) {
      $("historyList").innerHTML = `<p class="muted">暂无历史推演。</p>`;
      return;
    }
    $("historyList").innerHTML = runs.map((run) => `
      <article class="history-item">
        <div>
          <h3>${escapeHtml(run.title || run.id)}</h3>
          <p>${escapeHtml(run.id)} · ${escapeHtml(run.mode)} · ${escapeHtml(run.status)}</p>
          <p>${escapeHtml(formatTime(run.updated_at || run.created_at))}</p>
        </div>
        <button data-run-id="${escapeHtml(run.id)}">打开</button>
      </article>
    `).join("");
    $("historyList").querySelectorAll("[data-run-id]").forEach((button) => {
      button.addEventListener("click", () => loadRun(button.dataset.runId));
    });
  } catch (err) {
    $("historyList").innerHTML = `<p class="muted">加载失败：${escapeHtml(err.message)}</p>`;
  }
}

async function loadRun(runId) {
  currentRunId = runId;
  currentNodePositions = loadNodePositions(currentRunId);
  const graph = await api(`/api/runs/${runId}/graph`);
  $("history").classList.add("hidden");
  $("details").classList.add("hidden");
  showWorkspace();
  renderGraph(graph);
  if (pollTimer) clearInterval(pollTimer);
  if (["running", "waiting_user"].includes(graph.status)) {
    pollTimer = setInterval(refreshGraph, 1200);
  }
}

function formatTime(value) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function bindEvents() {
  $("startRun").addEventListener("click", startRun);
  $("newRun").addEventListener("click", showLanding);
  $("sendHumanInput").addEventListener("click", sendHumanInput);
  $("humanInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendHumanInput();
  });
  $("stopRun").addEventListener("click", stopRun);
  $("detailsClose").addEventListener("click", () => {
    currentDetailsNodeId = null;
    $("details").classList.add("hidden");
  });
  $("settingsOpen").addEventListener("click", openSettings);
  $("settingsOpen2").addEventListener("click", openSettings);
  $("settingsClose").addEventListener("click", () => $("settings").classList.add("hidden"));
  $("saveConfig").addEventListener("click", saveConfig);
  $("historyOpen").addEventListener("click", openHistory);
  $("historyOpenLanding").addEventListener("click", openHistory);
  $("historyClose").addEventListener("click", () => $("history").classList.add("hidden"));
  $("reportOpen").addEventListener("click", openReport);
  $("reportClose").addEventListener("click", () => $("report").classList.add("hidden"));
}

bindEvents();
loadHealth();
