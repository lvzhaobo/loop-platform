# step7 · 条件边 = 收敛判据 + 回喂（真实自愈 Loop）

## 这一步只比 step6 多了一件事

把 step6 里那条【验收完就到 END】的直线边，换成 **step3（条件边）+ step4（回边）** 的组合：

```python
# step6:  跑一次就结束
g.add_edge("checker", END)

# step7:  没过就把失败报告回喂给 maker，重生成
g.add_conditional_edges("checker", route, {"maker": "maker", END: END})
```

于是图从「跑一次」变成「**修到过为止**」——这就是 Agent Loop 的核心闭环。

## 三个关键点

1. **收敛判据**：`route(state)` 只读 `stop_reason`。checker 里 `gates.all_ok(results)` 为真才写 `stop_reason=pass`，否则留空 → route 判定回 `maker`。
2. **回喂（feedback）**：checker 没过时把 `gates.format_report(...)` 写进 `state["feedback"]`；maker 下一轮把它透传给 `model.generate(..., feedback=...)`。
   - real 模式：feedback 会拼进 prompt，让模型「看到哪里错了」再改。
   - sample 模式：忽略内容，只按 `attempt` 递增——第 1 轮 BUGGY、第 2 轮 CORRECT。
3. **回边**：`{"maker": "maker"}` 里等号右边指回上游节点，这一条就是「环」。

## 运行

```bash
source .venv/bin/activate
python langgraph-1/step7_loop_feedback/main.py
```

预期输出（2 轮收敛）：

```
第 1 轮:Maker 首次生成      → attempt=1 BUGGY → 验收 4/5 [FAIL] unittest → 回喂
第 2 轮:Maker 带着报告重生成 → attempt=2 CORRECT → 验收 5/5 → pass
结论:pass:验收通过 ✓(共 2 轮)
```

## ⚠️ 本步还没有护栏

如果模型「怎么修都修不好」，这个循环会一直转，只靠 `recursion_limit=50` 兜底强行报错。
真正的**迭代上限 / 花费上限 / 卡死检测（连续两轮产物相同就停）**是 **step8** 的内容。

想亲眼看到「修不好」的场景，可以强制 sample 永远产 BUGGY：

```bash
HARNESS_SAMPLE_STUCK=1 python langgraph-1/step7_loop_feedback/main.py
# 会一直第 N 轮未过…直到撞上 recursion_limit 抛错 —— 这正是 step8 要解决的
```

## 与前面各步的关系

| 用到的原语 | 来自 |
|---|---|
| 单节点函数、局部更新 | step1 |
| 顺序边、State 累积 | step2 |
| 条件边 + 路由函数 | step3 |
| 回边（环） | step4 |
| 真实 Maker/Checker（复用 harness-5/lib） | step6 |
| **回边 + 收敛判据 + 回喂（本步组装成闭环）** | **step7** |
