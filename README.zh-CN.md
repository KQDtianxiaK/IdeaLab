# IdeaLab

<p align="center">
  <a href="./README.md"><img alt="English" src="https://img.shields.io/badge/Language-English-2266DD"></a>
  <a href="./README.zh-CN.md"><img alt="中文" src="https://img.shields.io/badge/语言-中文-00A676"></a>
</p>

IdeaLab 是一个本地 AI 科研构思工作台。它把开放问题、研究方向、方法
idea 或早期结果转化为可追踪推演图、可量化 idea 评估和结构化研究报告。

IdeaLab 刻意放在完整自动实验之前的位置。它主要回答：**下一步最值得做
哪个 idea，为什么？**

## 当前状态

IdeaLab 目前是一个本地单用户原型，已经完成端到端科研构思闭环：

```text
problem -> decomposition -> literature -> ideation
-> per-idea reasoning + critic -> evaluation
-> comparison -> cross_review -> report
```

当前系统可以生成候选 idea，推演每条路线的机制，对每个分支做反方批判，
通过多维成对比较量化评估 idea，用 BTL/Elo 风格分数排序，并生成最终
Markdown 研究报告。

真实实验执行尚未实现。实验计划已经进入 evaluation 闭环，但当前只作为
`planned` / `skipped` 验证占位存在，并会明确标注“尚未执行实验”。

## 核心亮点

- **可追踪推演图**：每个流程步骤都是节点，保留输入、输出、模型来源、工具调用和状态。
- **适合人阅读的节点页**：详情页先说明这一步在做什么，并优先展示关键结论；原始 JSON 默认折叠。
- **多模型 Evaluation**：可配置多个 judge stage，从创新性、必要性、可行性、影响力、可验证性、风险、证据强度、信息增益等维度成对比较候选 idea。
- **量化排序**：成对判断会聚合为 BTL 分数、Elo 分数、维度表、模型分歧和 Pareto 分类。
- **证据感知文献检索**：文献 prompt 先规划多条 Semantic Scholar 检索式，再执行多 query 检索、去重并保存本地 evidence metadata。
- **实验计划占位**：每个 idea 可生成最小验证、指标、对照、消融、预期结果和失败信号，但不会执行实验。
- **Human-in-the-loop**：用户可在运行中注入评论、批准、拒绝、评分覆盖、合并建议或重新评估请求。
- **断点重跑**：固定流程失败或停止后，可从 evaluation、comparison、cross_review、report 等下游节点继续。
- **本地优先配置**：Provider、阶段模型、Prompt 和 API key 都可在浏览器中编辑，并保存到本地。

## 用户界面

前端由同一个 FastAPI 进程提供，包含：

- 支持鼠标拖拽平移的图谱画布，以及可拖拽节点；
- 节点卡片展示节点类型、状态、摘要和模型标签；
- 全屏节点详情页，左侧目录，正文按重点内容组织；
- 研究决策概览：排名表、评分热力图、成对比较日志、证据图、假设账本、验证计划和人工决策日志；
- 设置、历史、概览、报告弹窗支持点击遮罩关闭；
- Markdown 报告查看器。

## 项目结构

```text
.
├── README.md
├── README.zh-CN.md
├── REPORT_TEMPLATE.md     # 中文报告模板
├── requirements.txt       # Python 依赖
└── idealab/
    ├── app.py             # FastAPI 应用与 REST API
    ├── config.py          # 本地配置、默认值、.env 加载
    ├── engine.py          # 固定/自由流程、断点重跑、报告生成
    ├── evaluation.py      # 成对评估、BTL/Elo、实验计划占位
    ├── llm.py             # OpenAI-compatible chat completion 客户端
    ├── models.py          # Pydantic 图谱、节点、运行、评估模型
    ├── storage.py         # workspace 和 graph 持久化
    ├── tools.py           # Semantic Scholar 集成
    └── static/
        ├── index.html     # 浏览器 UI
        ├── styles.css     # 样式
        └── app.js         # 图谱 UI、设置、概览、报告查看器
```

运行时文件生成在包外：

