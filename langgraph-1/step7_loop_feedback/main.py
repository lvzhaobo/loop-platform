"""step7 · 条件边=收敛判据+回喂：真实的自愈 Loop（2 轮收敛）。

比 step6 只多一件事:把 checker 后面那条【一次性到 END】的边,换成
step3(条件边)+step4(回边)的组合 —— 验收没过就把失败报告【回喂】给 maker,
让它带着"哪里错了"重生成。于是图从"跑一次"变成"修到过为止"。

step6 → step7 的唯一结构改动:
    step6:  g.add_edge("checker", END)                 # 单次,验收完就结束
    step7:  g.add_conditional_edges("checker", route,  # 未过→回 maker(回边)
                                    {"maker": "maker", END: END})

配套改动(都在节点里,和 lib 无关):
  - checker 未过时,把 gates.format_report(...) 写进 state["feedback"]。
  - maker 下一轮把 feedback 透传给 model.generate —— 真实模式会拼进 prompt;
    sample 模式据 attempt 递增,第 2 轮产出 CORRECT 版,于是验收转绿。

⚠️ 本步只做"回喂收敛",还【没有护栏】:若模型永远修不好就会一直转,
   靠 recursion_limit 兜底。迭代上限/花费上限/卡死检测是 step8。

运行：
    source .venv/bin/activate
    python langgraph-1/step7_loop_feedback/main.py
"""
import os
import sys
from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph

HARNESS5 = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "harness-5",
)
sys.path.insert(0, HARNESS5)
from lib import common, gates, model  # noqa: E402  # pyright: ignore[reportMissingImports]

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


class State(TypedDict):
    spec_text: str
    facts: dict[str, Any]
    constraints: dict[str, Any]
    out_dir: str
    attempt: int
    feedback: Optional[str]  # ★ 新增:上一轮的失败报告,回喂给 maker
    results: list[dict[str, Any]]
    stop_reason: str


def n_consistency(state: State) -> dict:
    fails = gates.check_consistency(state["spec_text"], state["facts"])
    if fails:
        return {"stop_reason": "abort:自洽性门禁未过 — " + "; ".join(fails)}
    print("[step7] 自洽性门禁通过 ✓")
    return {}


def n_maker(state: State) -> dict:
    attempt = state["attempt"] + 1
    tag = "带着上一轮的失败报告重生成" if state["feedback"] else "首次生成"
    print(f"\n===== 第 {attempt} 轮:Maker {tag} =====")
    model.generate(state["out_dir"], state["spec_text"], state["facts"],
                   state["constraints"], attempt=attempt, feedback=state["feedback"])
    return {"attempt": attempt}


def n_checker(state: State) -> dict:
    results = gates.verify(state["out_dir"], state["facts"], state["constraints"])
    report = gates.format_report(results)
    print(report)
    if gates.all_ok(results):
        return {"results": results,
                "stop_reason": f"pass:验收通过 ✓(共 {state['attempt']} 轮)"}
    # ★ 没过:把报告写进 feedback,清空 stop_reason → route 会把它送回 maker。
    print(f"[step7] 第 {state['attempt']} 轮未过,回喂失败报告,继续...")
    return {"results": results, "feedback": report}


def after_consistency(state: State) -> str:
    return END if state["stop_reason"] else "maker"


# ★ step7 的重点:验收后的路由。通过→END;没过→回 maker(这条就是回边)。
def route(state: State) -> str:
    return END if state["stop_reason"] else "maker"


def build():
    g = StateGraph(State)
    g.add_node("consistency", n_consistency)
    g.add_node("maker", n_maker)
    g.add_node("checker", n_checker)

    g.set_entry_point("consistency")
    g.add_conditional_edges("consistency", after_consistency,
                            {"maker": "maker", END: END})
    g.add_edge("maker", "checker")
    # ← 和 step6 唯一的结构差别:这里从"直达 END"改成"未过则回 maker"的条件回边。
    g.add_conditional_edges("checker", route, {"maker": "maker", END: END})
    return g.compile()


def main():
    spec_text, facts, constraints = common.load_spec()
    app = build()

    print("---- 图结构(Mermaid,注意 checker→maker 那条回边) ----")
    print(app.get_graph().draw_mermaid())
    print("------------------------------------------------------")

    init: State = {
        "spec_text": spec_text, "facts": facts, "constraints": constraints,
        "out_dir": OUT, "attempt": 0, "feedback": None,
        "results": [], "stop_reason": "",
    }
    final = app.invoke(init, config={"recursion_limit": 50})
    print(f"\n[step7] 结论:{final['stop_reason']}")
    print(f"[产物] {os.path.join(OUT, facts['module'])}")


if __name__ == "__main__":
    main()
