"""Harness-4 配置工作台后端。

用途:通过 HTML 表单可视化配置 harness-4 的事实源(constraints.json + cases/<c>/case.json),
保存时自动派生三份 spec/*.md;并提供自洽性实时预检与门禁一键触发。

⚠️ 已知架构冲突(待重构,暂保留)：
    本 studio 的方向是 case 表单 -> render_all_specs 派生 spec（case 当源）,
    与仓库已切换到的新模型 spec -> compile_spec.py -> case（spec 才是唯一真源）**正好相反**。
    因此 studio 仍自带一份反向的 in-memory 校验 spec_render.check_consistency（不依赖已删的
    tools/check_consistency.py,不会崩）;但它让 studio 成了与新模型共存的"第二真源"。
    彻底修复 = 把 studio 也翻成 spec->case(表单编辑 spec 表格而非 case),改动较大,故本轮未做。

运行:
    source .venv/bin/activate
    python harness-4/studio/server.py            # http://127.0.0.1:5100
"""
from __future__ import annotations

import glob
import hmac
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time

from flask import (Flask, jsonify, redirect, render_template, request,
                   send_file, session, url_for)

STUDIO_DIR = os.path.dirname(os.path.abspath(__file__))
if STUDIO_DIR not in sys.path:
    sys.path.insert(0, STUDIO_DIR)
import spec_render  # noqa: E402  (脚本方式运行,依赖 STUDIO_DIR 在 sys.path)

HARNESS_DIR = os.path.dirname(STUDIO_DIR)
CASES_DIR = os.path.join(HARNESS_DIR, "cases")
CONSTRAINTS_PATH = os.path.join(HARNESS_DIR, "constraints.json")

# 一键交付入口:仓库根 / delivery-loop / run_backlog.sh(它自己 source config.env + .env)
REPO_ROOT = os.path.dirname(HARNESS_DIR)
RUN_BACKLOG = os.path.join(REPO_ROOT, "delivery-loop", "run_backlog.sh")

# 12 菜单 Loop Platform 前端(单文件自包含 HTML),默认在仓库根 loop-platform/index.html。
# 由本服务在 / 直接 serve,使前端与 /api/* 同源,登录后 session cookie 自动带上,不再 401。
PLATFORM_HTML = os.environ.get("LOOP_PLATFORM_HTML") or os.path.join(
    REPO_ROOT, "loop-platform", "index.html")

# 点“开始交付”时默认跑的完整链路开关(仅当外部环境未显式设置时才兜底,尊重已导出的覆盖)。
# 与 deploy/loop-platform.service 的 Environment 块保持一致:飞书源 + 真实 LLM + 推 GitHub。
# ECS 部署交给 loop-sample 仓的 GitHub Actions(本地 ECS_DEPLOY 保持 0),密钥由 run_backlog.sh 从 .env 读。
_DELIVERY_DEFAULTS = {
    "HARNESS_BACKLOG_SOURCE": "feishu",
    "HARNESS_MODE": "real",
    "HARNESS_AUTOCOMMIT": "1",
    "HARNESS_GIT_PUSH": "1",
    "HARNESS_GIT_SUBDIR_AUTO": "1",
    "HARNESS_GIT_REMOTE": "github.com/lvzhaobo/loop-sample.git",
}

app = Flask(__name__, template_folder=os.path.join(STUDIO_DIR, "templates"),
            static_folder=os.path.join(STUDIO_DIR, "static"))

# ---------------------------------------------------------------------------
# 访问门禁(纯新增):设了环境变量 STUDIO_TOKEN 就开启口令保护,未设=保持旧行为(本机开发无门禁)。
# 口令只来自环境变量,绝不写进代码或仓库。会话签名密钥 STUDIO_SECRET 未设则每次启动随机。
# ---------------------------------------------------------------------------
STUDIO_TOKEN = os.environ.get("STUDIO_TOKEN", "").strip()
app.secret_key = os.environ.get("STUDIO_SECRET") or os.urandom(24)


