# step3 · 条件边：按状态决定走哪条路（分支）

只比 step2 多**一个概念：条件边**。step2 的边是写死的（A 之后一定去 B）；这里的边要"看 state 再决定去哪"。

- 普通边：`add_edge(a, b)` —— 固定。
- 条件边：`add_conditional_edges(src, route_fn, {映射表})` —— `route_fn(state)` 读 state，返回下一个节点的"名字"，图据此选边。

## 运行

```bash
source .venv/bin/activate
python langgraph-1/step3_branch/main.py
```

## 为什么把分支设计成"检查→路由→通过/打回"？

这正是后面真实 Loop 的骨架。step4 只需把"打回 reject"那条边从指向 END 改成**指回上游**，分支就变成了循环。

一个约定：**route 函数只【读】state 做决策，不在里面改 state**（决策需要的值由上游节点写好）。

## 预期输出

同一张图对两个不同输入走出两条不同的路：

```
输入 'hi'          → score=2  → reject → 'hi -> [打回]'
输入 'hello world' → score=11 → approve → 'hello world -> [通过]'
```
