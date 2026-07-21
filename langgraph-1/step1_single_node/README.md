# step1 · 最小的 LangGraph：一个节点

LangGraph 的 "Hello World"——整张图只有一个节点。目的是把最小闭环跑通。

## 运行

```bash
source .venv/bin/activate
python langgraph-1/step1_single_node/main.py
```

## 讲什么

LangGraph 的最小闭环只有 5 个动作：

1. **定义 State**：用 `TypedDict` 声明在图里传来传去的共享状态。
2. **写 Node**：一个普通函数 `(state) -> 局部更新`，只负责改状态。
3. **连边**：`START → 节点 → END`，告诉图从哪进、到哪停。
4. **compile**：把"图纸"编译成可执行的 app。
5. **invoke**：喂一个初始 state，拿回最终 state。

把这 5 步跑通，后面所有复杂度（分支、循环、检查点）都只是在这张图上加东西。

## 预期输出

```
[节点 say_hello] 收到 text = 'start'
[最终 state] {'text': 'start -> hello, langgraph'}
```
