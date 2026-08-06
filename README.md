# Loop — 自主交付应用平台

从一句话需求到可运行应用的全自动交付流水线。支持多 AI Maker（DeepSeek / Claude / Qoder），内置 Better Harness 质量诊断。

## 一句话理解

> 告诉它"做一个招聘职位列表页"，它自动生成代码、自动验收、出来的就是一个能跑的应用。
>
> Better Harness 再对产出的代码做一次深度诊断：安全性、可维护性、可观测性… 出评分 + 问题清单。

## 架构

```
需求输入                 编排层                      引擎
───────────────────    ───────────────────────    ─────────────────
飞书文档 / 直接输入  →  orchestrator.py         →  generate.py
                        │                           ├─ Maker (多 AI)
                        │                           │   ├─ DeepSeek API
                        │                           │   ├─ Claude CLI
                        │                           │   └─ Qoder CLI
                        │                           ├─ Checker (20+ 硬验收)
                        │                           └─ spec_compiler
                        │
                        ├─ publisher.py   →  GitHub
                        ├─ deployer.py    →  ECS
                        └─ Better Harness  →  质量诊断报告
```

三层边界：

| 层 | 目录 | 职责 |
|---|---|---|
| 引擎 | `engine/` | 契约驱动的确定性代码生成 + 硬验证闭环 |
| 编排 | `pipeline/` | 需求池管理、调度引擎、发布、部署 |
| 配置 | `studio/` | Web 面板（需求管理、约束编辑、一键交付） |

**编排层不 import 引擎代码**，只通过子进程 + 退出码 + `runs.jsonl` 交互。引擎可独立跑，编排层可换引擎。

## 目录结构

```
engine/              # 生成引擎
│   ├── generate.py      #   多用例生成+验证闭环
│   ├── gate.py          #   CI 门禁（自洽→派生→全用例）
│   ├── prompt.md        #   系统提示（场景中立）
│   ├── rules/           #   规则（通用基座 + 任务约束）
│   ├── tools/           #   生成器 / 验证器 / spec 编译器
│   └── makers/          #   多 AI Maker（DeepSeek/Claude/Qoder/Copilot）
│
pipeline/            # 编排 + 交付
│   ├── orchestrator.py  #   主循环（取任务→调引擎→回写）
│   ├── publisher.py     #   发布到 GitHub
│   ├── deployer.py      #   部署到 ECS
│   ├── run.py           #   唯一入口
│   ├── adapters/        #   需求来源适配器（飞书/直接文本）
│   ├── trigger/         #   自动触发器（webhook / 轮询）
│   └── deploy/          #   部署基础设施
│
studio/              # Web 配置面板
│   ├── server.py        #   Flask 后端（16 个 API）
│   ├── templates/       #   前端 SPA + 登录页
│   └── static/          #   CSS / JS
│
cases/               # 所有用例（唯一事实源）
data/                # 需求池数据
│   ├── backlog.json     #   需求池
│   ├── state.json      #   任务状态
│   └── specs/          #   原始需求存档
config.env           # 一份统一配置
setup.py             # 环境初始化

output/                  # 产物
```

## 快速开始

```bash
# 1. 环境准备
python setup.py
source .venv/bin/activate

# 2. 配置 API Key（仓库根 .env）
echo 'export DEEPSEEK_API_KEY="sk-xxx"' > .env

# 3. 启动配置面板
python studio/server.py
# 打开 http://127.0.0.1:5100

# 4. 添加需求 → 点"开始交付"

# 或命令行直接跑：
source .env && python pipeline/run.py
```

## 工作流程

```
输入需求（飞书文档 / 直接输入文字）
  ↓
spec_compiler 编译为结构化契约（spec.md + manifest.json + acceptance.json）
  ↓
run_model.py 调用 LLM 生成代码（DeepSeek, temp=0, seed=42）
  ↓
verify.py 执行硬验收：
  ├─ 结构校验（必备文件齐全）
  ├─ 依赖扫描（禁 django/react/jQuery）
  ├─ 安全扫描（禁 eval/os.system）
  ├─ 数据校验（字段、类型、条数、field_rules）
  ├─ CSS 校验（配色、布局）
  ├─ 单元测试（unittest 全绿）
  ├─ 运行时（真起 Flask + 探活）
  └─ 渲染（真浏览器验证 DOM 结构）
  ↓
失败 → 反馈重试（最多 5 轮）
  ↓
通过 → 确定性复跑（两次生成比对哈希）
  ↓
可选：发布 GitHub → 部署 ECS
```

## 两种用例形态

| 形态 | 事实源 | 适用场景 | 验收方式 |
|---|---|---|---|
| Catalog | `cases/<name>/case.json` | 列表+详情站（电商/博客/课程） | 20 项固定门禁 |
| Spec | `cases/<name>/spec/manifest.json` | 任意交互工具（番茄钟/招聘页/仪表盘） | 自动验收 TC/AC |

## 核心设计原则

