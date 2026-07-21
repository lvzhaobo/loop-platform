"""step5 · Checkpointer：每一步落检查点，可回放、可恢复、可时间旅行。

比 step4 只多一个概念:**Checkpointer(检查点)**。
step4 跑完只能看到"最终 state";这里给图装上检查点后,LangGraph 会把
【每一步之后的 state 快照】都存下来,于是你能:

  1. 可观测:回看每一步之后 state 长什么样(get_state_history)。
  2. 可恢复:进程崩了,用同一个 thread_id 再 invoke 能从断点接着跑。
  3. 时间旅行:挑某个历史检查点,从那儿重新分叉跑(Studio 的核心能力)。

装检查点只改两处:
  a) compile(checkpointer=MemorySaver())   ← 教学用内存版;生产换 SqliteSaver
  b) invoke(..., config={"configurable": {"thread_id": "xxx"}})  ← 必须给线程 id

⚠️ MemorySaver 只活在进程内存里,进程一退就没了。要真"崩了能恢复",
   得用落盘的 SqliteSaver —— 这是 step10(工业化)的内容。

运行：
    source .venv/bin/activate
    python langgraph-1/step5_checkpoint/main.py
"""
from typing import TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

TARGET = 8


class State(TypedDict):
    text: str
    score: int
    attempt: int


def maker(state: State) -> dict:
    n = state["attempt"] + 1
    text = state["text"] + " +改进"
    print(f"[maker] 第 {n} 轮,产出 text={text!r}")
    return {"text": text, "attempt": n}


def check(state: State) -> dict[str, int]:
    score = len(state["text"])
    print(f"[check] 打分 = {score} (达标线 {TARGET})")
    return {"score": score}


def route(state: State) -> str:
    return "done" if state["score"] >= TARGET else "retry"


def build():
    g = StateGraph(State)
    g.add_node("maker", maker)
    g.add_node("check", check)
    g.add_edge(START, "maker")
    g.add_edge("maker", "check")
    g.add_conditional_edges("check", route, {"retry": "maker", "done": END})
    # ★ step5 的重点:compile 时传入 checkpointer,图从此"每步存档"。
    return g.compile(checkpointer=MemorySaver())


def main():
    app = build()

    # ★ 有了 checkpointer,invoke 必须带 thread_id:它是"这盘对话/这次任务"的标识,
    #   同一个 thread_id 的多次调用共享同一条检查点历史。
    config: RunnableConfig = {"configurable": {"thread_id": "run-1"}}

    result = app.invoke({"text": "初稿", "score": 0, "attempt": 0}, config=config)
    print(f"\n[最终 state] {result}")

    # ① 可观测:把每一步之后的 state 快照倒着打印出来(最新在前)。
    print("\n---- 检查点历史(每一步的 state 快照,最新在前) ----")
    for snap in app.get_state_history(config):
        nxt = snap.next or ("END",)  # 下一步要跑的节点;空=已结束
        attempt = snap.values.get("attempt", "-")  # 最初的空检查点还没有值
        score = snap.values.get("score", "-")
        print(f"  attempt={attempt!s:<2} score={score!s:<3} 下一步→{nxt}")

    # ② 时间旅行(演示):不给新输入、只带 thread_id 再 invoke,
    #    图会从最新检查点继续 —— 因为已达标,直接返回,不再多跑。
    print("\n---- 用同一 thread_id 再 invoke(从检查点恢复) ----")
    again = app.invoke(None, config=config)
    print(f"[恢复后 state] {again}  (已达标,未新增轮次)")


if __name__ == "__main__":
    main()
