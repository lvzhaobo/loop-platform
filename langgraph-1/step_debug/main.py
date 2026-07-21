"""step_debug · "写乱了会怎样"——LangGraph 的检查机制实操。

这不是主线 step,而是一个【排错演示】:故意把图写错,看 LangGraph 在
哪个阶段、报什么错。理解这些,自己搭图混乱时就知道去哪儿找问题。

三类错误,对应三道防线:
  ① compile 时的静态校验   —— 结构错(悬空边/无入口)在编译就炸,跑都跑不起来。
  ② 运行时校验             —— 路由返回了映射表里没有的名字,invoke 时才炸。
  ③ recursion_limit 兜底   —— 循环忘了终止条件,到上限自动抛错,不会真死循环。

外加一个"肉眼利器":draw_mermaid() 把图画出来,边连错一眼看穿。

运行：
    source .venv/bin/activate
    python langgraph-1/step_debug/main.py
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    x: int


def node_a(state: State) -> dict:
    return {"x": state["x"] + 1}


def _demo(title: str, fn) -> None:
    """跑一个会出错的构造,把异常类型和消息打出来(而不是让程序崩掉)。"""
    print(f"\n===== {title} =====")
    try:
        fn()
        print("  (没有报错)")
    except Exception as e:  # noqa: BLE001  # 演示用:捕获并展示错误
        print(f"  ✗ {type(e).__name__}: {e}")


# ① 悬空边:边指向一个没 add_node 的节点 → compile 时炸。
def case_dangling_edge():
    g = StateGraph(State)
    g.add_node("a", node_a)
    g.add_edge(START, "a")
    g.add_edge("a", "not_exist")  # ← 目标节点不存在
    g.compile()


# ② 没有入口:忘了 add_edge(START, ...) → compile 时炸。
def case_no_entry():
    g = StateGraph(State)
    g.add_node("a", node_a)
    g.add_edge("a", END)  # 只有出口,没有从 START 进来的边
    g.compile()


# ③ 路由返回未知分支:映射表里没有 route 返回的名字 → 运行时炸。
def case_bad_route():
    g = StateGraph(State)
    g.add_node("a", node_a)
    g.add_edge(START, "a")
    g.add_conditional_edges("a", lambda s: "typo", {"ok": END})  # 返回 "typo" 不在表里
    app = g.compile()
    app.invoke({"x": 0})


# ④ 死循环:回边永远成立,靠 recursion_limit 兜底抛错。
def case_infinite_loop():
    g = StateGraph(State)
    g.add_node("a", node_a)
    g.add_edge(START, "a")
    g.add_conditional_edges("a", lambda s: "again", {"again": "a"})  # 永远回自己
    app = g.compile()
    app.invoke({"x": 0}, config={"recursion_limit": 10})  # 到 10 步就抛 GraphRecursionError


def case_ok_but_visualize():
    """一个写对的图:用 draw_mermaid 把结构打出来,自查连线。"""
    g = StateGraph(State)
    g.add_node("a", node_a)
    g.add_edge(START, "a")
    g.add_edge("a", END)
    app = g.compile()
    print(app.get_graph().draw_mermaid())


def main():
    _demo("① 悬空边(边指向不存在的节点)→ compile 时报", case_dangling_edge)
    _demo("② 没有入口(忘了从 START 连边)→ compile 时报", case_no_entry)
    _demo("③ 路由返回未知分支 → invoke 运行时报", case_bad_route)
    _demo("④ 死循环 → recursion_limit 兜底报", case_infinite_loop)

    print("\n===== ⑤ 肉眼利器:draw_mermaid 自查结构 =====")
    case_ok_but_visualize()


if __name__ == "__main__":
    main()
