"""行前闸门（G1 的最简版）：高危动作前停下来问一句。"""
import sys, threading

def ask(action: str, detail: str, auto_yes: bool = False) -> bool:
    line = f"  [审批] {action}  {detail}"
    if auto_yes:
        print(line + "   → 自动通过（--yes）")
        return True
    print(line)
    if not sys.stdin.isatty():
        print("            → 非交互环境，默认拒绝")
        return False
    try:
        ans = input("           允许吗？[y/N] ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


class WebApprover:
    """浏览器版审批：发一条事件，然后阻塞等前端 POST 回来。"""

    def __init__(self, emit, timeout=300):
        self.emit = emit
        self.timeout = timeout
        self.seq = 0
        self.pending = {}
        self.lock = threading.Lock()

    def __call__(self, action, detail, auto_yes=False):
        if auto_yes:
            self.emit({"type": "approval_auto", "action": action, "detail": detail})
            return True
        with self.lock:
            self.seq += 1
            pid = f"ap{self.seq}"
            ev = threading.Event()
            self.pending[pid] = {"event": ev, "decision": None}
        self.emit({"type": "approval_request", "id": pid,
                   "action": action, "detail": detail})
        ev.wait(timeout=self.timeout)
        with self.lock:
            rec = self.pending.pop(pid, {})
        decision = rec.get("decision") or "timeout"
        self.emit({"type": "approval_decided", "id": pid, "decision": decision})
        return decision == "allow"

    def decide(self, pid, decision):
        with self.lock:
            rec = self.pending.get(pid)
        if not rec:
            return False
        rec["decision"] = decision
        rec["event"].set()
        return True

    def cancel_all(self):
        with self.lock:
            for rec in self.pending.values():
                rec["decision"] = "cancelled"
                rec["event"].set()