```text
idealab_config/
├── .env                   # 本地 API key，已 gitignore
├── models.json            # provider 与阶段模型配置
├── prompts.json           # 可编辑 prompt 模板
└── evaluation.json        # 维度、judge stages、评估策略

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

## 安装

建议使用 Python 3.10+。

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

## 快速启动

在仓库根目录运行：

```bash
python3 -m idealab.app
```

打开：

```text
http://127.0.0.1:8765
```

## API Key

缺少 key 时，IdeaLab 可以用 deterministic fallback 继续运行；但真实模型调用
和文献检索需要 API key。

常用 key：

- `DEEPSEEK_API_KEY`
- `CSTCLOUD_API_KEY`
- `S2_API_KEY`
- 通过 `api_key_env` 配置的任意自定义 provider key

推荐方式：在设置面板中保存 key。它们会写入：

```text
idealab_config/.env
```

Key 不会回显到浏览器，也不会写入浏览器 localStorage。

也可以手动配置：

```bash
mkdir -p idealab_config
printf 'DEEPSEEK_API_KEY="..."\nS2_API_KEY="..."\n' > idealab_config/.env
```

## 模型与 Prompt 配置

IdeaLab 使用 OpenAI-compatible chat completion 接口。Provider 和阶段模型配置
保存在：

```text
idealab_config/models.json
```

重要阶段包括：

- `default`
- `ideation`
- `critic`
- `report`
- `judge_primary`
- `judge_secondary`
- `evaluation_meta`

Prompt 模板保存在：

```text
idealab_config/prompts.json
```

Evaluation 配置保存在：

```text
idealab_config/evaluation.json
```

如果某个阶段设置：

```json
"max_tokens": null
```

IdeaLab 会在该模型请求中省略 `max_tokens` 字段。

## Evaluation 机制

Evaluation 是工作流中的一等节点，不是报告附录。默认评估流程：

1. 提取最多 `max_ideas` 个候选 idea；
2. 生成成对比较矩阵；
3. 将每对 idea 发送给所有配置的 judge stage；
4. 收集 winner、confidence、reasoning、evidence refs 和各维度评分；
5. 聚合为 BTL 分数、Elo 分数、维度均值、模型分歧和 Pareto 分类；
6. 生成实验计划占位；
7. 生成 evaluation meta-review。

如果 judge 模型调用失败，IdeaLab 会记录低置信度 fallback judgment。UI 和原始
评估文件都会保留 `judge_model` 与 fallback 元数据，方便区分真实模型判断和
启发式 fallback。

## REST API

主要接口：

- `GET /`：Web 应用
- `GET /api/health`：后端和 API key 状态
- `POST /api/runs`：创建新 run
- `GET /api/runs`：列出历史 run
- `GET /api/runs/{run_id}/graph`：读取推演图
- `POST /api/runs/{run_id}/human-input`：添加人工输入
- `POST /api/runs/{run_id}/stop`：停止 run
- `POST /api/runs/{run_id}/resume`：断点重跑
- `GET /api/runs/{run_id}/report`：读取 Markdown 报告
- `GET /api/runs/{run_id}/evaluation`：读取 Evaluation 输出
- `POST /api/runs/{run_id}/evaluation/recompute`：重新计算 Evaluation
- `POST /api/runs/{run_id}/evaluation/human-judgment`：追加人工 judgment
- `GET /api/config/models` / `PUT /api/config/models`
- `GET /api/config/prompts` / `PUT /api/config/prompts`
- `GET /api/config/evaluation` / `PUT /api/config/evaluation`
- `GET /api/config/api-keys` / `PUT /api/config/api-keys`

## 安全与隐私

- IdeaLab 当前是本地单用户原型。
- 不要在没有鉴权、授权、沙箱和资源限制的情况下暴露到公网。
- API key 保存在本地 `idealab_config/.env`。
- Runtime workspace 可能包含私有 prompt、idea、报告和模型输出，分享前需要审查。
- 当前实验阶段只规划验证工作，不执行代码或 benchmark。

## 当前限制

- 尚未实现沙箱实验执行。
- 尚未实现 benchmark runner、baseline runner、ablation runner。
- 文献检索依赖 Semantic Scholar 和 query 质量。
- 尚未实现 PDF 下载和全文解析。
- 尚无多用户登录和权限系统。
- Evaluation 质量依赖配置的 judge 模型、prompt 质量，以及是否触发 fallback。

## 路线图

近期：

- 更强的文献 query 规划和引用处理；
- 更完整的 evidence provenance 与报告引用；
- 更清晰的 fallback 检测和 judge 健康状态展示；
- 更细粒度的人工 evaluation override。

中期：

- 沙箱化最小验证实验；
- benchmark、baseline、ablation 和 multi-seed runner；
- 实验结果回流 Evaluation；
- 导出 review memo、论文大纲和演示文稿。

长期：

- 项目级 workspace；
- 插件化工具层；
- 基于 benchmark 的 idea 质量评估；
- 与自动实验系统集成。

## 许可证

尚未选择许可证。公开发布或接受外部贡献前，应补充 LICENSE 文件。
