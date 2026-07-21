# 学习地图 · Harness + Loop + Graph

> 这个仓库不是又一个"帮你写代码的黑盒"，而是一条**可自己动手、可复现、过程全透明**的学习阶梯。
> 目标：让你从零理解并亲手跑通「**自主交付流水线**」背后的三层能力——
> **Harness（引擎）→ Loop（闭环）→ Graph（编排）**，最后合成一个能把「一句需求」变成「验收通过的可运行应用」的系统。
>
> 定位锚点：我们对标的**不是** Cursor/Kiro 这类固定黑盒，而是**开源、可配置、可 fork、可自托管**的教学 + 交付平台。

---

## 0. 一张图看懂全局

```
自由文本需求
  │  (LLM)         ← 唯一真正"不确定"的一步
  ▼
spec 三件套 (data-model / api-contract / ui-spec)
  │  (确定性派生)   compile_spec.py
  ▼
case.json（规格是编译产物，不手改）
  │  (LLM 或 离线参考) run_model.py = Maker
  ▼
可运行的 Flask 应用产物
  │  verify.py = Checker：20+ 门禁（含"渲染:页面含全部指定文案"）
  ▼
✅ 通过 →（可选）publisher.py 推 GitHub → deployer 部署
        ✗ 不通过 → 失败信息回喂，重试（这就是 Loop）
```

越往下越确定；任何漂移都会在**门禁**处被挡住。**绿灯 = 真达标**，不是"跑完了"。

对应的工程层级（Addy Osmani 的 Loop Engineering 体系，见 [`harness-4/对标与定位分析.md`](harness-4/对标与定位分析.md)）：

```
Loop Engineering        ← 设计自主系统(调度/验证/状态/护栏)      ← delivery-loop
Agent Harness Engineering ← 设计单个 agent 的运行环境           ← harness / harness-4
Context Engineering     ← 管理上下文
Prompt Engineering      ← 优化单轮指令
```

---

## 1. 推荐学习顺序（每一站都能独立跑）

| 站 | 目录 | 你会学到 | 先决条件 |
|---|---|---|---|
| **① 概念地基** | [`harness-4/对标与定位分析.md`](harness-4/对标与定位分析.md) | 四层体系、spec 驱动 / 门禁 / loop 三根支柱、我们的差异点（确定性验收） | 只读，10 分钟 |
| **② Graph 基础** | [`langgraph-1/`](langgraph-1/) | 状态图从单节点 → 分支 → 循环 → checkpoint → 真实 Maker/Checker → 带反馈 loop | Python |
| **③ Harness 演进** | `harness/` → [`harness-2/`](harness-2/) → [`harness-3/`](harness-3/) → [`harness-4/`](harness-4/) | 一个"一次性生成脚本"如何长成"spec 驱动 + 门禁 + 确定性"的引擎 | Python |
| **④ Loop 阶梯** | [`harness-5/`](harness-5/) | L0→L5 六级递进：裸跑 → 加 harness → 成环 → 加护栏 → 确定性 → 上 LangGraph | 建议先过 ②③ |
| **⑤ 交付流水线** | [`delivery-loop/`](delivery-loop/) + [`harness-4/studio/`](harness-4/studio/) | 需求源 adapter → 编排 → 发布 → 部署；Studio 控制台 | 建议最后 |

> 只想最快看到"闭环 + 门禁"效果？直接跳到 **第 4 节 Quick Start**（零密钥）。

---

## 2. 逐站详解

### ② Graph 基础 —— `langgraph-1/`

从零手写 LangGraph，每步一个 `main.py`，配 `README.md`：

| 步骤 | 主题 |
|---|---|
| `step1_single_node` | 单节点图：理解 State / Node / 编译执行 |
| `step2_two_nodes` | 两节点串联：状态在节点间流动 |
| `step3_branch` | 条件分支：根据状态选择下一步 |
| `step4_loop` | 循环：回边 + 退出条件 |
| `step5_checkpoint` | 检查点：状态持久化 / 可恢复 |
| `step6_real_makercheck` | 真实 Maker/Checker：生成→检查两节点 |
| `step7_loop_feedback` | 带反馈的循环：检查失败把信息回喂重生成 |

跑法：`cd langgraph-1/step1_single_node && python main.py`（逐步往后）。

### ③ Harness 演进 —— `harness/` → `harness-4/`

一条"同一个东西越做越严谨"的时间线，建议对照各代 `README.md` / `VERSION` 看**为什么改**：

