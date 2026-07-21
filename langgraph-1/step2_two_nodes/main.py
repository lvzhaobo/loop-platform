"""step2 · 两个节点串成链：顺序边。

比 step1 只多一个概念:**顺序边**。
step1 是 START → 一个节点 → END;这里变成 START → 节点A → 节点B → END,
两个节点按边的方向依次执行,前一个节点的输出就是后一个节点的输入。

关键点:每个节点只返回"自己改动的字段(局部更新)",LangGraph 会把它
合并进共享 State,再交给下一个节点——你不用手动传参。

运行：
    source .venv/bin/activate
    python langgraph-1/step2_two_nodes/main.py
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


# State 比 step1 多一个 steps 字段,用来记录"经过了哪些节点",
# 直观看到两个节点是按顺序跑的。
class State(TypedDict):
    text: str
    steps: list[str]


# 节点A:第一个跑。它把 text 改写,并往 steps 里追加自己的名字。
def node_a(state: State) -> dict[str, object]:
    print(f"[节点A] 收到 text = {state['text']!r}")
    return {
        "text": state["text"] + " -> A",
        "steps": state["steps"] + ["A"],
    }


# 节点B:紧接着A跑。它收到的是"A 改过之后"的 state。
def node_b(state: State) -> dict[str, object]:
    print(f"[节点B] 收到 text = {state['text']!r}  (注意:已经带上 A 了)")
    return {
        "text": state["text"] + " -> B",
        "steps": state["steps"] + ["B"],
    }


def build():
    g = StateGraph(State)
    g.add_node("node_a", node_a)
    g.add_node("node_b", node_b)

    # ★ step2 的重点:三条顺序边,把节点串成一条链。
    g.add_edge(START, "node_a")     # 入口 → A
    g.add_edge("node_a", "node_b")  # A → B(这就是"顺序边")
    g.add_edge("node_b", END)       # B → 结束
    return g.compile()


def main():
    app = build()

    print("---- 图结构(Mermaid) ----")
    print(app.get_graph().draw_mermaid())
    print("--------------------------")

    result = app.invoke({"text": "start", "steps": []})
    print(f"[最终 state] {result}")
    print(f"[执行顺序] {' -> '.join(result['steps'])}")


if __name__ == "__main__":
    main()
