"""step6 · 换上真实的 Maker/Checker：跑 mathkit（单次，不循环）。

到 step5 为止,节点都是玩具(往 text 后面接字符串)。从这里开始接真实组件:
把 step2/step3 的图形状(直线 + 一个前置门禁)原样搬过来,只把节点内部换成
harness-5 里现成的 Maker 和 Checker —— 它们一行都不用改。

  - 门禁 n_consistency  = gates.check_consistency(生成前:facts 声明的函数在规格里有落点)
  - Maker n_maker       = model.generate      (真实生成 mathkit.py 到 out_dir)
  - Checker n_checker   = gates.verify         (结构/安全/行数 + 跑固定单测)

★ 本步【只跑一次】,不回喂、不循环。默认 sample 模式第 1 轮故意写个有 bug 的
  factorial,所以验收会 FAIL —— 这正好说明"单次不够",引出 step7 的回喂循环:
  只要把 checker 后面加一条【未过就回 maker】的回边,就变成会自愈的 Loop。

依赖:复用 harness-5/lib(Maker/Checker/common)与 harness-5/spec(mathkit 规格)。
默认 HARNESS_MODE=sample,离线、不烧额度。

运行：
    source .venv/bin/activate
    python langgraph-1/step6_real_makercheck/main.py
"""
import os
import sys
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

# 把 harness-5 加进 import 路径,直接复用它的 lib(Maker/Checker/common)。
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
    results: list[dict[str, Any]]
    report: str
    stop_reason: str


# 门禁:生成之前跑,最便宜。facts 声明的函数都能在规格里找到落点吗?
def n_consistency(s: State) -> dict:
    fails = gates.check_consistency(s["spec_text"], s["facts"])
    if fails:
        return {"stop_reason": "abort:自洽性门禁未过 — " + "; ".join(fails)}
    print("[step6] 自洽性门禁通过 ✓")
    return {}


# Maker:真实生成 mathkit.py。attempt=1 → sample 模式产出 BUGGY 版。
def n_maker(s: State) -> dict:
    attempt = s["attempt"] + 1
    print(f"\n===== 第 {attempt} 轮:Maker 生成 =====")
    model.generate(s["out_dir"], s["spec_text"], s["facts"], s["constraints"],
                   attempt=attempt, feedback=None)
    return {"attempt": attempt}


# Checker:真实验收(结构/安全/行数 + 跑单测),把逐项结果和报告写回 state。
def n_checker(s: State) -> dict:
    results = gates.verify(s["out_dir"], s["facts"], s["constraints"])
    report = gates.format_report(results)
    print(report)
    reason = "pass:验收通过 ✓" if gates.all_ok(results) else "fail:验收未过(单次不够,见 step7)"
    return {"results": results, "report": report, "stop_reason": reason}


# 条件边:门禁没过就直接 END(abort),否则去 maker。
def after_consistency(s: State) -> str:
    return END if s["stop_reason"] else "maker"


def build():
    g = StateGraph(State)
    g.add_node("consistency", n_consistency)
    g.add_node("maker", n_maker)
    g.add_node("checker", n_checker)

    g.set_entry_point("consistency")
    g.add_conditional_edges("consistency", after_consistency,
                            {"maker": "maker", END: END})
    g.add_edge("maker", "checker")  # 单次:生成完就验收,验收完就结束
    g.add_edge("checker", END)      # ★ step7 会把这条改成"未过则回 maker"的回边
    return g.compile()


def main():
    spec_text, facts, constraints = common.load_spec()  # 复用 harness-5 的 mathkit 规格
    app = build()

    print("---- 图结构(Mermaid) ----")
    print(app.get_graph().draw_mermaid())
    print("--------------------------")

    init: State = {
        "spec_text": spec_text, "facts": facts, "constraints": constraints,
        "out_dir": OUT, "attempt": 0,
        "results": [], "report": "", "stop_reason": "",
    }
    final = app.invoke(init)
    print(f"\n[step6] 结论:{final['stop_reason']}")
    print(f"[产物] {os.path.join(OUT, facts['module'])}")


if __name__ == "__main__":
    main()
