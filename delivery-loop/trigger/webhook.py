"""delivery-loop / trigger / webhook.py —— 事件式自动触发器(Event-driven Loop)。

作用
----
把"人手动跑 run_backlog.sh"升级为"外部事件一来就自动跑"。这是 Loop Engineering
里 Self-Triggering 的另一种形态:Polling(poll.sh 主动轮询)之外的 **被动事件驱动**。
典型触发源:GitHub/GitLab webhook(有新 issue/PR)、飞书机器人回调、CI 完成回调,
或最简单的一条 `curl` 手动踢一脚。

定位
----
纯外挂。本服务只做一件事——收到合法请求后 **子进程调用 run_backlog.sh**,
不 import orchestrator.py,不碰 harness-4/5 的任何代码或产物。零第三方依赖(只用 stdlib)。

接口
----
  POST /trigger   触发一批需求池处理。带并发锁:正在跑时再来请求返回 409,不排队堆积。
  GET  /health    健康检查,返回 {"ok": true}。

安全
----
  - 默认只绑 127.0.0.1(见 HARNESS_TRIGGER_HOST),不暴露公网。要对外请自套反向代理。
  - 可选共享密钥:设了 HARNESS_TRIGGER_TOKEN(建议写仓库根 .env)后,
    请求头须带 `X-Trigger-Token: <该值>`,否则 401。留空=不校验(仅限本机内网自测)。

用法
----
  # 启动(前台;默认 sample 离线模式,零密钥)
  python delivery-loop/trigger/webhook.py
  # 另开一个终端手动触发一批:
  curl -X POST http://127.0.0.1:8787/trigger
  # 带密钥时:
  curl -X POST http://127.0.0.1:8787/trigger -H "X-Trigger-Token: 你的密钥"

环境变量(见 config.env)
  HARNESS_TRIGGER_HOST   监听地址(默认 127.0.0.1)
  HARNESS_TRIGGER_PORT   监听端口(默认 8787)
  HARNESS_TRIGGER_TOKEN  共享密钥(默认空=不校验)
  其余开关(HARNESS_MODE / HARNESS_BACKLOG_SOURCE / HARNESS_AUTOCOMMIT ...)由 run_backlog.sh 自行读取
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# --- 定位路径:trigger/ 上一级是 delivery-loop,再上一级是仓库根 ---
TRIGGER_DIR = os.path.dirname(os.path.abspath(__file__))
DL_DIR = os.path.dirname(TRIGGER_DIR)
ROOT = os.path.dirname(DL_DIR)
RUN_BACKLOG = os.path.join(DL_DIR, "run_backlog.sh")
INDEX_HTML = os.path.join(TRIGGER_DIR, "index.html")

HOST = os.environ.get("HARNESS_TRIGGER_HOST", "127.0.0.1")
PORT = int(os.environ.get("HARNESS_TRIGGER_PORT", "8787") or 8787)
TOKEN = os.environ.get("HARNESS_TRIGGER_TOKEN", "") or ""

# --- 并发锁:同一时刻只允许一批在跑,避免同一 case 并行生成、产物互相踩踏 ---
# 与 poll.sh 的作用相同,这里用进程内的 threading.Lock 即可(webhook 是单进程多线程)。
_run_lock = threading.Lock()


def _trigger_batch() -> dict:
    """拿锁 → 子进程调 run_backlog.sh → 释放锁。拿不到锁说明有一批在跑。"""
    if not _run_lock.acquire(blocking=False):
        # 已有一批在运行:不排队,直接告知 busy(对应 HTTP 409)
        return {"ok": False, "busy": True, "reason": "上一批仍在运行,本次请求被忽略。"}
    try:
        started = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[webhook {started}] ▶ 触发一批:bash {RUN_BACKLOG}")
        # 纯子进程调用:继承当前环境(含各开关),cwd 设仓库根与 run_backlog.sh 预期一致
        proc = subprocess.run(["bash", RUN_BACKLOG], cwd=ROOT)
        finished = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[webhook {finished}] ✔ 本批结束(exit={proc.returncode})。")
        return {"ok": proc.returncode == 0, "exit_code": proc.returncode,
                "started_at": started, "finished_at": finished}
    finally:
        _run_lock.release()


class Handler(BaseHTTPRequestHandler):
    # 静音默认访问日志(我们自己打更有意义的日志)
    def log_message(self, *_args):  # noqa: D401
        pass

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, code: int, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        # 未配置 TOKEN → 不校验(仅本机自测场景);配置了 → 请求头必须匹配
        if not TOKEN:
            return True
        return self.headers.get("X-Trigger-Token", "") == TOKEN

    def do_GET(self):  # noqa: N802 (stdlib 约定的方法名)
        path = self.path.split("?", 1)[0].rstrip("/")
        if path in ("", "/index.html"):
            # 根路径回一个极简“跑一批”按钮页(前端直接 POST /trigger)
            try:
                with open(INDEX_HTML, encoding="utf-8") as f:
                    self._send_html(200, f.read())
            except OSError:
                self._send(404, {"ok": False, "reason": "index.html 缺失"})
        elif path == "/health":
            self._send(200, {"ok": True})
        else:
            self._send(404, {"ok": False, "reason": "未知路径,可用:GET /、GET /health、POST /trigger"})

    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/") != "/trigger":
            self._send(404, {"ok": False, "reason": "未知路径,可用:POST /trigger"})
            return
        if not self._authorized():
            self._send(401, {"ok": False, "reason": "缺少或错误的 X-Trigger-Token"})
            return
        # 读掉请求体(GitHub 等会带 payload;当前最小版不解析内容,只作为"触发信号")
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length:
            self.rfile.read(length)
        result = _trigger_batch()
        # busy → 409;正常 → 200
        self._send(409 if result.get("busy") else 200, result)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    token_hint = "已启用(需带 X-Trigger-Token)" if TOKEN else "未设(仅限本机自测)"
    print(f"[webhook] 监听 http://{HOST}:{PORT}  鉴权:{token_hint}")
    print(f"[webhook] 触发:curl -X POST http://{HOST}:{PORT}/trigger")
    print("[webhook] Ctrl-C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[webhook] 收到退出信号,停止。")
        server.shutdown()


if __name__ == "__main__":
    main()