@app.before_request
def _auth_guard():
    """未设 STUDIO_TOKEN 时直接放行(兼容本机);设了则:已登录会话/头 X-Studio-Token/参数 ?token= 命中放行,
    否则 /api/* 返 401,页面重定向 /login。"""
    if not STUDIO_TOKEN:
        return None
    p = request.path
    if p == "/login" or p == "/healthz" or p.startswith("/static/"):
        return None
    if session.get("auth"):
        return None
    supplied = request.headers.get("X-Studio-Token", "") or request.args.get("token", "")
    if supplied and hmac.compare_digest(supplied, STUDIO_TOKEN):
        return None
    if p.startswith("/api/"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    """口令登录:命中 STUDIO_TOKEN 则在会话里置 auth=True。未开启门禁时直接回首页。"""
    if not STUDIO_TOKEN:
        return redirect("/")
    if request.method == "POST":
        tok = (request.form.get("token") or "").strip()
        if hmac.compare_digest(tok, STUDIO_TOKEN):
            session["auth"] = True
            return redirect("/")
        return render_template("login.html", error="口令错误，请重试"), 401
    return render_template("login.html", error="")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/healthz")
def healthz():
    """探活端点(不需鉴权):部署自测/公网探活用。"""
    return jsonify({"ok": True, "auth": bool(STUDIO_TOKEN)})


# 允许 loop-platform 原型(另一端口的静态站)跨域读写本工作台 API。
# 本服务仅绑定 127.0.0.1(见 __main__),故放开 CORS 只影响本机开发,安全。
@app.after_request
def _add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


# ---------------------------------------------------------------------------
# 基础 IO
# ---------------------------------------------------------------------------
def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _read_text(path):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def _list_case_names():
    if not os.path.isdir(CASES_DIR):
        return []
    return sorted(
        name for name in os.listdir(CASES_DIR)
        if os.path.exists(os.path.join(CASES_DIR, name, "case.json"))
    )


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """默认入口:12 菜单 Loop Platform 前端(登录门禁后同源访问 /api/*)。
    找不到平台文件时回退旧的配置工作台,保证不影响老用法。"""
    if os.path.exists(PLATFORM_HTML):
        return send_file(PLATFORM_HTML)
    return render_template("index.html")


@app.route("/studio")
def studio_workbench():
    """旧的 3 面板配置工作台(需求/用例/约束表单编辑),保留备用。"""
    return render_template("index.html")


# ---------------------------------------------------------------------------
# 全局 constraints
# ---------------------------------------------------------------------------
@app.route("/api/constraints", methods=["GET"])
def get_constraints():
    return jsonify(_read_json(CONSTRAINTS_PATH))


@app.route("/api/constraints", methods=["POST"])
def save_constraints():
    data = request.get_json(force=True)
    # 始终以磁盘上实际存在的用例目录为准,避免登记漂移
    data["cases"] = _list_case_names()
    _write_json(CONSTRAINTS_PATH, data)
    return jsonify({"ok": True, "constraints": data})


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------
@app.route("/api/cases", methods=["GET"])
def list_cases():
    return jsonify({"cases": _list_case_names()})


@app.route("/api/case/<name>", methods=["GET"])
def get_case(name):
    cdir = os.path.join(CASES_DIR, name)
    case_path = os.path.join(cdir, "case.json")
    if not os.path.exists(case_path):
        return jsonify({"error": f"用例 {name} 不存在"}), 404
    return jsonify({
        "case": _read_json(case_path),
        "specs": {
            "data-model.md": _read_text(os.path.join(cdir, "spec", "data-model.md")),
            "api-contract.md": _read_text(os.path.join(cdir, "spec", "api-contract.md")),
            "ui-spec.md": _read_text(os.path.join(cdir, "spec", "ui-spec.md")),
        },
    })


@app.route("/api/validate", methods=["POST"])
def validate_case():
    """实时预检:根据当前表单 case 派生 spec 并跑自洽性,不落盘。"""
    case = request.get_json(force=True)
    try:
        specs = spec_render.render_all_specs(case)
        fails = spec_render.check_consistency(case, specs)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "fails": [f"渲染失败: {exc}"], "specs": {}})
    return jsonify({"ok": not fails, "fails": fails, "specs": specs})


