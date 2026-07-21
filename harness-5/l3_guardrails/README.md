# L3 · 护栏(让循环不失控)

## 讲什么
L2 的循环没有刹车。L3 装上**三条护栏**,任一触发即停,循环从此"可控、可预算":

| 护栏 | 作用 | 参数(constraints.json→loop) |
|---|---|---|
| 迭代上限 | 最多试几轮,防无限循环 | `max_iterations` |
| 花费上限 | 累计成本超预算即停(mock token/$) | `max_cost` / `cost_per_attempt` |
| 卡死检测 | 本轮产物与上轮字节相同 → 修不动了,停 | (diff by sha256) |

> 对应业界经验:Loop Engineering 的三护栏 = 迭代上限 / diff 检查 / 花费上限。
> 斯坦福研究说同任务 token 能差 30 倍——**先设花费上限再开 loop**,别烧穿预算。

## 组件(相对 L2 新增)
- `constraints.json` 的 `"loop"` 段:护栏参数,可一行行改。
- `loop_guarded.py`:循环体里三处 `if ... break`,外加 sha256 卡死检测。

## 动手
```bash
# 正常:第 2 轮通过,花费 40
python harness-5/l3_guardrails/loop_guarded.py

# 演示护栏触发:让 sample 永远修不好
HARNESS_SAMPLE_STUCK=1 python harness-5/l3_guardrails/loop_guarded.py
```
`STUCK=1` 时:第 1 轮 BUGGY,第 2 轮产物与第 1 轮完全相同 → **卡死检测**触发,秒停(不会白烧 5 轮)。

## 观察到的问题(引出 L4)
- 现在循环能停、能控预算了。但**同样的输入,重跑结果一定一样吗?** 不设防的话不一定。
- **教学点**:可复现是更硬的验收——固定 temperature/seed,重跑并比对产物哈希。→ **L4**。
