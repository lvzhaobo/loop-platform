# langgraph-1 · 从零逐步学 LangGraph

用**最小可运行的例子**一步步把 LangGraph 讲清楚。每个 step 是一个独立文件夹，内含 `main.py` + 自己的 `README.md`，后一步只比前一步多引入**一个**新概念。

> 每个 step 的详细说明在各自文件夹的 `README.md`；本文件只做总览与导航。

## 运行任意一步

```bash
source .venv/bin/activate                       # 必须：langgraph 只装在这个 venv
python langgraph-1/<step 文件夹>/main.py
```

## 学习路线

### 第一部分：LangGraph 原语（玩具 state，零负担）✅ 已完成

| 步骤 | 文件夹 | 新引入的概念 | 一句话 |
|---|---|---|---|
| step1 | `step1_single_node/` | State / Node / START·END / compile / invoke | 最小图：一个节点把状态改一下 |
| step2 | `step2_two_nodes/` | 顺序边(链式) | 两个节点串起来跑 |
| step3 | `step3_branch/` | 条件边(分支) | 检查 → 路由 → 通过/打回 |
| step4 | `step4_loop/` | 回边(循环) | 把"打回"那条边指回上游 = 循环 |
| step5 | `step5_checkpoint/` | Checkpointer(可恢复/可观测) | 每一步落检查点 |
| _debug_ | `step_debug/` | 检查机制 | 故意写乱，看它在哪报错 |

### 第二部分：从玩具 → 真实场景（复用 harness 的 Maker/Checker 写代码循环）

| 步骤 | 文件夹 | 从玩具→真实的关键一跃 | 状态 |
|---|---|---|---|
| step6 | `step6_real_makercheck/` | 节点里改调 `lib/model.generate` / `lib/gates.verify`，跑 mathkit（单次） | ✅ 已完成 |
| step7 | `step7_loop_feedback/` | 条件边=收敛判据+回喂：验收失败→回喂→重生成，2 轮收敛 | ✅ 已完成 |
| step8 | — | 护栏：迭代上限 / 花费上限 / 卡死检测 | 待做 |
| step9 | — | **接入 LangGraph Studio**：图形化看图 + 逐节点 state + 时间旅行 | 待做 |
| step10 | — | 切电商 mall + 工业化：SqliteSaver 断点续跑 + 人审介入 | 待做 |

> **LangGraph Studio 为什么放 step9？** 它的杀手锏（逐节点看 state、时间旅行）正是 step5 检查点数据的可视化；而在 step7 真实 loop 成型、能看到"第1轮失败→回喂→第2轮通过"之后接入，才有值得看的动态。前提两件：一个 `langgraph.json` + 检查点（step5 已具备）。

## 依赖与环境

- langgraph 装在仓库根 `.venv`（Python 3.14）。运行前 `source .venv/bin/activate`。
- 编辑器报错（无法解析 langgraph、类型未知等）已由仓库根 `pyrightconfig.json` 修复；若仍显示，`Reload Window` 让语言服务器重载即可。
- step6 起复用 `harness-5/lib`（Maker/Checker）与 `harness-5/spec`（任务规格），默认 `HARNESS_MODE=sample` 离线运行。
