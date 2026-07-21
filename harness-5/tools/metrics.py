"""harness-5 · 【指标聚合】Phase 2 —— 读 output/events.jsonl,算出核心指标。

最高价值的一条是【门禁失败 Top-N】:模型最常挂在哪一关,直接指导你改哪条 rule/spec
—— 正是 "一条规则被反复提就写成 Linter 规则" 的数据化落地。

用法:
    python harness-5/tools/metrics.py            # 人读表格
    python harness-5/tools/metrics.py --md        # Markdown(进报告/CI)
    python harness-5/tools/metrics.py --json       # 机器可读(给控制台)

只读 stdlib,零依赖。
"""
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # harness-5
EVENTS_PATH = os.path.join(ROOT, "output", "events.jsonl")


def load_events() -> list[dict]:
    if not os.path.exists(EVENTS_PATH):
        sys.exit(f"[metrics] 没有事件日志: {EVENTS_PATH}\n先跑一次带埋点的生成,如: "
                 "HARNESS_MODE=sample python harness-5/l2_loop/loop.py")
    events = []
    with open(EVENTS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def compute(events: list[dict]) -> dict:
    checks = [e for e in events if e.get("kind") == "check.result"]
    llms = [e for e in events if e.get("kind") == "llm.call"]

    # 门禁失败 Top-N:按 check 名聚合 出现次数 / 失败次数
    per_check: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [total, fail]
    for e in checks:
        rec = per_check[e["check"]]
        rec[0] += 1
        if not e.get("ok"):
            rec[1] += 1
    top_fail = sorted(
        ({"check": k, "total": v[0], "fail": v[1],
          "fail_rate": round(v[1] / v[0], 3) if v[0] else 0.0}
         for k, v in per_check.items()),
        key=lambda x: (-x["fail"], -x["fail_rate"]),
    )

    # 按 trace 分组:首轮失败率 / 回喂修复率
    traces: dict[str, dict] = defaultdict(lambda: {"attempts": {}, "case": None})
    for e in checks:
        tid = e.get("trace_id") or "?"
        att = e.get("attempt") or 1
        t = traces[tid]
        t["case"] = e.get("case")
        t["attempts"].setdefault(att, True)
        if not e.get("ok"):
            t["attempts"][att] = False  # 该轮存在失败

    n_trace = len(traces)
    first_fail = sum(1 for t in traces.values() if not t["attempts"].get(1, True))
    # 回喂修复:首轮失败,但最后一轮全绿
    fixed = 0
    for t in traces.values():
        atts = t["attempts"]
        if not atts.get(1, True):  # 首轮失败
            last = max(atts)
            if atts.get(last):     # 末轮通过
                fixed += 1

    tokens = sum(e.get("total_tokens") or 0 for e in llms)
    return {
        "n_events": len(events),
        "n_traces": n_trace,
        "n_llm_calls": len(llms),
        "total_tokens": tokens,
        "first_fail_rate": round(first_fail / n_trace, 3) if n_trace else 0.0,
        "feedback_fix_rate": round(fixed / first_fail, 3) if first_fail else 0.0,
        "top_fail": top_fail,
    }


def render_text(m: dict) -> str:
    L = []
    L.append("===== harness-5 指标聚合(来自 output/events.jsonl) =====")
    L.append(f"事件 {m['n_events']} 条 · 运行链路 {m['n_traces']} 条 · "
             f"LLM 调用 {m['n_llm_calls']} 次 · 累计 token {m['total_tokens']}")
    L.append(f"首轮失败率 {m['first_fail_rate']:.0%} · 回喂修复率 {m['feedback_fix_rate']:.0%}")
    L.append("")
    L.append("--- 门禁失败 Top-N(fail 次数降序;最该优先改的在最上面) ---")
    L.append(f"{'失败':>4} {'总计':>4} {'失败率':>6}  门禁")
    any_fail = False
    for r in m["top_fail"]:
        if r["fail"] == 0:
            continue
        any_fail = True
        L.append(f"{r['fail']:>4} {r['total']:>4} {r['fail_rate']:>6.0%}  {r['check']}")
    if not any_fail:
        L.append("(本批数据里没有任何门禁失败 —— 全绿)")
    return "\n".join(L)


def render_md(m: dict) -> str:
    L = ["# harness-5 指标报告", "",
         f"- 事件：{m['n_events']} 条，链路：{m['n_traces']} 条，"
         f"LLM 调用：{m['n_llm_calls']} 次，累计 token：{m['total_tokens']}",
         f"- 首轮失败率：{m['first_fail_rate']:.0%}，回喂修复率：{m['feedback_fix_rate']:.0%}",
         "", "## 门禁失败 Top-N", "", "| 失败 | 总计 | 失败率 | 门禁 |", "|---:|---:|---:|---|"]
    for r in m["top_fail"]:
        if r["fail"] == 0:
            continue
        L.append(f"| {r['fail']} | {r['total']} | {r['fail_rate']:.0%} | {r['check']} |")
    return "\n".join(L)


def main() -> None:
    events = load_events()
    m = compute(events)
    if "--json" in sys.argv:
        print(json.dumps(m, ensure_ascii=False, indent=2))
    elif "--md" in sys.argv:
        print(render_md(m))
    else:
        print(render_text(m))


if __name__ == "__main__":
    main()
