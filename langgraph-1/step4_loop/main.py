"""step4 · 回边：把"打回"指回上游，分支就变成了循环。

比 step3 只多一个概念:**回边(把边指回上游节点)**。
step3 里 route 判"打回"时走向 END;这里改成走回 maker —— 于是形成一个
【生成 → 检查 → 不达标就回去重生成】的循环,直到达标才 END。

★ 循环 = 图里的一条回边。这就是 LangGraph 对"循环"的建模方式:
  不是写 while,而是在图里让某条边指回上游节点。

⚠️ 有循环就可能跑不停。LangGraph 用 recursion_limit(默认 25)兜底,
   超过就抛错。真正"该不该停"的判据(达标/超限)写在节点+路由里 —— 这正是
   step8 要展开的"护栏"。本步先只关心"循环怎么建"。

运行：
    source .venv/bin/activate
    python langgraph-1/step4_loop/main.py
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

TARGET = 8  # 达标线:score(这里用 text 长度模拟)到 8 就算通过


class State(TypedDict):
    text: str
    score: int
    attempt: int


# maker:每轮"生成/改进"一次。这里用"追加一段"模拟产物在变好。
# 真实 Loop 里,这一步会换成调模型生成代码(见 step6)。
def maker(state: State) -> dict:
    n = state["attempt"] + 1
    text = state["text"] + " +改进"
    print(f"[maker] 第 {n} 轮,产出 text={text!r}")
    return {"text": text, "attempt": n}


# check:给产物打分(模拟验收)。真实 Loop 里换成 gates.verify(见 step6/7)。
def check(state: State) -> dict[str, int]:
    score = len(state["text"])
    print(f"[check] 打分 = {score} (达标线 {TARGET})")
    return {"score": score}


# ★ 路由:达标 → END;没达标 → 回 maker(这条就是"回边")。
def route(state: State) -> str:
    if state["score"] >= TARGET:
        print("[route] 达标 → 结束")
        return "done"
    print("[route] 未达标 → 回 maker 再来一轮")
    return "retry"


def build():
    g = StateGraph(State)
    g.add_node("maker", maker)
    g.add_node("check", check)

    g.add_edge(START, "maker")
    g.add_edge("maker", "check")      # 生成完就检查
    # ★ step4 的重点:条件边里,"retry" 指回 maker —— 这条回边就是循环。
    g.add_conditional_edges("check", route, {
        "retry": "maker",  # ← 回边:指回上游,形成循环
        "done": END,
    })
    return g.compile()


def main():
    app = build()

    print("---- 图结构(Mermaid,注意 check→maker 那条回边) ----")
    print(app.get_graph().draw_mermaid())
    print("----------------------------------------------------")

    result = app.invoke({"text": "初稿", "score": 0, "attempt": 0})
    print(f"\n[最终 state] {result}")
    print(f"[共循环] {result['attempt']} 轮后达标")


if __name__ == "__main__":
    main()
