#!/usr/bin/env python3
"""
MumuLoop 平台服务（形态 2：沙箱服务化）—— Flask 骨架

职责：
  1. 静态托管 web/ 控制台
  2. REST API：读 data/logs/ 下 JSONL（schema 与课程素材 loop/ 一致），
     按 aggregate.py 口径聚合出 概览 / 运行 / 检查 / 工单 / Trace 数据
  3. 不改造任何脚本；后续接入 loop.py 采用 subprocess 薄包（P1）

启动：
  python3 platform/server/app.py
  浏览器打开 http://127.0.0.1:8787

配置（环境变量，均可选）：
  MUMULOOP_PORT   端口，默认 8787
  MUMULOOP_LOGS   日志目录，默认 platform/data/logs
  LANGFUSE_URL    LangFuse 地址（Trace 页外链，未配置则不显示）
"""

import json
import os
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

BASE = Path(__file__).resolve().parent          # platform/server
PLATFORM = BASE.parent                          # platform
WEB = PLATFORM / "web"
LOGS = Path(os.environ.get("MUMULOOP_LOGS") or (PLATFORM / "data" / "logs"))
LANGFUSE_URL = os.environ.get("LANGFUSE_URL", "")
PORT = int(os.environ.get("MUMULOOP_PORT", "8787"))

app = Flask(__name__, static_folder=str(WEB), static_url_path="")

# 「收敛」判定：任务末轮 result == closed（与课程素材 aggregate.py 一致）
CLOSED = "closed"


def task_key(stem: str) -> str:
    """loop-20261016 -> loop；content-publish-20261013 -> content-publish"""
    parts = stem.split("-")
    if parts and parts[-1].isdigit() and len(parts[-1]) == 8:
        return "-".join(parts[:-1])
    return stem


def load_entries():
    """读取全部 JSONL 日志（含子目录），附加任务名 / 日期 / 来源标记"""
    entries = []
    if not LOGS.exists():
        return entries
    for lf in sorted(LOGS.rglob("*.jsonl")):
        stem = lf.stem
        for line in lf.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            e["_task"] = task_key(stem)
            e["_day"] = stem.split("-")[-1]
            e["_demo"] = "sample-multi" in lf.parts
            e["_file"] = str(lf.relative_to(LOGS))
            entries.append(e)
    return entries


def group_by_task(entries):
    tasks = {}
    for e in entries:
        tasks.setdefault(e["_task"], []).append(e)
    for es in tasks.values():
        es.sort(key=lambda x: (x["ts"], x["round"]))
    return tasks


@app.get("/api/overview")
def api_overview():
    entries = load_entries()
    tasks = group_by_task(entries)
    total_hits = sum(e["violations"] for e in entries)
    pending = sum(es[-1]["violations"] for es in tasks.values())
    by_rule, by_day = {}, {}
    for e in entries:
        by_day[e["_day"]] = by_day.get(e["_day"], 0) + e["violations"]
        for k, n in e.get("byRule", {}).items():
            by_rule[k] = by_rule.get(k, 0) + n
    converged = sum(1 for es in tasks.values() if es[-1]["result"] == CLOSED)
    effective = total_hits - pending
    return jsonify({
        "tasks": len(tasks),
        "rounds": len(entries),
        "converged": converged,
        "total_hits": total_hits,
        "pending": pending,
        "effective_rate": round(effective * 100 / total_hits) if total_hits else None,
        "by_rule": [{"rule": k, "count": n}
                    for k, n in sorted(by_rule.items(), key=lambda x: -x[1])],
        "by_day": [{"day": k, "count": by_day[k]} for k in sorted(by_day)],
        "recent": sorted(entries, key=lambda x: x["ts"], reverse=True)[:8],
        "files": len({e["_file"] for e in entries}),
        "demo_rounds": sum(1 for e in entries if e["_demo"]),
    })


@app.get("/api/runs")
def api_runs():
    entries = load_entries()
    tasks = group_by_task(entries)
    out = []
    for name, es in sorted(tasks.items()):
        out.append({
            "task": name,
            "rounds": len(es),
            "total_hits": sum(e["violations"] for e in es),
            "last_result": es[-1]["result"],
            "last_ts": es[-1]["ts"],
            "days": sorted({e["_day"] for e in es}),
            "entries": es,
        })
    return jsonify(out)


@app.get("/api/checks")
def api_checks():
    entries = load_entries()
    by_rule, seq = {}, []
    for e in entries:
        for k, n in e.get("byRule", {}).items():
            by_rule[k] = by_rule.get(k, 0) + n
        if e["violations"]:
            seq.append({"ts": e["ts"], "task": e["_task"], "round": e["round"],
                        "violations": e["violations"], "byRule": e.get("byRule", {})})
    return jsonify({
        "by_rule": [{"rule": k, "count": n}
                    for k, n in sorted(by_rule.items(), key=lambda x: -x[1])],
        "seq": sorted(seq, key=lambda x: x["ts"], reverse=True),
    })


@app.get("/api/tickets")
def api_tickets():
    """票据视图（工单桥未接入前的雏形）：从日志推导待处理与历史提票记录"""
    entries = load_entries()
    tasks = group_by_task(entries)
    open_tasks, history = [], []
    for name, es in sorted(tasks.items()):
        last = es[-1]
        if last["result"] != CLOSED:
            open_tasks.append({"task": name, "status": last["result"], "rounds": len(es)})
        for e in es:
            action = e.get("action", "")
            # feedback_written：课程素材 loop.py 口径；ticket_written：平台形态 1 CLI 口径
            for prefix in ("feedback_written:", "ticket_written:"):
                if action.startswith(prefix):
                    history.append({"task": name, "round": e["round"], "ts": e["ts"],
                                    "feedback": action.split(":", 1)[1],
                                    "violations": e["violations"]})
                    break
    return jsonify({
        "open": open_tasks,
        "history": sorted(history, key=lambda x: x["ts"], reverse=True),
        "bridge": "未接入（待决：Jira / 禅道）",
    })


@app.get("/api/trace")
def api_trace():
    entries = load_entries()
    return jsonify({
        "langfuse_url": LANGFUSE_URL,
        "entries": sorted(entries, key=lambda x: x["ts"], reverse=True),
    })


@app.get("/api/settings")
def api_settings():
    entries = load_entries()
    return jsonify({
        "version": "v0.1（骨架）",
        "logs_dir": str(LOGS),
        "files": len({e["_file"] for e in entries}),
        "rounds": len(entries),
        "port": PORT,
        "langfuse_url": LANGFUSE_URL,
        "metrics": {
            "拦截次数": "每轮 violations 之和",
            "有效拦截率": "(拦截总次数 - 末轮残留) / 拦截总次数",
            "收敛判定": "任务末轮 result == closed（与课程素材 aggregate.py 口径一致）",
        },
        "todo": [
            "工单桥对接（Jira / 禅道，待选型）",
            "loop.py 触发接入（P1 沙箱形态，subprocess 薄包）",
            "LangFuse 跳转配置（LANGFUSE_URL）",
        ],
    })


@app.get("/")
def index():
    return send_from_directory(WEB, "index.html")


if __name__ == "__main__":
    print(f"MumuLoop 控制台: http://127.0.0.1:{PORT}")
    print(f"日志目录: {LOGS}")
    app.run(host="127.0.0.1", port=PORT, debug=False)
