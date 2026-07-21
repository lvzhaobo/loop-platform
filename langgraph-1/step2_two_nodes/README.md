# step2 · 两个节点串成链：顺序边

只比 step1 多**一个概念：顺序边**。

- step1：`START → 一个节点 → END`
- step2：`START → 节点A → 节点B → END`

## 运行

```bash
source .venv/bin/activate
python langgraph-1/step2_two_nodes/main.py
```

## 两个要点

1. **边决定执行顺序**：`add_edge("node_a", "node_b")` 让 A 跑完自动进 B，A 的输出就是 B 的输入。
2. **节点只返回局部更新**：每个节点只 `return` 自己改动的字段，LangGraph 自动合并进共享 State，不用手动传参。

## 预期输出

```
[节点A] 收到 text = 'start'
[节点B] 收到 text = 'start -> A'   ← 注意：B 收到的是 A 改过之后的 state
[最终 state] {'text': 'start -> A -> B', 'steps': ['A', 'B']}
[执行顺序] A -> B
```
