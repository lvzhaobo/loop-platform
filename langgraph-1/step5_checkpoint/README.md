# step5 · Checkpointer：每一步落检查点，可回放、可恢复、可时间旅行

只比 step4 多**一个概念：Checkpointer（检查点）**。step4 跑完只能看到"最终 state"；装上检查点后，LangGraph 会把**每一步之后的 state 快照**都存下来。

## 运行

```bash
source .venv/bin/activate
python langgraph-1/step5_checkpoint/main.py
```

## 只改两处

1. `compile(checkpointer=MemorySaver())` —— 教学用内存版；生产换 `SqliteSaver`。
2. `invoke(..., config={"configurable": {"thread_id": "xxx"}})` —— 必须给线程 id。

## 解锁三件事

- **可观测**：`get_state_history` 回看每步快照。
- **可恢复**：同一 `thread_id` 再 invoke 从断点接着跑。
- **时间旅行**：从某个历史检查点重新分叉——这正是 **LangGraph Studio（step9）** 的核心能力。

> ⚠️ `MemorySaver` 只活在进程内存，进程一退就没了。要真"崩了能恢复"得用落盘的 `SqliteSaver`——那是 step10。

## 预期输出

打印出 6 个检查点快照（含最初的空检查点），并演示按 `thread_id` 从检查点恢复。
