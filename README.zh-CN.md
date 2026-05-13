# IdeaLab

<p align="center">
  <a href="./README.md"><img alt="English" src="https://img.shields.io/badge/Language-English-2266DD"></a>
  <a href="./README.zh-CN.md"><img alt="中文" src="https://img.shields.io/badge/语言-中文-00A676"></a>
</p>

IdeaLab 是一个本地单用户 AI 科研构思系统，核心目标是围绕复杂研究问题进行“问题驱动的想法生成与深层推演”，并输出可追踪的推演图和结构化研究报告。

与主要强调自动实验执行的 AI Scientist 类系统不同，IdeaLab 把重心放在科研流程更早的位置：帮助研究者先判断**什么方向值得做**，再决定是否投入实验资源。

IdeaLab 会把用户输入的研究问题、研究方向、方法 idea 或已有结果转化为可追踪推演图：

```text
问题 -> 想法 -> 推演 -> 验证 -> 结论
```

最终输出不是简短回答，而是一份包含客观评价、文献证据、候选想法分支、实现方案、验证设计、风险分析、结论和下一步计划的完整研究推演报告。

## 当前状态

IdeaLab 目前是一个本地原型系统，适合用于：

- 探索研究方向；
- 在实验前完善方法 idea；
- 比较多条可行路线；
- 为讨论或组会生成可追踪推演图；
- 生成阶段性研究推演报告。

它还不是完整的自动实验平台。沙箱代码执行、基准评估、自动实验和论文写作等能力属于后续模块。

## 核心功能

- 极简 Web 界面：打开后只有标题、说明、输入框和模式选择。
- 固定流程模式：按结构化研究流程推进。
- 自由探索模式：AI agent 自主选择下一步动作。
- 推演图展示：每个阶段都会生成一个可点击节点。
- 候选想法分支：多个 idea 会成为独立分支，再汇总到路径比较节点。
- 全屏节点详情页：支持目录、折叠卡片、中英双语字段、节点间直接切换。
- 人类输入注入：推演中途可以插入想法，并在后续推理中注入上下文。
- 本地配置界面：可以修改 prompt、模型、temperature、max tokens 等。
- 本地 API key 存储：密钥保存在 `idealab_config/.env`，不写入浏览器 localStorage。
- Semantic Scholar 文献检索：作为证据层辅助创新性和必要性判断。
- 分阶段模型配置：不同阶段可使用不同模型和参数。
- 不限制输出 token 开关：当 `max_tokens` 为 `null` 时，请求中不传 `max_tokens`。
- 历史推演：可以重新打开已完成的历史 run。
- 固定报告模板：最终报告按 15 节研究报告格式生成。

## 工作流程

### 固定流程模式

固定流程当前包括：

1. 问题规范化
2. 方法型 idea 的可选澄清
3. 问题拆解
4. 文献与证据检索
5. 候选想法生成
6. 每个 idea 创建独立分支
7. 每个分支进行机制推演
8. 每个分支进行反方批判与风险分析
9. 路径比较与排序
10. 交叉审查
11. 最终研究推演报告生成

### 自由探索模式

自由探索模式中，AI agent 可以自主选择动作，例如：

- `decompose`
- `literature`
- `ideate`
- `reason`
- `critic`
- `compare`
- `validate`
- `report`

目标不是机械执行固定流程，而是最大化最终研究判断质量。

## 最终报告格式

最终报告以 Markdown 形式保存：

```text
idealab_workspaces/<run_id>/reports/report.md
```

报告固定包含 15 个部分：

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

详细模板见 [REPORT_TEMPLATE.md](REPORT_TEMPLATE.md)。

## 项目结构

```text
idealab/
├── app.py                 # FastAPI 应用和 REST API
├── config.py              # 本地配置、默认 prompt、.env 加载
├── engine.py              # 固定/自由推演流程与报告生成
├── llm.py                 # OpenAI-compatible chat completion 适配器
├── models.py              # Pydantic 图谱、运行、节点模型
├── storage.py             # workspace 和 graph 持久化
├── tools.py               # Semantic Scholar 工具
├── requirements.txt       # Python 依赖
├── REPORT_TEMPLATE.md     # 固定研究报告模板
└── static/
    ├── index.html         # 前端页面
    ├── styles.css         # 样式
    └── app.js             # 图谱 UI、设置、历史、报告查看
```

