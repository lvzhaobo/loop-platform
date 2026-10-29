"""人工审核 —— 真的停下来等人，不是在日志里写一行"需要审核"。

三种放行方式：
  1. 交互（默认）：终端里 y/n
  2. 自动：REVIEW_AUTO=allow|reject（CI / demo 用）
  3. 超时：REVIEW_TIMEOUT 秒后按 policy 决定（默认 reject，不默认放行）

每次决策都写审计事件，带谁、什么时候、为什么。
"""
from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass, field


@dataclass
class ReviewRequest:
    run_id: str
    kind: str              # gate | delivery | publish | deploy
    title: str
    detail: str = ""
    artifacts: list[str] = field(default_factory=list)


@dataclass
class ReviewDecision:
    allowed: bool
    by: str
    reason: str
    at: float


def _audit(event_store, req: ReviewRequest, dec: ReviewDecision) -> None:
    """把审核决策写进审计。event_store 可为 None（沙箱里不外抛）。"""
    if event_store is None:
        return
    try:
        event_store.append({
            "type": "review_decision", "run_id": req.run_id, "kind": req.kind,
            "title": req.title, "allowed": dec.allowed,
            "by": dec.by, "reason": dec.reason, "ts": dec.at,
        })
    except Exception:
        pass


def request_review(req: ReviewRequest, event_store=None,
                   timeout: int | None = None) -> ReviewDecision:
    timeout = int(timeout or os.environ.get("REVIEW_TIMEOUT", "0"))
    auto = os.environ.get("REVIEW_AUTO", "").strip().lower()

    # ── 1. 自动模式（CI / 无人值守演示）
    if auto in ("allow", "reject"):
        dec = ReviewDecision(auto == "allow", "auto:REVIEW_AUTO",
                             f"REVIEW_AUTO={auto}", time.time())
        _audit(event_store, req, dec)
        return dec

    # ── 2. 交互模式
    print("\n" + "─" * 62)
    print(f"⏸  需要人工审核 · {req.kind}")
    print(f"   run: {req.run_id}")
    print(f"   {req.title}")
    if req.detail:
        for line in req.detail.splitlines()[:12]:
            print(f"   {line}")
    if req.artifacts:
        print(f"   产物: {', '.join(req.artifacts[:6])}")
    print("─" * 62)

    if timeout > 0:
        print(f"   {timeout}s 内无应答将按 policy 自动拒绝")
        holder: dict[str, ReviewDecision] = {}

        def ask():
            try:
                ans = input("   通过？[y/N] ").strip().lower()
                holder["d"] = ReviewDecision(ans in ("y", "yes"), "human",
                                             "交互输入", time.time())
            except EOFError:
                holder["d"] = ReviewDecision(False, "timeout", "无输入", time.time())

        t = threading.Thread(target=ask, daemon=True)
        t.start()
        t.join(timeout)
        dec = holder.get("d") or ReviewDecision(False, "timeout",
                                                f"{timeout}s 无应答", time.time())
    else:
        try:
            ans = input("   通过？[y/N] ").strip().lower()
            dec = ReviewDecision(ans in ("y", "yes"), "human", "交互输入", time.time())
        except EOFError:
            dec = ReviewDecision(False, "no-tty", "非交互环境默认拒绝", time.time())

    _audit(event_store, req, dec)
    print(f"   → {'✅ 通过' if dec.allowed else '⛔ 拒绝'}（{dec.by}）\n")
    return dec
