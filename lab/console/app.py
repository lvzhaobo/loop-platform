#!/usr/bin/env python3
"""平台后端骨架 —— 零第三方依赖。

  python3 app.py --port 8787
  python3 verify.py                 # 另开一个终端做端到端自检

四个模块：需求 / 执行 / 审批 / 事件总线，够验证架构了。
"""
import argparse
import json
import queue
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.bus import Bus            # noqa: E402
from core.store import Store        # noqa: E402
from modules import approvals, constraints, coverage, gates, reqs, runs, specs, wbs, workspaces   # noqa: E402

DATA = ROOT / "data"
WEB = ROOT / "web"


class Ctx:
    def __init__(self, mock=True):
        self.bus = Bus(log_path=DATA / "events.jsonl")
        self.store = Store(DATA)
        self.data_dir = DATA
        self.mock = mock


ROUTES = [
    ("POST", r"^/api/admin/reset$",         lambda c, p_, b: (200, _reset(c))),
    ("GET",  r"^/api/health$",              lambda c, p, b: (200, {"ok": True, "modules": ["workspaces", "reqs", "specs", "wbs", "constraints", "gates", "runs", "approvals"]})),
    ("GET",  r"^/api/reqs$",                reqs.list_reqs),
    ("POST", r"^/api/reqs$",                reqs.create_req),
    ("GET",  r"^/api/reqs/(?P<id>[^/]+)$",  reqs.get_req),
    ("PATCH", r"^/api/reqs/(?P<id>[^/]+)$", reqs.patch_req),
    ("GET",  r"^/api/reqs/_/stats$",        reqs.stats),
    ("GET",  r"^/api/coverage$",            coverage.coverage),
    ("GET",  r"^/api/workspaces$",          workspaces.list_workspaces),
    ("GET",  r"^/api/workspaces/(?P<id>[^/]+)/files$", workspaces.files),
    ("POST", r"^/api/runs$",                runs.create_run),
    ("GET",  r"^/api/runs$",                runs.list_runs),
    ("GET",  r"^/api/runs/(?P<id>[^/]+)$",  runs.get_run),
    ("POST", r"^/api/runs/(?P<id>[^/]+)/stop$", runs.stop_run),
    ("POST", r"^/api/specs/generate$",      specs.generate),
    ("GET",  r"^/api/specs$",               specs.list_specs),
    ("GET",  r"^/api/specs/graph$",         specs.graph),
    ("GET",  r"^/api/specs/progress$",      specs.progress),
    ("GET",  r"^/api/specs/engine$",        specs.engine),
    ("GET",  r"^/api/specs/(?P<id>[^/]+)$", specs.get_spec),
    ("POST", r"^/api/specs/(?P<id>[^/]+)/review$",     specs.review),
    ("POST", r"^/api/specs/(?P<id>[^/]+)/regenerate$", specs.regenerate),
    ("POST", r"^/api/gates/run$",           gates.run),
    ("GET",  r"^/api/gates/tasks$",         gates.tasks),
    ("GET",  r"^/api/gates/latest$",        gates.latest),
    ("GET",  r"^/api/gates$",               gates.history),
    ("GET",  r"^/api/constraints$",         constraints.list_constraints),
    ("POST", r"^/api/constraints/check$",   constraints.check),
    ("POST", r"^/api/constraints/patch$",   constraints.patch_file),
    ("POST", r"^/api/wbs/generate$",        wbs.generate),
    ("GET",  r"^/api/wbs$",                 wbs.list_wbs),
    ("GET",  r"^/api/wbs/stale$",           wbs.stale_check),
    ("POST", r"^/api/wbs/(?P<id>[^/]+)/jira$", wbs.push_jira),
    ("POST", r"^/api/jira/push-all$",       wbs.push_all),
    ("GET",  r"^/api/approvals$",           approvals.list_pending),
    ("POST", r"^/api/approvals/(?P<id>[^/]+)$", approvals.decide),
]


def _reset(ctx):
    """演示前清空业务数据（保留事件日志）"""
    import shutil
    cleared = []
    for coll in ("reqs", "specs", "wbs", "gates", "runs"):
        if ctx.store._path(coll).exists():
            ctx.store._path(coll).unlink()
            cleared.append(coll)
    ctx.store._cache.clear()
    sess = ctx.data_dir / "sessions"
    if sess.exists():
        shutil.rmtree(sess, ignore_errors=True)
    ctx.bus.publish({"type": "admin_reset", "cleared": cleared})
    return {"ok": True, "cleared": cleared}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    ctx = None

    def log_message(self, *a):
        pass

    # ---------- 辅助 ----------
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
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

    def _dispatch(self, method):
        u = urlparse(self.path)
        path = u.path
        params = {k: v[0] for k, v in parse_qs(u.query).items()}
        for m, pattern, fn in ROUTES:
            if m != method:
                continue
            hit = re.match(pattern, path)
            if not hit:
                continue
            params.update(hit.groupdict())
            try:
                code, out = fn(self.ctx, params, self._body())
            except Exception as e:
                code, out = 500, {"error": f"{type(e).__name__}: {e}"}
            return self._json(out, code)
        return self._json({"error": "not found", "path": path}, 404)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/events":
            return self._sse()
        if u.path.startswith("/api/"):
            return self._dispatch("GET")
        return self._static(u.path)

    def do_POST(self):  return self._dispatch("POST")
    def do_PATCH(self): return self._dispatch("PATCH")

    # ---------- SSE ----------
    def _sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = self.ctx.bus.subscribe()
        try:
            for ev in self.ctx.bus.replay(0)[-50:]:
                self.wfile.write(f"data: {json.dumps(ev, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()
            while True:
                try:
                    ev = q.get(timeout=15)
                    self.wfile.write(f"data: {json.dumps(ev, ensure_ascii=False)}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.ctx.bus.unsubscribe(q)

    # ---------- 静态 ----------
    def _static(self, path):
        f = WEB / (path.lstrip("/") or "index.html")
        if not f.is_file():
            return self._json({"error": "not found"}, 404)
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--real", action="store_true", help="用真实模型（需 config.env 填 key）")
    args = ap.parse_args()

    Handler.ctx = Ctx(mock=not args.real)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.daemon_threads = True
    print(f"  平台后端  http://{args.host}:{args.port}")
    print(f"  模式      {'真实模型' if args.real else 'MOCK（离线）'}")
    print(f"  数据目录  {DATA}")
    print("  Ctrl+C 停止\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止")


if __name__ == "__main__":
    main()
