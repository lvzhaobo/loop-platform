"""通用入口探测。不再把入口文件名写死为 app.py/server.js。

应用由 LLM 自由选择技术栈生成，文件名与语言都可能不同，因此这里按
「常见文件名 → 内容特征 → 静态页面」的顺序识别可运行入口。

detect_entry(dir) 返回 dict 或 None：
  {"kind": "python"|"node"|"static", "file": 相对文件名, "cmd": [启动命令]（static 无）}
"""

import json, os, shutil
from typing import Any

# 各语言常见的服务入口文件名（按优先级）
_PY_NAMES = ["app.py", "main.py", "server.py", "run.py", "wsgi.py", "manage.py", "__main__.py"]
_NODE_NAMES = ["server.js", "index.js", "app.js", "main.js"]
# Python 源码里表明「这是个可启动服务」的特征片段
_PY_MARKERS = ["app.run(", "if __name__", "uvicorn", "FastAPI(", "Flask(", "run_server", "serve("]


def clean_env(port: int) -> dict:
    """给被验收子进程准备干净环境：注入 PORT，并清除父进程(studio)泄漏的 Flask/Werkzeug 变量。

    studio 若经 `flask run` 启动会注入 FLASK_RUN_FROM_CLI=true 并被子进程继承，
    导致被验收的 app.run() 被 Flask 直接忽略，服务永远起不来(Connection refused)；
    WERKZEUG_SERVER_FD 则会让子进程去复用父进程套接字报 Bad file descriptor。
    与 tools/verify.py 的防护保持一致。"""
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["PYTHONUNBUFFERED"] = "1"
    for v in ("WERKZEUG_SERVER_FD", "WERKZEUG_RUN_MAIN",
              "FLASK_RUN_FROM_CLI", "FLASK_APP", "FLASK_DEBUG",
              "FLASK_RUN_PORT", "FLASK_RUN_HOST"):
        env.pop(v, None)
    return env


def wait_http_ready(proc, url: str, timeout: float = 15.0):
    """轮询等待服务就绪：进程存活且 URL 可访问。返回 (resp|None, 诊断信息)。"""
    import time as _t
    import urllib.request as _rq
    deadline = _t.time() + timeout
    last_err = ""
    while _t.time() < deadline:
        if proc.poll() is not None:
            return None, f"入口启动即退出 code={proc.returncode}"
        try:
            return _rq.urlopen(url, timeout=3), ""
        except Exception as e:  # noqa: BLE001
            last_err = str(e)[:80]
            _t.sleep(0.5)
    return None, f"未在 {int(timeout)}s 内就绪: {last_err}"


def _iter_files(target_dir, exts):
    """遍历目录（含一层子目录）下指定扩展名的文件，返回相对路径。"""
    for name in sorted(os.listdir(target_dir)):
        full = os.path.join(target_dir, name)
        if os.path.isfile(full) and name.endswith(exts):
            yield name
    for name in sorted(os.listdir(target_dir)):
        sub = os.path.join(target_dir, name)
        if os.path.isdir(sub) and not name.startswith((".", "__")) and name not in ("node_modules", "venv", ".venv"):
            for f in sorted(os.listdir(sub)):
                if f.endswith(exts) and os.path.isfile(os.path.join(sub, f)):
                    yield os.path.join(name, f)


def _detect_python(target_dir) -> dict[str, Any] | None:
    # 1) 常见文件名优先
    for name in _PY_NAMES:
        if os.path.isfile(os.path.join(target_dir, name)):
            return {"kind": "python", "file": name}
    # 2) 按内容特征扫描 .py（含一层子目录）
    for rel in _iter_files(target_dir, (".py",)):
        try:
            with open(os.path.join(target_dir, rel), encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        if any(m in text for m in _PY_MARKERS):
            return {"kind": "python", "file": rel}
    return None


def _detect_node(target_dir) -> dict[str, Any] | None:
    # 1) package.json 声明的入口（scripts.start / main）
    pkg = os.path.join(target_dir, "package.json")
    if os.path.isfile(pkg):
        try:
            with open(pkg, encoding="utf-8") as f:
                data = json.load(f)
            start = (data.get("scripts") or {}).get("start")
            if start:
                return {"kind": "node", "file": "package.json", "cmd": ["npm", "start"]}
            main = data.get("main")
            if main and os.path.isfile(os.path.join(target_dir, main)):
                return {"kind": "node", "file": main}
        except (OSError, ValueError):
            pass
    # 2) 常见文件名
    for name in _NODE_NAMES:
        if os.path.isfile(os.path.join(target_dir, name)):
            return {"kind": "node", "file": name}
    return None


def _detect_static(target_dir) -> dict[str, Any] | None:
    if os.path.isfile(os.path.join(target_dir, "index.html")):
        return {"kind": "static", "file": "index.html"}
    for rel in _iter_files(target_dir, (".html", ".htm")):
        return {"kind": "static", "file": rel}
    return None


def detect_entry(target_dir) -> dict[str, Any] | None:
    """按 Python → Node → 静态 顺序探测入口，找不到返回 None。"""
    import sys
    py = _detect_python(target_dir)
    if py:
        py.setdefault("cmd", [sys.executable, py["file"]])
        return py
    node = _detect_node(target_dir)
    if node:
        if "cmd" not in node:
            runner = shutil.which("node")
            node["cmd"] = [runner or "node", node["file"]]
        return node
    return _detect_static(target_dir)
