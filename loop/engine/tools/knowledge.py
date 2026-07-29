"""09a-knowledge：从历史运行数据中学习。失败模式库 + 成功模式库 + 自动推荐。"""

import json, os
from collections import Counter, defaultdict
from pathlib import Path

RUNS_FILE = os.environ.get("LOOP_RUNS_FILE", "output/runs.jsonl")
TRACE_FILE = os.environ.get("LOOP_TRACE_FILE", "output/trace.jsonl")


def load_runs():
    """读取 runs.jsonl。"""
    if not os.path.exists(RUNS_FILE):
        return []
    runs = []
    with open(RUNS_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    runs.append(json.loads(line))
                except Exception:
                    pass
    return runs


def load_traces():
    """读取 trace.jsonl。"""
    if not os.path.exists(TRACE_FILE):
        return []
    events = []
    with open(TRACE_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass
    return events


def analyze(runs: list[dict], events: list[dict]) -> dict:
    """分析历史数据，返回洞察报告。"""
    if not runs:
        return {"total_runs": 0, "insights": [], "recommendations": []}

    total = len(runs)
    passed = [r for r in runs if r.get("result") == "pass"]
    failed = [r for r in runs if r.get("result") != "pass"]
    pass_rate = round(len(passed) / total * 100, 1) if total else 0

    # 平均尝试次数
    attempts = [r.get("attempts", 1) for r in runs]
    avg_attempts = round(sum(attempts) / len(attempts), 1)

    # 花费统计
    costs = [r.get("cost_yuan", 0) for r in runs if r.get("cost_yuan")]
    total_cost = round(sum(costs), 2)

    # 失败模式：统计哪些 case 最容易失败
    case_stats = defaultdict(lambda: {"total": 0, "pass": 0, "fail": 0})
    for r in runs:
        case = r.get("case", "unknown")
        case_stats[case]["total"] += 1
        if r.get("result") == "pass":
            case_stats[case]["pass"] += 1
        else:
            case_stats[case]["fail"] += 1

    # 最常失败的 case
    worst_cases = sorted(
        [(c, s) for c, s in case_stats.items() if s["total"] >= 2],
        key=lambda x: x[1]["fail"] / x[1]["total"], reverse=True
    )[:3]

    # 最成功的 case
    best_cases = sorted(
        [(c, s) for c, s in case_stats.items() if s["total"] >= 2],
        key=lambda x: x[1]["pass"] / x[1]["total"], reverse=True
    )[:3]

    # 确定性统计
    det_stats = Counter(r.get("determinism", "skip") for r in passed)
    identical_rate = round(det_stats.get("identical", 0) / max(len(passed), 1) * 100, 1)

    # 趋势：最近 5 次
    recent = runs[-5:]
    recent_pass = sum(1 for r in recent if r.get("result") == "pass")

    insights = [
        {"type": "stat", "label": "总运行", "value": total, "detail": f"通过率 {pass_rate}%"},
        {"type": "stat", "label": "平均尝试", "value": f"{avg_attempts} 次", "detail": "首次通过率高则低"},
        {"type": "stat", "label": "累计花费", "value": f"¥{total_cost}", "detail": f"平均 ¥{round(total_cost/max(total,1),4)}/次"},
    ]

    if worst_cases:
        insights.append({
            "type": "warning",
            "label": "高频失败 Case",
            "value": worst_cases[0][0],
            "detail": f"{worst_cases[0][0]}: {worst_cases[0][1]['fail']}/{worst_cases[0][1]['total']} 失败。建议检查该 case 的 spec 规则"
        })

    if best_cases:
        insights.append({
            "type": "success",
            "label": "最佳 Case",
            "value": best_cases[0][0],
            "detail": f"{best_cases[0][0]}: {best_cases[0][1]['pass']}/{best_cases[0][1]['total']} 通过。可复制其规则配置"
        })

    # 推荐
    recommendations = []
    if avg_attempts > 1.5:
        recommendations.append("平均重试次数偏高，建议检查 rules 和 spec 是否足够详细")
    if identical_rate < 50 and det_stats.get("drift", 0) > 0:
        recommendations.append(f"确定性复跑漂移率较高（{100-identical_rate}%），建议检查 spec 中是否有模糊描述")
    if total_cost > 10:
        recommendations.append(f"累计花费已超 ¥10，建议优化 prompt 提高一次通过率")
    if pass_rate < 70:
        recommendations.append("整体通过率偏低，建议加强 rules 约束和 field_rules 量化规则")
    if pass_rate >= 90:
        recommendations.append("通过率优秀！可以尝试更复杂的 spec 挑战更高难度")

    return {
        "total_runs": total,
        "pass_rate": pass_rate,
        "avg_attempts": avg_attempts,
        "total_cost_yuan": total_cost,
        "identical_rate": identical_rate,
        "recent": {"count": len(recent), "pass": recent_pass},
        "insights": insights,
        "recommendations": recommendations,
        "updated_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
    }


if __name__ == "__main__":
    runs = load_runs()
    events = load_traces()
    result = analyze(runs, events)
    print(json.dumps(result, ensure_ascii=False, indent=2))