@app.route("/api/case/<name>", methods=["POST"])
def save_case(name):
    """写 case.json + 三份派生 spec,并把用例登记进 constraints.cases。

    ⚠️ 方向与仓库新模型相反(见模块顶部注释):这里是 case -> spec;
    新模型是 spec(data-model/api-contract/ui-spec 表格) -> compile_spec.py -> case。
    若用 studio 保存,产出的 spec 会被下次 compile_spec 视为源;两边同时手改会冲突。
    待将 studio 翻成 spec->case 后可消除此注释。
    """
    case = request.get_json(force=True)
    case["name"] = name
    specs = spec_render.render_all_specs(case)
    fails = spec_render.check_consistency(case, specs)

    cdir = os.path.join(CASES_DIR, name)
    os.makedirs(os.path.join(cdir, "spec"), exist_ok=True)
    _write_json(os.path.join(cdir, "case.json"), case)
    for fname, text in specs.items():
        with open(os.path.join(cdir, "spec", fname), "w", encoding="utf-8") as f:
            f.write(text)

    # 同步 constraints.cases(以磁盘目录为准)
    constraints = _read_json(CONSTRAINTS_PATH)
    constraints["cases"] = _list_case_names()
    _write_json(CONSTRAINTS_PATH, constraints)

    return jsonify({"ok": not fails, "fails": fails, "written": name})


@app.route("/api/case/<name>", methods=["DELETE"])
def delete_case(name):
    import shutil
    cdir = os.path.join(CASES_DIR, name)
    if not os.path.isdir(cdir):
        return jsonify({"error": f"用例 {name} 不存在"}), 404
    shutil.rmtree(cdir)
    constraints = _read_json(CONSTRAINTS_PATH)
    remaining = _list_case_names()
    constraints["cases"] = remaining
    constraints["run_cases"] = [c for c in constraints.get("run_cases", []) if c in remaining]
    _write_json(CONSTRAINTS_PATH, constraints)
    return jsonify({"ok": True, "cases": remaining})


# ---------------------------------------------------------------------------
# 门禁触发(真正生效层:先接入最便宜的自洽性关,完整 gate 可后续打开)
# ---------------------------------------------------------------------------
@app.route("/api/gate/consistency", methods=["POST"])
def run_consistency_gate():
    """跑真实的 tools/compile_spec.py --check(spec 为唯一源,校验 case.json 派生忠实)。无需 API 额度。"""
    proc = subprocess.run(
        [sys.executable, os.path.join(HARNESS_DIR, "tools", "compile_spec.py"), "--check"],
        capture_output=True, text=True, cwd=HARNESS_DIR,
    )
    return jsonify({
        "ok": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    })


# ---------------------------------------------------------------------------
# 一键交付触发(继承 delivery-loop/trigger/webhook.py 的"子进程调 run_backlog.sh + 并发锁"思路)
# 差别:studio 里跑完整流水线可能数分钟,故放**后台线程**执行,前端轮询 /api/trigger/status。
# 纯新增,不改动上面任何配置/门禁路由;不 import orchestrator,仍把 harness-4 引擎当黑盒。
# ---------------------------------------------------------------------------
_trigger_lock = threading.Lock()
_trigger_state = {
    "running": False,
    "exit_code": None,
    "started_at": None,
    "finished_at": None,
    "log": "",
}


