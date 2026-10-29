#!/usr/bin/env python3
"""本地控制台服务 —— 零第三方依赖。

  python3 server.py            # http://127.0.0.1:8765
  python3 server.py --port 9000 --mock
"""
import argparse, json, queue, sys, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

DEMO = Path(__file__).resolve().parent
sys.path.insert(0, str(DEMO / "A-python"))

import approve, compact, config, llm, loop, policy, session, tools  # noqa: E402

WEB = DEMO / "web"
REGISTRY = json.loads((DEMO / "shared" / "tasks.json").read_text(encoding="utf-8"))

STATE = {
    "running": False,
    "cancel": None,
    "approver": None,
    "messages": [],
    "task": None,
    "last": None,
}
SUBS = []                      # 每个 SSE 客户端一个 Queue
SUBS_LOCK = threading.Lock()
RUN_LOCK = threading.Lock()


def emit(ev):
    ev = dict(ev)
    ev.setdefault("ts", time.time())
    with SUBS_LOCK:
        for q in list(SUBS):
            try:
                q.put_nowait(ev)
            except queue.Full:
                pass


def task_by_id(tid):
    for t in REGISTRY["tasks"]:
        if t["id"] == tid:
            return t
    return REGISTRY["tasks"][0]


def build_cfg(task, mock):
    cfg = config.load()
    if mock:
        cfg["MOCK"] = "true"
    cfg["WORKSPACE_PATH"] = (DEMO / task["fixture"]).resolve()
    cfg["CHECK_PATH"] = (DEMO / task["check"]).resolve()
    cfg["TASK_PATH"] = (DEMO / task["task"]).resolve()
    cfg["MOCK_SCRIPT"] = str((DEMO / task.get("mock", "shared/mock/pomodoro.json")).resolve())
    return cfg


def worker(task, free_text, mock, auto_approve):
    global STATE
    cfg = build_cfg(task, mock)
    prov = approve.WebApprover(emit)
    STATE["approver"] = prov
    cfg["AUTO_YES"] = auto_approve

    sess = session.Session(DEMO / "runs" / "web.jsonl")
    t = tools.Tools(cfg, sess, prov, emit=emit, check_path=cfg["CHECK_PATH"])
    bud = policy.Budget(cfg)
    text = free_text.strip() or cfg["TASK_PATH"].read_text(encoding="utf-8")

    try:
        res = loop.run(cfg, llm.LLM(cfg), t, sess, bud, text,
                       emit=emit, cancel=STATE["cancel"])
        STATE["last"] = res
        STATE["messages"] = res.get("messages", [])
    except Exception as e:
        emit({"type": "error", "message": f"{type(e).__name__}: {e}"})
        STATE["last"] = {"status": "error"}
    finally:
        prov.cancel_all()
        STATE["running"] = False
        STATE["approver"] = None
        emit({"type": "done"})


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    # ---------- 工具 ----------
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode())
        except Exception:
            return {}

    def _file(self, path, ctype="text/html; charset=utf-8"):
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self.send_response(404); self.send_header("Content-Length","0"); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # ---------- GET ----------
    def do_GET(self):
        u = urlparse(self.path)
        p = u.path

        if p in ("/", "/index.html"):
            return self._file(WEB / "console.html")
        if p.startswith("/web/"):
            f = WEB / p[len("/web/"):]
            if f.is_file():
                ct = "text/css" if f.suffix == ".css" else "application/javascript" if f.suffix == ".js" else "text/html; charset=utf-8"
                return self._file(f, ct)
            return self._json({"error": "not found"}, 404)

        if p == "/api/tasks":
            return self._json({"tasks": REGISTRY["tasks"],
                               "mock": STATE.get("mock", False)})

        if p == "/api/workspace":
            from urllib.parse import parse_qs
            tid = (parse_qs(u.query).get("id") or [REGISTRY["tasks"][0]["id"]])[0]
            t = task_by_id(tid)
            ws = (DEMO / t["fixture"]).resolve()
            out = {}
            for f in sorted(ws.iterdir()):
                if f.is_file():
                    out[f.name] = f.read_text(encoding="utf-8")[:20000]
            return self._json({"files": out})

        if p == "/api/context":
            return self._json({"messages": compact.snapshot(STATE["messages"]),
                               "tokens": compact.estimate_tokens(STATE["messages"])})

        if p == "/api/events":
            return self._sse()

        return self._json({"error": "not found"}, 404)

    def _sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = queue.Queue(maxsize=2000)
        with SUBS_LOCK:
            SUBS.append(q)
        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    ev = q.get(timeout=15)
                    payload = json.dumps(ev, ensure_ascii=False)
                    self.wfile.write(f"data: {payload}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with SUBS_LOCK:
                if q in SUBS:
                    SUBS.remove(q)

    # ---------- POST ----------
    def do_POST(self):
        p = urlparse(self.path).path
        body = self._body()

        if p == "/api/run":
            if STATE["running"]:
                return self._json({"error": "已有任务在跑，先停止"}, 409)
            task = task_by_id(body.get("taskId") or REGISTRY["tasks"][0]["id"])
            STATE["running"] = True
            STATE["mock"] = bool(body.get("mock"))
            STATE["cancel"] = threading.Event()
            STATE["messages"] = []
            emit({"type": "clear"})
            threading.Thread(target=worker, daemon=True, args=(
                task, body.get("text") or "", bool(body.get("mock")),
                bool(body.get("autoApprove")))).start()
            return self._json({"ok": True, "task": task["id"]})

        if p == "/api/stop":
            if STATE["cancel"]:
                STATE["cancel"].set()
            if STATE["approver"]:
                STATE["approver"].cancel_all()
            return self._json({"ok": True})

        if p == "/api/approve":
            prov = STATE["approver"]
            ok = bool(prov and prov.decide(body.get("id"), body.get("decision")))
            return self._json({"ok": ok})

        if p == "/api/compact":
            msgs = STATE["messages"]
            if not msgs:
                return self._json({"error": "还没有上下文，先跑一次任务"}, 400)
            keep = int(body.get("keepLast") or 3)
            fake = msgs + [
                {"role": "assistant", "content": "（模拟水位的填充消息）" + "·" * 0}
            ] * 0
            res = compact.compact(msgs, keep_last=keep)
            emit({"type": "compact", "before": res.get("before"),
                  "after": res.get("after"), "ratio": res.get("ratio"),
                  "covered": res.get("covered")})
            return self._json({"ok": True, "result": {
                k: v for k, v in res.items() if k != "messages"},
                "messages": compact.snapshot(res.get("messages") or []),
                "tokens": compact.estimate_tokens(res.get("messages") or [])})

        if p == "/api/context":
            msgs = STATE["messages"]
            return self._json({"messages": compact.snapshot(msgs),
                               "tokens": compact.estimate_tokens(msgs)})

        return self._json({"error": "not found"}, 404)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()
    STATE["mock"] = args.mock
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.daemon_threads = True
    print(f"\n  控制台：http://{args.host}:{args.port}")
    print(f"  模式：{'MOCK（离线）' if args.mock else '真实模型（需 config.env 填 key）'}")
    print("  Ctrl+C 停止\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止")


if __name__ == "__main__":
    main()
