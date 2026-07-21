# loop-platform

> **一个开源、可 fork、可自托管的教学 + 交付平台**——带你从零理解并亲手跑通「自主交付流水线」背后的三层能力：**Harness（引擎）→ Loop（闭环）→ Graph（编排）**，最终把「一句话需求」变成「验收通过的可运行应用」。

我们对标的**不是** Cursor / Kiro 这类固定黑盒，而是**过程全透明、每一步可自己动手、可复现**的开源阶梯。

---

## 这个项目是什么

它有两个可以独立使用的面：

| 你是谁 | 你能拿它做什么 | 从哪进 |
|---|---|---|
| **学习者 / Workshop 学员** | 顺着 L0→L5 阶梯，亲手把「单次生成」一步步搭成「带门禁、能自愈、可编排」的自主系统；每一站都能独立跑、零密钥即可看到效果 | 读 [`LEARNING_PATH.md`](LEARNING_PATH.md) |
| **开发者 / 想自托管** | 把它当一条真实的交付流水线：自由文本 / 飞书需求 → LLM 生成 → 契约验收 → 推 GitHub → 部署服务器，可 fork 后按自己的领域改造 | 见下方「如何使用 · 生产模式」 |

核心信念：**绿灯 = 真达标**，不是"跑完了"。任何漂移都会在**确定性门禁**处被挡住。

---

## 目录结构

```
# —— 教学阶梯（读代码、动手跑，理解每层能力怎么长出来）——
langgraph-1/      从零学 Graph：单节点 → 分支 → 循环 → checkpoint → 带反馈 loop（step1~7）
harness/          Harness 一代：最小骨架（契约 → 生成 → 验收 → 重试）
harness-2/        二代：分层约束 / 测试 / 基线 / 确定性配置
harness-3/        三代：多用例 cases/ + 硬约束 + 生成前自洽性证伪
harness-5/        Loop 六级阶梯 L0→L5：裸跑 → 加 harness → 成环 → 护栏 → 确定性 → 上 LangGraph

# —— 生产引擎与流水线（真实交付时调用）——
harness-4/        契约驱动的确定性代码生成 + 验证引擎（当前引擎本体）
  ├─ cases/       各领域用例（spec 契约 + 样例数据 + case.json）
  ├─ tools/       compile_spec / verify / build_schema / run_model …
  ├─ studio/      配置控制台（Flask）
  └─ generate.sh  引擎入口（子进程调用）
delivery-loop/    编排层（Loop Engine）
  ├─ orchestrator.py  主循环：取需求 → 调引擎 → 发布 → 部署 → 回写
  ├─ publisher.py     发布到 GitHub
  ├─ deployer.py      拉取式部署到服务器（pty 驱动 ssh，零依赖）
  ├─ adapters/        需求来源（local / feishu）
  └─ deploy/          自托管资产（systemd / setup / sync）

LEARNING_PATH.md  学习地图（推荐第一份读的文档）
.env.example      密钥模板（复制为 .env 后填值；.env 永不提交）
```

---

## 如何使用

### 前置

```bash
python3 -m venv .venv && source .venv/bin/activate
cp .env.example .env          # 仅"真实 LLM / 推 GitHub / 飞书 / 部署"时才需要填
```

### A. 学习模式（零密钥，5 分钟看到门禁生效）

```bash
# 1) 把"自由文本 → spec 三件套 → 合规 case"跑通（内置 recipe 领域）
.venv/bin/python harness-4/tools/spec_compiler.py --name recipe --mock

# 2) 离线生成 + 验收（sample 模式，确定性参考实现，无需 API key）
HARNESS_MODE=sample HARNESS_CASES=recipe bash harness-4/generate.sh
#    观察验收输出出现：[OK] 渲染:页面含全部指定文案
```

**想验证门禁真的会拦？** 把某个 case 里 `must_contain_text` 要求的文案从模板删掉再验收，会看到 21/21 掉成 20/21 FAIL——这就是"绿灯=真达标"的证据。

想系统学，直接读 [`LEARNING_PATH.md`](LEARNING_PATH.md)：langgraph-1（Graph 基础）→ harness 四代演进 → harness-5 的 L0-L5 → delivery-loop。

### B. 生产模式（真实交付，需密钥）

```bash
# .env 填 DEEPSEEK_API_KEY 后，真实生成 + 发布 + 部署
HARNESS_MAX_TASKS=1 HARNESS_AUTOCOMMIT=1 bash delivery-loop/run_backlog.sh
```

全流程与自托管细节见 [`delivery-loop/docs/自主交付流水线-全流程与改进.md`](delivery-loop/docs/自主交付流水线-全流程与改进.md) 与 [`delivery-loop/deploy/OPS.md`](delivery-loop/deploy/OPS.md)。

---

## 设计原则

- **引擎黑盒**：`delivery-loop` 只通过命令行 + 退出码 + `output/runs.jsonl` 调 `harness-4`，不 import 其内部。
- **确定性验收**：每个产物过 20+ 项硬校验才发布，失败反馈重试；`temperature=0` + 固定 seed，可复跑比对。
- **密钥安全**：所有密钥仅存本机 `.env` / CI Secrets / 服务器环境变量，**绝不进仓**。

---

## 文档

- [学习地图 LEARNING_PATH.md](LEARNING_PATH.md) —— 建议第一份读
- [自主交付流水线-全流程与改进](delivery-loop/docs/自主交付流水线-全流程与改进.md)
- [Spec 编译层与动态模板方案](delivery-loop/docs/Spec编译层与动态模板方案.md)
- [GitHub 多仓发布方案](delivery-loop/docs/GitHub多仓发布方案.md)