- **确定性**：temp=0 + seed=42，生成两次比哈希，不一致也须过验收
- **契约驱动**：生成和验证同一份事实源，不漂移
- **可执行验收**：不靠人工"看对不对"，真起 Flask、真打路由、真跑 unittest
- **黑盒解耦**：编排层不 import 引擎，引擎可独立跑 `gate.sh`
- **多 Maker 可插拔**：同一套 Checker 体系不动，Maker 随意换（API 型 DeepSeek / CLI 型 Claude + Qoder）
- **零密钥自测**：`HARNESS_MODE=sample` 离线模式，无需 API Key 即可跑通

## Better Harness 质量诊断

Loop 集成了 Better Harness 流程质量诊断 —— 对生成的代码做**第二层深度诊断**，补充硬验收覆盖不到的维度：

| 维度 | 检查什么 | 硬验收做不到的 |
|---|---|---|
| 任务理解 | 生成的代码是否真正解决了需求 | 硬验收只查字段/文件存在性 |
| 可控执行 | 代码运行行为是否可预测 | 硬验收只查一进一出 |
| 变更验证 | 修改后是否有回归风险 | 硬验收无增量对比 |
| 可靠交付 | 是否有生产隐患 | 硬验收不查部署/日志/监控 |
| 学习捕获 | 是否有可复用的模式 | 纯工具不感知 |

**调用方式**：通过 Qoder CLI 子进程运行 `/better-harness` 技能，产物写入生成目录。

```bash
# CLI 直接调用
qodercli -w output/maker-xxx /better-harness

# Studio Web 面板中一键触发
# → 生成历史 → 点击"🔬 分析"按钮
```

Better Harness 需要 Qoder Desktop（提供 qodercli）。[安装指南 →](#开发环境)

## 多 Maker 架构

Loop 支持多种 AI 代码生成器（Maker），**同一套 Checker 验收体系，Maker 随意换**：

| Maker | 类型 | Session | 适用场景 | 接入方式 |
|---|---|---|---|---|
| **DeepSeek** | API 型 | ❌ 无状态 | 快速批量生成、CI/CD | `DEEPSEEK_API_KEY` 环境变量 |
| **Claude Code** | CLI 型 | ✅ 有 Session | 复杂交互式生成 | `claude` CLI（需安装） |
| **Qoder CLI** | CLI 型 | ✅ 有 Session | 原生集成 Better Harness | `qodercli`（需 Qoder Desktop） |
| **Copilot** | CLI 型 | ✅ 有 Session | GitHub 生态 | `copilot-cli`（需安装） |

**API 型 vs CLI 型的核心差异**：
- API 型：HTTP 一发一收，无对话历史，纯靠 prompt 质量
- CLI 型：Agent 持续交互读写文件，Session 记录留在生成目录，**Better Harness 可分析 Agent 行为链路**

切换 Maker：
```bash
export HARNESS_MAKER=qoder       # deepseek | claude | qoder | copilot
# 或在 Studio → 设置 → Maker 下拉选择
```

## 配置

所有配置在 `config.env`，可被环境变量覆盖：

| 变量 | 默认 | 说明 |
|---|---|---|
| `HARNESS_MODE` | `real` | real=DeepSeek / sample=离线 |
| `HARNESS_MAKER` | `deepseek` | deepseek / claude / qoder / copilot |
| `HARNESS_AUTOCOMMIT` | `0` | 1=产物通过后推 GitHub |
| `HARNESS_GIT_REMOTE` | — | 目标仓库 |
| `ECS_DEPLOY` | `0` | 1=推送后部署到 ECS |
| `HARNESS_DET_CHECK` | `1` | 1=通过后复跑比对 |
| `HARNESS_MAX_TASKS` | `0` | 单批最大处理数 |

密钥（`DEEPSEEK_API_KEY`、`FEISHU_APP_ID` 等）统一放仓库根 `.env`（已 gitignore）。

## ECS 部署（含 CLI 工具安装）

`pipeline/deploy/setup_ecs.sh` 负责在 ECS 上一键部署。默认只装 Python + Git + Flask。

**如需在 ECS 上使用 CLI 型 Maker 或 Better Harness**，需额外安装对应工具：

```bash
# Qoder CLI（Better Harness 依赖）
# 从 Qoder Desktop 提取 qodercli 二进制，上传到 ECS /usr/local/bin/
# 或等官方提供 Linux 安装脚本后：
# curl -fsSL https://qoder.dev/install.sh | bash

# Claude Code CLI
npm install -g @anthropic-ai/claude-code

# 验证
qodercli --version
claude --version
```

ECS 上各功能对应的工具依赖：

| 功能 | 需要 | ECS 默认有？ |
|---|---|---|
| DeepSeek API 生成 | `DEEPSEEK_API_KEY` | ✅ 开箱可用 |
| Qoder CLI 生成 | `qodercli` | ❌ 需手动装 |
| Claude CLI 生成 | `claude` | ❌ 需手动装 |
| Better Harness 诊断 | `qodercli` | ❌ 需手动装 |
