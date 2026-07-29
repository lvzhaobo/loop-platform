# Loop — 自主交付应用平台

从一句话需求到可运行应用的全自动交付流水线。

## 一句话理解

> 告诉它"做一个招聘职位列表页"，它自动生成代码、自动验收、出来的就是一个能跑的应用。

## 架构

```
需求输入                 编排层                      引擎
───────────────────    ───────────────────────    ─────────────────
飞书文档 / 直接输入  →  orchestrator.py         →  generate.sh
                        │                           ├─ run_model.py   (LLM 生成)
                        │                           ├─ verify.py      (20 项硬验收)
                        │                           └─ spec_compiler  (自由文本→结构化契约)
                        │
                        ├─ publisher.py   →  GitHub
                        └─ deployer.py    →  ECS
```

三层边界：

| 层 | 目录 | 职责 |
|---|---|---|
| 引擎 | `loop/engine/` | 契约驱动的确定性代码生成 + 硬验证闭环 |
| 编排 | `loop/pipeline/` | 需求池管理、调度引擎、发布、部署 |
| 配置 | `loop/studio/` | Web 面板（需求管理、约束编辑、一键交付） |

**编排层不 import 引擎代码**，只通过子进程 + 退出码 + `runs.jsonl` 交互。引擎可独立跑，编排层可换引擎。

## 目录结构

```
loop/
├── engine/              # 生成引擎
│   ├── generate.sh      #   多用例生成+验证闭环
│   ├── gate.sh          #   CI 门禁（自洽→派生→全用例）
│   ├── constraints.json #   全局硬约束
│   ├── prompt.md        #   系统提示（场景中立）
│   ├── rules/           #   规则（通用基座 + 任务约束）
│   └── tools/           #   生成器 / 验证器 / spec 编译器
│
├── pipeline/            # 编排 + 交付
│   ├── orchestrator.py  #   主循环（取任务→调引擎→回写）
│   ├── publisher.py     #   发布到 GitHub
│   ├── deployer.py      #   部署到 ECS
│   ├── run.sh           #   唯一入口
│   ├── adapters/        #   需求来源适配器（飞书/直接文本）
│   ├── trigger/         #   自动触发器（webhook / 轮询）
│   └── deploy/          #   部署基础设施
│
├── studio/              # Web 配置面板
│   ├── server.py        #   Flask 后端（16 个 API）
│   ├── templates/       #   前端 SPA + 登录页
│   └── static/          #   CSS / JS
│
├── cases/               # 所有用例（唯一事实源）
├── backlog/              # 需求池数据
├── specs/               # 原始需求存档
├── config.env           # 一份统一配置
└── setup.sh             # 环境初始化

output/                  # 产物
```

## 快速开始

```bash
# 1. 环境准备
bash loop/setup.sh
source .venv/bin/activate

# 2. 配置 API Key（仓库根 .env）
echo 'export DEEPSEEK_API_KEY="sk-xxx"' > .env

# 3. 启动配置面板
python loop/studio/server.py
# 打开 http://127.0.0.1:5100

# 4. 添加需求 → 点"开始交付"

# 或命令行直接跑：
source .env && bash loop/pipeline/run.sh
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
- **零密钥自测**：`HARNESS_MODE=sample` 离线模式，无需 API Key 即可跑通

## 配置

所有配置在 `loop/config.env`，可被环境变量覆盖：

| 变量 | 默认 | 说明 |
|---|---|---|
| `HARNESS_MODE` | `real` | real=DeepSeek / sample=离线 |
| `HARNESS_AUTOCOMMIT` | `0` | 1=产物通过后推 GitHub |
| `HARNESS_GIT_REMOTE` | — | 目标仓库 |
| `ECS_DEPLOY` | `0` | 1=推送后部署到 ECS |
| `HARNESS_DET_CHECK` | `1` | 1=通过后复跑比对 |
| `HARNESS_MAX_TASKS` | `0` | 单批最大处理数 |

密钥（`DEEPSEEK_API_KEY`、`FEISHU_APP_ID` 等）统一放仓库根 `.env`（已 gitignore）。