运行时文件会生成在包外：

```text
idealab_config/
├── .env                   # 本地 API key，已 gitignore
├── models.json            # 模型、provider、阶段配置
└── prompts.json           # 可编辑 prompt 模板

idealab_workspaces/
└── <run_id>/
    ├── graph.json         # 推演图
    ├── events.jsonl       # 审计事件流
    ├── problem.json
    ├── ideas.json
    ├── evidence/
    └── reports/report.md
```

## 安装

建议使用 Python 3.10+。

### 方式 A：uv

在仓库根目录执行：

```bash
uv venv
source .venv/bin/activate
uv pip install -r idealab/requirements.txt
```

### 方式 B：pip

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r idealab/requirements.txt
```

## 快速启动

在仓库根目录执行：

```bash
python3 -m idealab.app
```

打开：

```text
http://127.0.0.1:8765
```

前端和后端由同一个 FastAPI 进程提供。

## API Key 配置

缺少 API key 时，IdeaLab 可以使用 deterministic fallback 继续运行；但真实 LLM 推理和文献检索需要配置 API key。

当前支持：

- `DEEPSEEK_API_KEY`
- `S2_API_KEY`

推荐方式：打开页面右上角设置面板，在浏览器中填写并保存。密钥会写入：

```text
idealab_config/.env
```

该文件已被 gitignore，密钥不会回显到浏览器。

也可以手动创建：

```bash
mkdir -p idealab_config
cat > idealab_config/.env <<'EOF'
DEEPSEEK_API_KEY="..."
S2_API_KEY="..."
EOF
```

或在启动前导出环境变量：

```bash
export DEEPSEEK_API_KEY="..."
export S2_API_KEY="..."
python3 -m idealab.app
```

## 模型与 Prompt 配置

模型配置保存在：

```text
idealab_config/models.json
```

Prompt 配置保存在：

```text
idealab_config/prompts.json
```

二者都可以在设置面板中编辑。

每个阶段可以使用独立模型配置，例如：

- `default`
- `ideation`
- `critic`
- `report`

如果某阶段配置为：

```json
"max_tokens": null
```

IdeaLab 会在模型请求中省略 `max_tokens` 字段。

## REST API

主要接口：

- `GET /`：Web 应用
- `GET /api/health`：后端和 API key 状态
- `POST /api/runs`：创建新推演
- `GET /api/runs`：列出历史推演
- `GET /api/runs/{run_id}/graph`：读取推演图
- `POST /api/runs/{run_id}/human-input`：注入用户输入
- `POST /api/runs/{run_id}/stop`：停止推演
- `GET /api/runs/{run_id}/report`：读取最终报告
- `GET /api/config/models` / `PUT /api/config/models`
- `GET /api/config/prompts` / `PUT /api/config/prompts`
- `GET /api/config/api-keys` / `PUT /api/config/api-keys`

## 安全与隐私

- API key 保存在本地 `idealab_config/.env`。
- API key 不写入浏览器 localStorage。
- 每次推演的 workspace 保存在本地 `idealab_workspaces/`。
- 当前是单用户本地原型，不建议在没有鉴权、授权和沙箱机制的情况下暴露到公网。

## 当前限制

- 尚未接入沙箱代码执行模块。
- 尚未接入自动 benchmark runner。
- 尚无多用户登录和权限系统。
- 报告质量仍依赖模型能力和 prompt 设计。
- 文献检索目前主要依赖 Semantic Scholar，可能遗漏未收录或非论文来源。
- 证据可靠性评分仍较基础。

## 路线图

近期：

- 更强的输入分类与澄清机制；
- 更细的 evidence schema 和引用处理；
- 报告引用与证据节点绑定；
- idea 和报告质量评分；
- 更好的历史 run 对比和审查界面。

中期：

- 沙箱代码执行和最小验证实验；
- baseline 与 ablation runner；
- 失败样例回填推演图；
- 多模型交叉审查；
- 导出论文、review memo 和 PPT。

长期：

- 插件化工具层；
- 项目级 workspace；
- 基于 benchmark 的 idea 质量评估；
- 与自动实验系统集成。

## 许可证

尚未选择许可证。公开发布或接受外部贡献前，建议补充 LICENSE 文件。
