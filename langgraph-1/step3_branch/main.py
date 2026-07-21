"""step3 · 条件边：按状态决定走哪条路（分支）。

比 step2 只多一个概念:**条件边(conditional edge)**。
step2 的边是"写死的"(A 之后一定去 B);这里的边要"看 state 再决定去哪"。

这一步故意把分支设计成 **检查 → 路由 → 通过/打回** 的形状,
因为这正是后面真实 Loop 的骨架:
  - 现在:check → route →(通过 approve / 打回 reject)→ END
  - step4:只需把"打回"那条边从指向 END 改成【指回上游】,分支就变成了循环。

核心区别:
  - 普通边 add_edge(a, b)      : 固定,a 跑完一定去 b。
  - 条件边 add_conditional_edges(src, route_fn, {...}) :
        route_fn(state) 读 state,返回下一个节点的"名字",图据此选边。
    ★ 约定:route 函数只【读】state 做决策,不要在里面改 state。

运行：
    source .venv/bin/activate
    python langgraph-1/step3_branch/main.py
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    text: str
    score: int  # 由 check 节点打分,route 依据它选边


# 节点 check:假装做了个"质量打分"(这里用 text 长度代替真实验收)。
def check(state: State) -> dict[str, int]:
    score = len(state["text"])
    print(f"[check] text={state['text']!r} 打分 = {score}")
    return {"score": score}


# ★ 条件边的路由函数:只读 state,返回【下一个节点的名字】。
#   注意:这里不修改 state,决策所需的 score 是上游 check 节点写好的。
def route(state: State) -> str:
    decision = "approve" if state["score"] >= 5 else "reject"
    print(f"[route] score={state['score']} → 走 {decision}")
    return decision


# 分支①:通过。
def approve(state: State) -> dict[str, str]:
    return {"text": state["text"] + " -> [通过]"}


# 分支②:打回。(step4 里,这条分支会改成"回喂重来"的回边)
def reject(state: State) -> dict[str, str]:
    return {"text": state["text"] + " -> [打回]"}


def build():
    g = StateGraph(State)
    g.add_node("check", check)
    g.add_node("approve", approve)
    g.add_node("reject", reject)

    g.add_edge(START, "check")
    # ★ step3 的重点:条件边。第三个参数是"路由返回值 → 目标节点"的映射表。
    g.add_conditional_edges("check", route, {
        "approve": "approve",
        "reject": "reject",
    })
    g.add_edge("approve", END)
    g.add_edge("reject", END)
    return g.compile()


def main():
    app = build()

    print("---- 图结构(Mermaid) ----")
    print(app.get_graph().draw_mermaid())
    print("--------------------------")

    # 跑两个不同输入,看到同一张图走出两条不同的路:
    for text in ["hi", "hello world"]:
        print(f"\n===== 输入 text={text!r} =====")
        result = app.invoke({"text": text, "score": 0})
        print(f"[最终 state] {result}")


if __name__ == "__main__":
    main()
