# Workshop 课件结构 · 手把手搭 Harness 与 Loop

> 时长建议 90–120 分钟。每章 = 一段讲解(为什么)+ 一次现场手搭/跑(怎么做)+ 一个"暴露问题"引出下一章。
> 全程用 `HARNESS_MODE=sample` 离线跑,不依赖网络/额度;有 key 可切 `real` 演示真实模型。

## 开场(10 min):为什么要自己搭
- 现成产品的两难:**越开箱即用越黑盒,越可控越要自己搭**。
- Kiro(闭源黑盒)/ Spec Kit(重框架)都不适合"教原理"。
- 引出体系:Prompt → Context → **Harness → Loop**(Addy Osmani, Loop Engineering)。

## 第 1 章 · L0 单次调用(15 min)
- 讲:最朴素的生成 = 拼提示词 → 调模型 → 落盘。
- 手搭:`l0_single/run.py`(20 行)。
- 跑:`python3 harness-5/l0_single/run.py`,打开产物。
- 暴露问题:**对不对没人知道**(sample 下 factorial 是错的)。→ 需要验收。

## 第 2 章 · L1 Harness(20 min)
- 讲:Harness = 给生成套可控环境。三关**从便宜到贵**:自洽性 → 生成 → 验收。
- 手搭:`constraints.json`(宪法)、`lib/gates.py`(consistency + verify)、`gate.py`。
- 跑:`python3 harness-5/l1_harness/gate.py`,看门禁**抓出** factorial 的 bug(退出码 1)。
- 暴露问题:**只发现,不修复**。→ 需要闭环。

## 第 3 章 · L2 Loop(20 min)
- 讲:Maker/Checker 分离;失败报告回喂;**可验证的停止条件**(验收全绿,而非"模型说完了")。
- 手搭:`l2_loop/loop.py`(`while not ok: 生成→验收→回喂`)+ `state.json`。
- 跑:第 1 轮失败 → 回喂 → 第 2 轮修好。看 `state.json`。
- 暴露问题:**裸循环没刹车**,真实模型可能无限烧钱。→ 需要护栏。

## 第 4 章 · L3 护栏(20 min)
- 讲:三护栏 = 迭代上限 / 花费上限 / 卡死检测(diff)。引斯坦福"token 差 30 倍"。
- 手搭:`constraints.json` 加 `loop` 段;`loop_guarded.py` 三处 `if...break` + sha256 diff。
- 跑:正常路径(第 2 轮通过);`HARNESS_SAMPLE_STUCK=1` 演示**卡死检测秒停**。
- 暴露问题:**同样输入重跑一样吗?** → 需要确定性。

## 第 5 章 · L4 确定性(15 min)
- 讲:可复现是最硬的验收;temp0+seed;哈希基线;这是主流产品普遍不做的差异点。
- 手搭:`determinism.py`(跑两遍 → 比对哈希)+ `runs.jsonl`。
- 跑:两次 sha256 一致 → 确定性通过。

## 收尾(10 min):把玩与延伸
- **现场改给学员看**(体现"可控"):
  - 改 `spec/facts.json` 加一个函数 → 自洽性门禁立刻报错(facts 与 spec 漂移)。
  - 改 `constraints.json` 的 `max_lines=10` → 行数关卡触发。
  - 改 `loop.max_iterations=1` → 循环第 1 轮就被迭代上限拦下。
- 延伸讨论:换更复杂的 task(如 harness-4 的 Flask 应用)、接 CI、多用例矩阵。
- 一句话总结:**Harness 管"一次生成可控",Loop 管"多次收敛可控",确定性管"结果可信"。**

## 讲师备忘
- 每章的"暴露问题 → 下一章"是主线,别跳。
- sample 的"先错后对"是刻意设计的教具(`lib/model.py`),讲清楚它不是真模型。
- 出错先查:是否在仓库根目录运行、`python3` 是否可用、`output/` 是否可写。