def _run_backlog_bg(extra_env=None):
    """后台线程:子进程跑 delivery-loop/run_backlog.sh(它自己 source config.env + .env),
    实时把输出累积到 _trigger_state['log']。锁在 /api/trigger 里 acquire,这里 finally 释放。
    extra_env:本次请求的显式覆盖(如指定 HARNESS_ONLY_TASK / HARNESS_MODE),优先于默认值。"""
    env = dict(os.environ)
    for k, v in _DELIVERY_DEFAULTS.items():
        env.setdefault(k, v)  # 仅兜底:已导出的同名变量优先
    if extra_env:
        env.update(extra_env)  # 本次请求的选择强制生效(覆盖默认)
    try:
        proc = subprocess.Popen(
            ["bash", RUN_BACKLOG], cwd=REPO_ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        for line in proc.stdout or ():
            _trigger_state["log"] += line
        proc.wait()
        _trigger_state["exit_code"] = proc.returncode
    except Exception as exc:  # noqa: BLE001
        _trigger_state["log"] += f"\n[studio] 触发失败: {exc}\n"
        _trigger_state["exit_code"] = -1
    finally:
        _trigger_state["running"] = False
        _trigger_state["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _trigger_lock.release()


@app.route("/api/trigger", methods=["POST"])
def trigger_delivery():
    """点"开始交付":后台跑完整 run_backlog.sh(飞书→编译→生成→验收→推→部署)。
    可选 body:{task:"FS-002"}只交付该条,缺省整池;{mode:"sample|real"}覆盖模式。
    正在跑时返回 409(不排队),对齐 webhook 的 busy 语义。"""
    if not _trigger_lock.acquire(blocking=False):
        return jsonify({"ok": False, "busy": True, "reason": "上一批仍在运行"}), 409
    body = request.get_json(silent=True) or {}
    extra = {}
    only = str(body.get("task", "")).strip()
    if only:
        extra["HARNESS_ONLY_TASK"] = only
    mode = str(body.get("mode", "")).strip()
    if mode in ("sample", "real"):
        extra["HARNESS_MODE"] = mode
    scope = only or "整池"
    _trigger_state.update({
        "running": True, "exit_code": None,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": None,
        "log": f"[studio] 发起交付 范围={scope} 模式={mode or _DELIVERY_DEFAULTS['HARNESS_MODE']}\n",
    })
    threading.Thread(target=_run_backlog_bg, args=(extra,), daemon=True).start()
    return jsonify({"ok": True, "started_at": _trigger_state["started_at"], "scope": scope})


@app.route("/api/trigger/status", methods=["GET"])
def trigger_status():
    """前端轮询:回当前交付批次的运行状态与实时日志。"""
    return jsonify(_trigger_state)


# ---------------------------------------------------------------------------
# 已部署应用列表(APP List):扫描拉取式部署目录 <ECS_REMOTE_DIR>/<repo>/sampleN,
# 端口 = 1000 + N(与 loop-sample 的 deploy.yml 及 publisher 完全对齐),本机 127.0.0.1
# 探活得 online。studio 本就跑在 ECS 同机,apps 目录在本地,故纯只读、不 SSH。
# 本机开发无该目录时回空列表(前端据此回退旧的静态示例卡,不报错)。
# ---------------------------------------------------------------------------
def _apps_dir():
    """部署根:LOOP_APPS_DIR 显式优先,否则 <ECS_REMOTE_DIR|~/apps>/<repo>。
    repo 名从 HARNESS_GIT_REMOTE 推导(缺省 loop-sample)。"""
    override = os.environ.get("LOOP_APPS_DIR")
    if override:
        return os.path.expanduser(override)
    base = os.path.expanduser(os.environ.get("ECS_REMOTE_DIR", "~/apps"))
    remote = os.environ.get("HARNESS_GIT_REMOTE", "").strip()
    repo = "loop-sample"
    if remote:
        name = remote.rstrip("/").split("/")[-1]
        repo = name[:-4] if name.endswith(".git") else name
    return os.path.join(base, repo)


def _port_alive(port, timeout=0.3):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _app_title(sample_dir, fallback):
    """标题取 README.md 第一个 Markdown 标题;取不到则回目录名。"""
    readme = os.path.join(sample_dir, "README.md")
    if os.path.exists(readme):
        try:
            with open(readme, encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s.startswith("#"):
                        t = s.lstrip("#").strip()
                        if t:
                            return t
        except OSError:
            pass
    return fallback


@app.route("/api/apps", methods=["GET"])
def list_apps():
    """真实已部署应用:sampleN → 端口 1000+N,本机探活 online,README 取标题。
    最新(端口大)排前。URL 主机沿用浏览器访问 studio 的主机名,自动对外可点。"""
    apps_dir = _apps_dir()
    host = (request.host or "").split(":")[0] or "127.0.0.1"
    apps = []
    if os.path.isdir(apps_dir):
        for d in sorted(glob.glob(os.path.join(apps_dir, "sample*"))):
            name = os.path.basename(d)
            m = re.fullmatch(r"sample(\d+)", name)
            if not m or not os.path.isdir(d):
                continue
            port = 1000 + int(m.group(1))
            apps.append({
                "name": name,
                "title": _app_title(d, name),
                "port": port,
                "url": f"http://{host}:{port}/",
                "online": _port_alive(port),
                "deployed": os.path.exists(os.path.join(d, "app.pid")),
            })
    apps.sort(key=lambda a: a["port"], reverse=True)
    online_n = sum(1 for a in apps if a["online"])
    return jsonify({"apps": apps, "total": len(apps),
                    "online": online_n, "offline": len(apps) - online_n,
                    "dir": apps_dir})


# ---------------------------------------------------------------------------
# 需求池(feishu backlog)可视化 + 新增飞书文档链接 —— 又一个纯新增外挂:
# 只读写 feishu_docs.json(需求清单) / feishu_state.json(处理状态),
# 不 import 适配器、不碰 orchestrator。与 config.env 的 HARNESS_FEISHU_* 同一份文件。
# ---------------------------------------------------------------------------
def _repo_path(env_key, default_rel):
    """把 config.env 里可能是相对(相对仓库根)的路径解析成绝对路径。"""
    p = os.environ.get(env_key, default_rel)
    return p if os.path.isabs(p) else os.path.join(REPO_ROOT, p)


def _feishu_docs_path():
    return _repo_path("HARNESS_FEISHU_DOCS", "delivery-loop/backlog/feishu_docs.json")


def _feishu_state_path():
    return _repo_path("HARNESS_FEISHU_STATE", "delivery-loop/backlog/feishu_state.json")


_FEISHU_TOKEN_RE = re.compile(r"/(wiki|docx|docs)/([A-Za-z0-9]+)")


def _parse_feishu_link(link):
    """从飞书链接提取 (token_kind, token)。
    - /wiki/<token>            -> ("wiki_token", token)
    - /docx/<token> 或 /docs/  -> ("doc_token",  token)
    - 直接粘贴纯 token(无斜杠) -> ("wiki_token", token)(知识库最常见)。
    解析不出返回 (None, None)。"""
    link = (link or "").strip()
    m = _FEISHU_TOKEN_RE.search(link)
    if m:
        return ("wiki_token" if m.group(1) == "wiki" else "doc_token", m.group(2))
    if link and "/" not in link and re.fullmatch(r"[A-Za-z0-9]+", link):
        return ("wiki_token", link)
    return (None, None)


def _next_fs_id(docs):
    """扫描已有 FS-<n> 生成下一个递增 id(FS-002...)。"""
    mx = 0
    for d in docs:
        m = re.fullmatch(r"FS-(\d+)", str(d.get("id", "")))
        if m:
            mx = max(mx, int(m.group(1)))
    return f"FS-{mx + 1:03d}"


@app.route("/api/backlog", methods=["GET"])
def get_backlog():
    """读需求池:合并 feishu_docs.json + feishu_state.json,给前端渲染清单与状态。"""
    docs_path = _feishu_docs_path()
    state_path = _feishu_state_path()
    docs = _read_json(docs_path).get("docs", []) if os.path.exists(docs_path) else []
    state = _read_json(state_path) if os.path.exists(state_path) else {}
    items = []
    for d in docs:
        tid = str(d.get("id"))
        st = state.get(tid, {})
        status = st.get("status", "pending")
        items.append({
            "id": tid,
            "title": d.get("title", tid),
            "token_kind": "wiki_token" if d.get("wiki_token") else ("doc_token" if d.get("doc_token") else None),
            "token": d.get("wiki_token") or d.get("doc_token"),
            "priority": d.get("priority", 99),
            # 适配器把 done/fetched 视为已处理跳过,其余(含 failed / 无记录)仍会入队
            "pending": status not in ("done", "fetched"),
            "status": status,
            "attempts": st.get("attempts"),
            "finished_at": st.get("finished_at"),
            "publish": st.get("publish"),
        })
    items.sort(key=lambda x: (x["priority"], x["id"]))
    return jsonify({"docs": items, "source": os.environ.get("HARNESS_BACKLOG_SOURCE", "local")})


@app.route("/api/backlog", methods=["POST"])
def add_backlog():
    """新增一条飞书文档需求:{title?, link, priority?, force?}。
    从链接解析 wiki_token/doc_token,自动生成 FS-NNN,追加进 feishu_docs.json。
    允许重复添加同一文档(文档内容会变/需多次拿同一文档生成):每条各自一个 id 与状态。
    但默认会检测重复:token 已存在且 force 不为真时返回 409+duplicate,由前端二次确认后带 force 重提。"""
    data = request.get_json(force=True) or {}
    title = (data.get("title") or "").strip()
    kind, token = _parse_feishu_link(data.get("link"))
    if not token:
        return jsonify({"ok": False, "error": "无法从链接解析飞书文档 token(需含 /wiki/ 或 /docx/,或直接粘贴纯 token)"}), 400
    if not title:
        title = token
    docs_path = _feishu_docs_path()
    cfg = _read_json(docs_path) if os.path.exists(docs_path) else {"docs": []}
    docs = cfg.setdefault("docs", [])
    if not data.get("force"):
        dups = [str(d.get("id")) for d in docs
                if d.get("wiki_token") == token or d.get("doc_token") == token]
        if dups:
            return jsonify({"ok": False, "duplicate": True, "existing": dups,
                            "error": f"该文档已在需求池中(id={', '.join(dups)})"}), 409
    try:
        priority = int(data.get("priority", len(docs) + 1))
    except (TypeError, ValueError):
        priority = len(docs) + 1
    entry = {"id": _next_fs_id(docs), "title": title, kind: token, "priority": priority}
    docs.append(entry)
    _write_json(docs_path, cfg)
    return jsonify({"ok": True, "id": entry["id"], "entry": entry})


@app.route("/api/backlog/<tid>/reset", methods=["POST"])
def reset_backlog(tid):
    """清除某需求的处理状态(从 feishu_state.json 移除),令其重新变 pending 可再次交付。"""
    state_path = _feishu_state_path()
    state = _read_json(state_path) if os.path.exists(state_path) else {}
    if str(tid) in state:
        del state[str(tid)]
        _write_json(state_path, state)
        return jsonify({"ok": True, "id": tid, "reset": True})
    return jsonify({"ok": True, "id": tid, "reset": False, "note": "该需求本无状态记录"})


@app.route("/api/backlog/<tid>", methods=["DELETE"])
def delete_backlog(tid):
    """从需求池移除一条文档(并清掉它的状态记录)。"""
    docs_path = _feishu_docs_path()
    cfg = _read_json(docs_path) if os.path.exists(docs_path) else {"docs": []}
    docs = cfg.get("docs", [])
    remaining = [d for d in docs if str(d.get("id")) != str(tid)]
    if len(remaining) == len(docs):
        return jsonify({"ok": False, "error": f"需求 {tid} 不存在"}), 404
    cfg["docs"] = remaining
    _write_json(docs_path, cfg)
    state_path = _feishu_state_path()
    if os.path.exists(state_path):
        state = _read_json(state_path)
        if str(tid) in state:
            del state[str(tid)]
            _write_json(state_path, state)
    return jsonify({"ok": True, "id": tid})


if __name__ == "__main__":
    port = int(os.environ.get("STUDIO_PORT", "5100"))
    # 部署到公网需 STUDIO_HOST=0.0.0.0;本机开发默认仍只绑回环。debug 默认关(公网暴露时勿开)。
    host = os.environ.get("STUDIO_HOST", "127.0.0.1")
    debug = os.environ.get("STUDIO_DEBUG", "0") == "1"
    print(f"Harness-4 配置工作台: http://{host}:{port}  鉴权: {'ON' if STUDIO_TOKEN else 'OFF'}  debug: {debug}")
    app.run(host=host, port=port, debug=debug)