- **`harness/`（gen1）**：最小骨架——`spec/` + `rules/` + `prompt.md` + `run_model.py`（Maker）+ `verify.py`（Checker）+ `generate.sh`。理解"契约 → 生成 → 校验"。
- **`harness-2/`**：引入 `baseline/`、`rules/base` 与 `rules/task` 分层、`config.env`、`setup.sh`。工程化起步。
- **`harness-3/`**：引入 `cases/`（blog/ecommerce 多用例）、`constraints.json`（硬约束）、`check_consistency.py`（**生成前**自洽性证伪）、`gate.sh`、CI。
- **`harness-4/`（当前引擎）**：加 `schemas/`、`tools/`（`compile_spec.py` 确定性编译、`spec_compiler.py` LLM 编译、`sample_generator.py` 离线参考、`verify.py` 门禁）、`studio/`（Flask 控制台）。这是流水线真正调用的引擎。

**看点**：`harness-4/tools/verify.py` 里的 `渲染:页面含全部指定文案` 门禁——它校验需求原文要求的字面文案（如"页面须显示 Loop-20260721"）真的出现在渲染页，是"绿灯=真达标"的关键一环。

### ④ Loop 阶梯 —— `harness-5/`

把 Loop 拆成**六级可运行的递进**，每级一个目录 + `README.md`，另配 `洗车间比喻.md` 帮助建立直觉：

| 级 | 目录 | 新增的原语 |
|---|---|---|
| L0 | `l0_single` | 单次生成，无验证 |
| L1 | `l1_harness` | 加 harness：把生成放进受控环境 + 门禁 |
| L2 | `l2_loop` | 成环：失败重试 |
| L3 | `l3_guardrails` | 护栏：迭代上限 / diff / 成本上限 |
| L4 | `l4_determinism` | 确定性：temperature=0 + seed + 哈希复跑比对 |
| L5 | `l5_langgraph` | 用 LangGraph 重写这个 loop |

跑法：`cd harness-5 && bash run_all.sh`（或进各级目录单独跑 `run.py`）。

### ⑤ 交付流水线 —— `delivery-loop/`

把引擎接上"真实世界"：

- `adapters/`：需求源（`feishu_adapter.py` 飞书 / `local_adapter.py` 本地），统一 `base.py`。
- `orchestrator.py`：编排主循环（发现待办 → 编译 → 生成 → 验收 → 发布 → 部署）。
- `publisher.py`：把验收通过的产物推到 GitHub 样例仓（`sample1/ sample2/ ...`）。
- `deployer.py`：部署到服务器。
- `studio/server.py`：控制台后端（Flask）。
- `deploy/`：自托管资产（systemd service、`setup_ecs.sh`、`sync_to_ecs.py`）。

---

## 3. 环境准备

```bash
python3 -m venv .venv && source .venv/bin/activate
# 各阶梯的依赖很轻；langgraph 步骤见 langgraph-1/step5/requirements 或 harness-5/l5_langgraph/requirements.txt
cp .env.example .env          # 只有需要"真实 LLM / 推 GitHub / 飞书 / 部署"时才需填
```

- **纯学习、看闭环**：不需要任何密钥（用 sample 离线模式）。
- **真实生成**：`.env` 填 `DEEPSEEK_API_KEY`。
- **推 GitHub / 飞书 / 部署**：按 `.env.example` 各段补齐（详见 [`README.md`](README.md) 与 [`delivery-loop/deploy/OPS.md`](delivery-loop/deploy/OPS.md)）。

---

## 4. Quick Start（零密钥，5 分钟看到门禁生效）

```bash
# 1) 用内置 recipe 领域把"自由文本 → spec 三件套 → 合规 case"跑通(内置了 must_contain_text 行)
.venv/bin/python harness-4/tools/spec_compiler.py --name recipe --mock

# 2) 离线生成 + 验收(sample 模式走确定性参考实现，无需 API key)
HARNESS_MODE=sample HARNESS_CASES=recipe bash harness-4/generate.sh
#    观察验收输出里出现:  [OK] 渲染:页面含全部指定文案
```

**反向验证门禁真的会拦**：把某个 case 里 `must_contain_text` 要求的文案从产物模板里删掉再验收，会看到 21/21 掉成 20/21 FAIL（缺文案）——这就是"绿灯=真达标"的证据。

---

## 5. 常见问题

- **为什么生成出来总是"列表 + 详情"两页？**
  这是 harness-4 的**刻意设定**：它本质是一个「列表+详情内容站生成器」，被做窄才能确定性验收。要支持"单页交互应用/看板"等其他形态，需要在 `spec_compiler` 的 prompt 里新增 archetype，并配套 `verify` 分支——这是进阶练习。
- **sample 和 real 模式差别？**
  `sample`=离线确定性参考实现（零密钥，用于跑通闭环与自证）；`real`=调用 DeepSeek 真实生成（需 `DEEPSEEK_API_KEY`）。
- **确定性怎么体现？**
  `temperature=0` + 固定 seed + 复跑产物哈希/字节比对；把"可复现"像 lint/test 一样纳入门禁。

---

> 更完整的动手细节见 workspace 里的 `doc/自己跑一遍-实操指南.md`（若一并分发）。
> 本仓库定位：**学习 Harness+Loop+Graph 的开源阶梯 + 可 fork 的自主交付流水线**。
