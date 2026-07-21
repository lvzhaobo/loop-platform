"""L5 入口:和 L2/L3 一样的体验,但底层是 LangGraph 状态图。

用法:
  python harness-5/l5_langgraph/run.py                          # mathkit,2 轮收敛
  HARNESS_TASK=mall python harness-5/l5_langgraph/run.py         # mall,2 轮收敛
  HARNESS_SAMPLE_STUCK=1 python harness-5/l5_langgraph/run.py    # 演示卡死检测护栏
  python harness-5/l5_langgraph/run.py --mermaid                 # 顺带打印图的 Mermaid
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lib import common  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]
import graph as g  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]

OUT = os.path.join(ROOT, "output", "l5")


def main():
    spec_text, facts, constraints = common.load_spec()
    app = g.build()

    if "--mermaid" in sys.argv:
        print(app.get_graph().draw_mermaid())
        print("-" * 40)

    init: g.LoopState = {
        "spec_text": spec_text, "facts": facts, "constraints": constraints,
        "out_dir": OUT, "attempt": 0, "cost": 0,
        "feedback": None, "prev_hash": None, "results": [], "stop_reason": "",
    }
    final = app.invoke(init, config={"configurable": {"thread_id": "run-1"},
                                     "recursion_limit": 50})

    print(f"\n[L5] {final['stop_reason']}")
    passed = final["stop_reason"].startswith("pass")
    state = {
        "engine": "langgraph",
        "passed": passed,
        "attempts": final["attempt"],
        "cost": final["cost"],
        "stop_reason": final["stop_reason"],
    }
    common.write(os.path.join(OUT, "state.json"),
                 json.dumps(state, ensure_ascii=False, indent=2))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
