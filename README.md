# Loop — Agentic Work Delivery Platform

> **从自然语言需求到可信软件交付。** Loop 将任务合同、受控执行、确定性检查、不可变证据与交付连接在一起，让 AI 生成的结果能够被验证、回放与审查。

[What it is](#what-it-is) · [远景与共同语言](#vision-and-shared-language) · [架构](#architecture) · [快速开始](#quick-start) · [当前状态](#current-status)

## What it is

Loop 是一个面向 AI 软件交付的**契约驱动、可组合、可验证、可回放**平台。它不把“模型产出代码”当作完成，而是将每一次工作组织为：

```text
Task → Spec / Acceptance / Policy → Immutable Run Plan → Maker / Runtime
     → Candidate Artifact → Checker → Approval / Delivery → Event + Evidence
```

它适合作为 AI Coding、Agent Engineering、Hands-on Lab 与企业交付 Workshop 的参考实现：不同模型、Agent Runtime、Skill、Tool 和交付物可以替换，但任务合同、质量门禁和证据语义保持一致。

## Vision and shared language

Loop 的长期愿景是成为企业 AI 工作系统中的**可信交付与协同核心**：让业务任务不止停留在模型回答、低代码 Demo 或一次性的脚本执行，而是可以被清楚委托、受控执行、验证修复、人工批准并留下可回放证据的工作成果。

它服务于一组相互协同的平台与场景，而非孤立工具：

```text
行业业务场景 Sample                 制造 · 经营分析 · 知识助手 · 研发交付
        ↕
Agent Runtime / Workbench            Dify · EPAI · 百炼 · LangGraph · BAT Work
        ↕
Agentic Work Delivery Platform        Task Contract · Checker · Evidence · Delivery
        ↕
AI Coding 工作台与工程能力             Kiro · Qoder · Coding Agent · Harness · Tests
```

### One language across platforms

无论使用低代码平台、LangGraph、AI Coding 工具还是行业业务系统，都可用同一套语言讨论一项 AI 工作：

| Concept | Meaning |
|---|---|
| **Task** | 业务目标与预期结果。 |
| **Contract** | 范围、验收、权限、风险、预算与完成定义。 |
| **Context** | 本次任务的输入、环境、限制与当前状态。 |
| **Knowledge** | 有来源、版本、适用范围的领域规则、事实与资料。 |
| **Agent** | 负责推理、决策或执行协调的角色。 |
| **Workflow** | 步骤、分支、状态流转与人机协作。 |
| **Capability** | Skill、Tool、MCP、API 与 Connector 等可调用动作。 |
| **State** | 会话、任务和历史决策的运行状态与 Memory。 |
| **Result** | 代码、报告、图表、PPT、API、工单或业务动作。 |
| **Assurance** | Check、Eval、审批、Evidence、审计与交付。 |

反馈、失败案例、高成本成功路径、人工评审和客户使用反馈会持续更新知识、流程、Lab 与场景。Memory 用于协作延续；Evidence 用于证明某一次结果为何可以交付。

### Three capability tracks

| Track | Focus | Typical practices |
|---|---|---|
| **AI Agent Engineering** | 构建 Agent 系统与运行机制 | Dify/扣子/EPAI/百炼、LangChain/LangGraph、AgentScope、多 Agent、Skill、Tool、MCP、Memory、Runtime。 |
| **AI Builder** | 将业务和客户场景构建为可用、可验证、可复制的方案 | 场景发现、任务设计、知识与流程、低代码构建、试点、验收与交付。 |
| **AI Coding Transformation** | 用 AI 变革研发的上下文、开发、质量与交付 | Kiro、Qoder、Coding Agent、知识工程、Harness、测试、Checker 与 Evidence。 |

这三条主线可按客户角色和场景组合：业务、管理、产品、数据、合作伙伴、Agent 工程、研发和治理团队在同一张任务语言与能力地图中协作。

## Why Loop

- **合同先于执行**：Profile、Spec、AC/TC、权限、预算和副作用范围在 Run 前冻结。
- **验证先于交付**：确定性 Checker 负责放行；LLM Review 只能提供语义建议，不能替代最终门禁。
- **Evidence 不等于 Memory**：Memory 用于执行协作；Event、制品和 SHA-256 Evidence 用于证明本次 Run 的结论。
- **执行者可替换**：DeepSeek、Coding Agent、LangGraph、BAT Work 或确定性 Worker 都可以通过明确合同接入。
- **不同交付物，不同验收**：网页、代码、报告、数据分析、PPT、API 与企业自动化不共享一套虚假的通用验收规则。

## Architecture

| 平面 | 主要职责 | 当前对应能力 |
|---|---|---|
| Control Plane | 决定什么可做、何时通过、向哪里交付 | Profile、Run Plan、Policy、Checker、Evidence、Delivery |
| Execution Plane | 决定如何完成任务 | Compiler、Maker、Agent/Skill/Tool、Workspace |
| Experience Plane | 让用户审阅、确认和追踪任务 | Vue Studio：Intake、Plan、Confirm、Run Detail |

```text
Vue Studio / API → Task Intake → Profile + Plan Review → Explicit Confirm
                → Compiler → Maker → Checker → Delivery
                → append-only Events + immutable Evidence → Replay / Observability
```

## Current status

| Capability | Status | Notes |
|---|---|---|
| Profile validation + immutable Run Plan | ✅ Core | Confirm 必须携带同一份 `plan_id + plan_digest`。 |
| Event, Evidence and Replay | ✅ Core | 每个 Run 有 append-only JSONL、digest 绑定的证据与回放校验。 |
| Vue Studio | 🟡 Ready for browser acceptance | 正式入口为 `/studio-vue/`；仍需持续完成浏览器主链 smoke。 |
| `deepseek-local` | 🟡 Connected | 真实模型、Security/Pages Checker 和本地制品路径已经接线。 |
| GitHub delivery | 🟡 Controlled push | Git push 与 Workflow/ECS 成功被严格区分；状态回读尚未实现。 |
| Project revisions / change requests / attempt repair | ⏳ Planned | 当前执行单位仍是单条需求对应的独立 Run。 |
| Better Harness | ⏳ Advisory integration | 未来作为 Run 绑定的 Evidence Adapter，不替代硬验收。 |

状态表只描述当前高层实现情况；每一次运行的可信结论仍以冻结 Plan、RunEvent、Evidence 和实际制品为准。

## Quick start

**Prerequisites:** Python 3.11+、Node.js 20+；如需真实模型 Run，还需要 DeepSeek API Key。以下命令适用于 macOS/Linux。

```bash
# 1. Create a Python environment and install the current server dependency
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install "Flask==3.0.*"

# 2. Build the formal Vue Studio
cd studio/web
npm install
npm run build
cd ../..

# 3. Optional: enable the real local-generation Profile
printf 'DEEPSEEK_API_KEY="your-key"\n' > .env

# 4. Start the server, then open http://127.0.0.1:5100/studio-vue/
.venv/bin/python studio/server.py
```

For frontend development, run `npm run dev` inside `studio/web/` in a second terminal; Vite listens on port `5175`. Browser clients never receive model, Git, or deployment credentials.

## Profiles and safety boundaries

| Profile | Intended use | Allowed effects |
|---|---|---|
| `fixture-local` | Offline regression and CI reference path | Local Plan, artifact, Event and Evidence only |
| `deepseek-local` | Default user requirement → local artifact path | Model call, deterministic checks, local artifacts |
| `deepseek-github` | Explicitly confirmed GitHub delivery | Model call, checks, fixed-target Git push |

A profile is not UI metadata: the server resolves it again at execution time. Local generation does not push, publish, or deploy. GitHub delivery does not claim Workflow or ECS success without independent readback evidence.

## Verification

```bash
.venv/bin/python -m unittest discover -s tests -v
cd studio/web && npm run build
```

A real model run has cost; a GitHub run has external side effects. Review the Profile, Plan and permissions before confirming either action.

## Repository map

```text
engine/          contracts, Profile execution, Compiler/Maker/Checker registry
studio/          Flask API and formal Vue Studio
profiles/        versioned execution-profile definitions
pipeline/        delivery adapters and GitHub workflow integration
data/            Run Plans, append-only events and immutable evidence
adapters/        integration boundaries and compatibility adapters
docs/            authoritative development entry, architecture and workshop materials
```

## Reference scope

This repository is both an evolving engineering reference and a Workshop/Lab reference. Its core demonstrations cover: task contracts and executable acceptance; AI Coding and knowledge engineering; Agent Runtime and tool orchestration; quality checks, evidence and controlled delivery; and industry Samples such as manufacturing, data analysis, enterprise knowledge and software-change delivery.

## License and contribution

Before contributing, preserve the Profile → Plan → Checker → Evidence boundaries, stage only the intended files, and validate changes with the most relevant test or build command. Historical output and Markdown claims must not be treated as current runtime truth.
