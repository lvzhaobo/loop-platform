"""Loop 结构化日志 / Trace 模块。

写入 output/trace.jsonl，每行一个事件。供 Studio 监控页查询。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

TRACE_FILE = os.environ.get("LOOP_TRACE_FILE", "output/trace.jsonl")


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _write(event: dict) -> None:
    event["_ts"] = _now()
    os.makedirs(os.path.dirname(TRACE_FILE) or ".", exist_ok=True)
    with open(TRACE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


# ---- 公共 API ----

def batch_start(mode: str, cases: str, cost_cap: float) -> None:
    _write({"event": "batch_start", "mode": mode, "cases": cases, "cost_cap": cost_cap})


def batch_end(ok: int, fail: int, cost: float) -> None:
    _write({"event": "batch_end", "ok": ok, "fail": fail, "cost_yuan": round(cost, 4)})


def gen_start(case: str, attempt: int) -> None:
    _write({"event": "gen_start", "case": case, "attempt": attempt})


def gen_done(case: str, attempt: int, files: int, cost: float) -> None:
    _write({"event": "gen_done", "case": case, "attempt": attempt, "files": files, "cost_yuan": round(cost, 4)})


def verify_start(case: str, source: str) -> None:
    _write({"event": "verify_start", "case": case, "source": source})


def verify_done(case: str, passed: int, total: int, ok: bool) -> None:
    _write({"event": "verify_done", "case": case, "passed": passed, "total": total, "ok": ok})


def verify_fail_feedback(case: str, attempt: int) -> None:
    _write({"event": "verify_fail_feedback", "case": case, "attempt": attempt})


def case_done(case: str, result: str, attempts: int, determinism: str, cost: float) -> None:
    _write({"event": "case_done", "case": case, "result": result, "attempts": attempts,
            "determinism": determinism, "cost_yuan": round(cost, 4)})


def guard_cost_cap(case: str, cost: float, cap: float) -> None:
    _write({"event": "guard_cost_cap", "case": case, "cost_yuan": round(cost, 4), "cap": cap})


def guard_stall(case: str) -> None:
    _write({"event": "guard_stall", "case": case})


# ---- 查询 API ----

def query(limit: int = 100, event_type: str | None = None) -> list[dict]:
    """读取最近的 trace 事件。"""
    if not os.path.exists(TRACE_FILE):
        return []
    events: list[dict] = []
    with open(TRACE_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                if event_type and e.get("event") != event_type:
                    continue
                events.append(e)
            except json.JSONDecodeError:
                continue
    return events[-limit:]


def metrics() -> dict:
    """从 trace 聚合效率指标。

    Returns:
        {
            "total_batches": int, "total_cases": int,
            "pass_rate": float, "first_pass_rate": float,
            "total_cost_yuan": float, "avg_attempts": float
        }
    """
    events = query(limit=10000)
    batches = set()
    cases = []
    total_cost = 0.0
    for e in events:
        if e["event"] == "batch_start":
            batches.add(e.get("_ts", ""))
        if e["event"] == "case_done":
            cases.append(e)
            total_cost += e.get("cost_yuan", 0)

    if not cases:
        return {"total_batches": len(batches), "total_cases": 0}

    passed = sum(1 for c in cases if c["result"] == "pass")
    first_pass = sum(1 for c in cases if c["attempts"] == 1 and c["result"] == "pass")

    return {
        "total_batches": len(batches),
        "total_cases": len(cases),
        "pass_rate": round(passed / len(cases) * 100, 1),
        "first_pass_rate": round(first_pass / len(cases) * 100, 1),
        "total_cost_yuan": round(total_cost, 2),
        "avg_attempts": round(sum(c["attempts"] for c in cases) / len(cases), 1),
    }
