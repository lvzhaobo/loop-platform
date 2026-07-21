# harness-5 · 手把手搭 Harness 与 Loop(Workshop 教学版)

> 这是一套**为教学而生**的最小实现:从"裸调模型"一层层搭到"可控、会自愈、不失控、可复现"的闭环。
> 每一层都是**独立、几十行、能当场改**的组件——不是黑盒产品,是让你看清原理、亲手改的骨架。

## 为什么不直接用现成产品

| 产品 | 能一行行改吗 | 适合"教怎么搭"吗 |
|---|---|---|
| Kiro | ❌ 闭源黑盒 | ❌ 只看到结果,看不到原理 |
| Spec Kit | ✅ 开源 | ⚠️ 重框架,学员学的是"怎么用它",不是第一性原理 |
| **harness-5** | ✅ 完全可控 | ✅ 组件小、透明、可当场改给学员看 |

教学目标是"讲清原理",所以我们**自研最小组件**。

> 📐 想先看"骨架长什么样、每个部件为什么存在"?见 [ARCHITECTURE.md](ARCHITECTURE.md)
> —— Loop Engineering 理论骨架(Harness/Maker/Checker/Loop + 计算型/推理型 × 前馈/反馈 + AC/TC 门禁)。

## 五层阶梯(L0 → L4)+ 工业化对照(L5)

```
L0  单次调用      裸调模型,无任何检查          → 生成 ≠ 正确
L1  Harness      + 约束 + 自洽性 + 验收门禁     → 怎么知道对不对
L2  Loop         + 失败回喂,重试到通过         → 自我纠错的闭环
L3  护栏         + 迭代上限/花费上限/卡死检测   → 循环不失控、不烧钱
L4  确定性       + temp0+seed,重跑比对哈希     → 可复现(我们的差异点)
L5  LangGraph    同一个 Loop 换成状态图(需装 langgraph) → 可恢复/可观测/可扩展
```

> L0~L4 **零第三方依赖**,逐行可讲;L5 是“工业化对照版”,把手写 while 换成
> LangGraph 状态图,**Maker/Checker 一行不改**,只换编排。二者并存,见 [l5_langgraph/README.md](l5_langgraph/README.md)。

## 快速开始(开箱即用,无需 API key)

默认 `HARNESS_MODE=sample`,离线确定性运行,并**故意先错后对**以演示 Loop:

```bash
python3 harness-5/l0_single/run.py              # 裸生成(sample 下这版有 bug)
python3 harness-5/l1_harness/gate.py            # 门禁发现 bug(退出码 1)
python3 harness-5/l2_loop/loop.py               # 失败回喂 → 第 2 轮修好
python3 harness-5/l3_guardrails/loop_guarded.py # 带护栏的循环
python3 harness-5/l4_determinism/determinism.py # 跑两遍,哈希一致
python3 harness-5/l5_langgraph/run.py           # 同一个 Loop 换成 LangGraph 状态图

# 一键跑通全部
bash harness-5/run_all.sh
```

演示护栏被触发:
```bash
HARNESS_SAMPLE_STUCK=1 python3 harness-5/l3_guardrails/loop_guarded.py  # 卡死检测触发
```

## 接真实模型(可选)

```bash
export HARNESS_MODE=real
export DEEPSEEK_API_KEY=sk-xxxx      # 或 source 项目根的 .env
python3 harness-5/l2_loop/loop.py
```
`real` 模式下,失败报告会拼进 prompt 回喂给 DeepSeek 让它自己修。

## 换个任务(证明框架任务无关)

同一套 Maker/Checker/Loop,换 `HARNESS_TASK` 就换任务——**只换 spec/facts/constraints 三份声明,部件不动**:

```bash
# 默认 mathkit(数学模块);切到淘宝风商城(商品列表+详情)只加一个环境变量
HARNESS_TASK=mall python3 harness-5/l2_loop/loop.py    # 第1轮7条商品→数据门禁FAIL→第2轮8条修好
HARNESS_TASK=mall python3 harness-5/l1_harness/gate.py # 单次门禁:精准报"商品数≥8 实际7"
```

> mall 用**静态数据/标记校验**(不起服务),保持 dependency-light、逐行可讲;
> harness-4 走的是"真起 Flask 打路由"的生产味版本。

## 目录结构

```
harness-5/
  spec/            spec.md + facts.json(mathkit) · spec-mall.md + facts-mall.json(mall)
  constraints.json / constraints-mall.json  宪法:禁用模式 / 上限 / loop 护栏参数
  tests/           固定验收测试(= 可执行的规格)
  lib/             共享库:model(Maker) · gates(Checker) · common · sample_mall(mall素材)
  l0_single/       L0 裸生成
  l1_harness/      L1 门禁
  l2_loop/         L2 闭环
  l3_guardrails/   L3 护栏
  l4_determinism/  L4 确定性
  l5_langgraph/    L5 用 LangGraph 重写同一个 Loop(换引擎,原理不变)
  output/          运行产物(可删,已 gitignore)
  ARCHITECTURE.md  Loop Engineering 理论骨架(讲义)
  OUTLINE.md       Workshop 课件结构
```

## 与业界体系的对应

对应 Addy Osmani 的 Loop Engineering 四层(Prompt→Context→**Harness→Loop**):
- L1 的 constraints/spec/verify = **Harness** 层(可控环境 + 门禁)。
- L2/L3 的回喂循环 + 护栏 = **Loop** 层(Maker/Checker 分离 + 可验证停止 + 三护栏)。
- L4 的确定性验收是主流产品普遍不做的一环,是本项目**窄而确定**的差异点。
