"""审批模块 —— 长任务线程真的会停下来等 HTTP。

这是四个模块里最难的一个：agent 跑到高危动作时，工作线程必须阻塞，
直到浏览器（或 curl）POST 一个决定。
实现：threading.Event，不轮询。
"""
import threading
import time

PENDING = {}          # id -> {"event":Event, "decision":None, "meta":{...}}
_lock = threading.Lock()
_seq = 0


class HttpApprover:
    """满足 demo/loop 的调用约定：approver(action, detail) -> bool"""

    def __init__(self, bus, run_id, timeout=180):
        self.bus = bus
        self.run_id = run_id
        self.timeout = timeout

    def __call__(self, action, detail, auto_yes=False):
        global _seq
        if auto_yes:
            self.bus.publish({"type": "approval_auto", "run": self.run_id,
                              "action": action, "detail": detail})
            return True

        with _lock:
            _seq += 1
            aid = f"ap-{_seq:03d}"
            ev = threading.Event()
            PENDING[aid] = {"event": ev, "decision": None,
                            "meta": {"id": aid, "run": self.run_id,
                                     "action": action, "detail": detail,
                                     "created_at": time.time()}}

        self.bus.publish({"type": "approval_request", "id": aid, "run": self.run_id,
                          "action": action, "detail": detail})
        ev.wait(timeout=self.timeout)

        with _lock:
            rec = PENDING.pop(aid, None)
        decision = (rec or {}).get("decision") or "timeout"
        self.bus.publish({"type": "approval_decided", "id": aid,
                          "run": self.run_id, "decision": decision})
        return decision == "allow"


def list_pending(ctx, params, body):
    with _lock:
        return 200, {"pending": [r["meta"] for r in PENDING.values()]}


def decide(ctx, params, body):
    """POST /api/approvals/<id>  {"decision": "allow" | "reject"}"""
    aid = params["id"]
    decision = (body or {}).get("decision")
    if decision not in ("allow", "reject"):
        return 400, {"error": "decision 必须是 allow 或 reject"}
    with _lock:
        rec = PENDING.get(aid)
    if not rec:
        return 404, {"error": f"没有待批项 {aid}"}
    rec["decision"] = decision
    rec["event"].set()
    return 200, {"ok": True, "id": aid, "decision": decision}


def cancel_all():
    with _lock:
        for rec in PENDING.values():
            rec["decision"] = "cancelled"
            rec["event"].set()
