"""step1 · 最小的 LangGraph：一个节点。

这是 LangGraph 的"Hello World"——整张图只有一个节点，
目的是把最小闭环跑通：State → Node → 连边 → compile → invoke。

运行：
    source .venv/bin/activate
    python langgraph-1/step1_single_node/main.py
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


# ① State：图里传来传去的共享状态,用 TypedDict 声明字段。
#    每个节点读它、返回对它的"局部更新",LangGraph 负责合并。
class State(TypedDict):
    text: str


# ② Node:就是一个普通函数,签名是 (state) -> 局部更新(dict)。
#    这里只做一件事:在 text 后面接一段,证明"状态被节点改过"。
def say_hello(state: State) -> dict[str, str]:
    print(f"[节点 say_hello] 收到 text = {state['text']!r}")
    return {"text": state["text"] + " -> hello, langgraph"}


# ③ 组装图:声明节点,再用边把 START → 节点 → END 连起来。
def build():
    g = StateGraph(State)
    g.add_node("say_hello", say_hello)  # 注册节点
    g.add_edge(START, "say_hello")      # 入口:从 START 进到 say_hello
    g.add_edge("say_hello", END)        # 出口:say_hello 跑完就结束
    return g.compile()                  # ④ compile:图纸 → 可执行 app


def main():
    app = build()

    # 顺带看一眼图长什么样(LangGraph 一行导出 Mermaid)
    print("---- 图结构(Mermaid) ----")
    print(app.get_graph().draw_mermaid())
    print("--------------------------")

    # ⑤ invoke:喂初始 state,拿回最终 state。
    result = app.invoke({"text": "start"})
    print(f"[最终 state] {result}")


if __name__ == "__main__":
    main()
