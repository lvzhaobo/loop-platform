#!/usr/bin/env python3
"""长程任务 · 上下文水位 · 断点续跑 —— 三合一实验器。

    python3 pipeline/long_task.py run  --task "…"              # 跑一次长的
    python3 pipeline/long_task.py run  --task "…" --kill-after 90   # 跑一半杀掉
    python3 pipeline/long_task.py resume --session <id> "继续做完"   # 续跑
    python3 pipeline/long_task.py show --session <id>          # 看水位曲线

观测来源（DSH 原生，不用改它）：
  dsh --json          → 实时事件流（tool_call / text / final）
  ~/.dsh/sessions/<cwd>/<id>/session.v4.jsonl.zstd
                      → 每步 usage.totalTokens（水位）+ agent/inbox/spliced（压缩）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

DSH = os.environ.get("DSH_BIN", "dsh")
PROFILE = os.environ.get("DSH_MAKER_PROFILE", "headless")


def sessions_root(workdir: Path) -> Path:
    """DSH 的会话目录 key = 绝对路径里的 / 全换成 -，去掉开头连字符再包 --。"""
    p = str(workdir).replace("/", "-").lstrip("-")
    return Path.home() / ".dsh" / "sessions" / f"--{p}--"


def find_session(workdir: Path, sid: str) -> Path | None:
    d = sessions_root(workdir) / sid / "session.v4.jsonl.zstd"
    if d.exists():
        return d
    root = Path.home() / ".dsh" / "sessions"
    if root.exists():
        for hit in root.glob(f"*/{sid}/session.v4.jsonl.zstd"):
            return hit
    return None


def read_log(p: Path) -> list[dict]:
    if not p.exists():
        return []
    raw = subprocess.run(["zstd", "-dc", str(p)], capture_output=True).stdout
    if not raw:
        return []
    out = []
    for line in raw.decode("utf-8", "replace").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def watermark(events: list[dict]) -> list[dict]:
    """每步的上下文水位 + 压缩事件。"""
    rows, splices = [], []
    for e in events:
        t = e.get("type", "")
        d = e.get("data", {}) or {}
        if t == "assistant/message":
            u = d.get("usage") or {}
            rows.append({"step": d.get("step"), "turn": d.get("turn"),
                         "in": u.get("inputTokens", 0), "out": u.get("outputTokens", 0),
                         "cache": u.get("cacheReadTokens", 0),
                         "total": u.get("totalTokens", 0)})
        elif t == "agent/inbox/spliced":
            removed = d.get("removedCount", 0)
            inserted = len(d.get("inserted") or [])
            if removed or inserted:
                splices.append({"seq": e.get("seq"), "removed": removed,
                                "inserted": inserted, "target": d.get("target", "")})
    return rows, splices


def cmd_run(a) -> int:
    work = Path(a.workdir).expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)
    argv = [DSH, "--profile", PROFILE, "--json"]
    if a.session:
        argv += ["--session-id", a.session]
    argv.append(a.task)

    env = dict(os.environ)
    # 必须覆盖：config.env 里常带着错误的 /chat/completions base
    env["DEEPSEEK_BASE_URL"] = os.environ.get(
        "DSH_BASE_URL", "https://api.deepseek.com/anthropic")

    print(f"▶ {DSH} --profile {PROFILE} --json  (cwd={work})")
    t0 = time.time()
    proc = subprocess.Popen(argv, cwd=str(work), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env, bufsize=1)
    sid, kills = None, a.kill_after
    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            t = e.get("type")
            if t == "session":
                sid = e.get("sessionId")
                print(f"  session: {sid}")
            elif t == "tool_call":
                print(f"  → {e.get('tool')}({json.dumps(e.get('input', {}), ensure_ascii=False)[:70]})")
            elif t == "final":
                print(f"  最终: {(e.get('text') or '')[:120]}")
            if kills and time.time() - t0 > kills:
                print(f"\n⏹ 已运行 {kills}s，主动杀掉（模拟中断）")
                proc.kill()
                break
    finally:
        proc.wait(timeout=30)

    elapsed = time.time() - t0
    print(f"\n用时 {elapsed:.1f}s  退出码 {proc.returncode}")
    if proc.returncode != 0 and proc.stderr:
        err = [l for l in proc.stderr.read().splitlines()
               if "disabling profile plugin" not in l and "Exact-version" not in l]
        if err:
            print("  stderr:", " / ".join(err[-4:])[:400])
    if sid:
        print(f"续跑命令： python3 pipeline/long_task.py resume --session {sid} \"继续\"")
        return cmd_show(argparse.Namespace(workdir=str(work), session=sid))
    return 0


def cmd_show(a) -> int:
    work = Path(a.workdir).expanduser().resolve()
    p = find_session(work, a.session)
    if not p:
        print(f"找不到会话 {a.session}（在 {sessions_root(work)}）", file=sys.stderr)
        return 1
    rows, splices = watermark(read_log(p))
    if not rows:
        print("会话里没有 assistant/message，可能是空跑")
        return 1

    print(f"\n═══ 上下文水位 · {a.session} ═══")
    print(f"{'步':<4}{'输入':>8}{'输出':>8}{'缓存读':>10}{'总计':>10}   水位")
    peak = max(r["total"] for r in rows) or 1
    for r in rows:
        bar = "█" * max(1, round(r["total"] / peak * 28))
        print(f"{r['step']:<4}{r['in']:>8}{r['out']:>8}{r['cache']:>10}{r['total']:>10}   {bar}")
    print(f"\n峰值 {peak} tokens ｜ {len(rows)} 步")

    real = [s for s in splices if s["removed"] > 0]
    print(f"\n上下文拼接事件 {len(splices)} 次（其中移除内容的 {len(real)} 次）")
    for s in splices[:10]:
        print(f"  seq {s['seq']:<4} removed={s['removed']:<3} inserted={s['inserted']:<3} target={s['target']}")
    if not real:
        print("  ⚠️ 没有观察到真正的压缩（上下文没到阈值，或任务太短）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--task", required=True)
    r.add_argument("--workdir", default=".")
    r.add_argument("--session", default="")
    r.add_argument("--kill-after", type=int, default=0)
    s = sub.add_parser("show")
    s.add_argument("--session", required=True)
    s.add_argument("--workdir", default=".")
    rs = sub.add_parser("resume")
    rs.add_argument("--session", required=True)
    rs.add_argument("task")
    rs.add_argument("--workdir", default=".")
    a = ap.parse_args()
    if a.cmd == "run":
        return cmd_run(a)
    if a.cmd == "show":
        return cmd_show(a)
    return cmd_run(argparse.Namespace(task=a.task, workdir=a.workdir,
                                      session=a.session, kill_after=0))


if __name__ == "__main__":
    sys.exit(main())
