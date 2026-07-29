"""Loop Studio — Web 控制台后端。纯路由转发，业务逻辑在 api/ 和 engine/ 中。"""

import json, os, sys, time
from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for

STUDIO_DIR = os.path.dirname(os.path.abspath(__file__))
LOOP_DIR = os.path.dirname(STUDIO_DIR)
REPO_ROOT = os.path.dirname(LOOP_DIR)
ENGINE_DIR = os.path.join(LOOP_DIR, "engine")

sys.path.insert(0, LOOP_DIR)
sys.path.insert(0, ENGINE_DIR)
sys.path.insert(0, os.path.join(ENGINE_DIR, "tools"))
sys.path.insert(0, os.path.join(LOOP_DIR, "pipeline"))

# ── 加载 .env(必须在读 STUDIO_TOKEN/STUDIO_SECRET 之前)：优先仓库上级(本地开发布局)，其次 loop 目录本身(loop 作为仓库根克隆时) ──
def _load_env():
    env_file = os.path.join(REPO_ROOT, ".env")
    if not os.path.exists(env_file):
        env_file = os.path.join(LOOP_DIR, ".env")
    if not os.path.exists(env_file):
        return
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line.startswith("export "): line = line[7:]
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

_load_env()

# ── 注册 API Blueprint ──
from api.maker_api import maker_bp
from api.checker_api import checker_bp

app = Flask(__name__, template_folder=os.path.join(STUDIO_DIR, "templates"),
            static_folder=os.path.join(STUDIO_DIR, "static"))
app.register_blueprint(maker_bp, url_prefix="/api/maker")
app.register_blueprint(checker_bp, url_prefix="/api/checker")
app.secret_key = os.environ.get("STUDIO_SECRET") or os.urandom(24)
STUDIO_TOKEN = os.environ.get("STUDIO_TOKEN", "").strip()

# ── 鉴权守卫：设了 STUDIO_TOKEN 即全站拦截(页面跳登录、API 返 401)，未设则开发模式直接放行 ──
_AUTH_EXEMPT = {"/login", "/logout", "/healthz", "/favicon.ico"}

@app.before_request
def _auth_guard():
    if not STUDIO_TOKEN:
        return None
    p = request.path
    if p in _AUTH_EXEMPT or p.startswith("/static/"):
        return None
    if session.get("authed"):
        return None
    # API 调用支持 Bearer token(给脚本/webhook 用)
    auth = request.headers.get("Authorization", "")
    if auth == f"Bearer {STUDIO_TOKEN}":
        return None
    if p.startswith("/api/") or p.startswith("/output/"):
        return jsonify({"error": "unauthorized"}), 401
    return redirect(url_for("login", next=p))


@app.route("/login", methods=["GET", "POST"])
def login():
    if not STUDIO_TOKEN or session.get("authed"):
        return redirect("/")
    error = None
    if request.method == "POST":
        if request.form.get("token", "") == STUDIO_TOKEN:
            session["authed"] = True
            session.permanent = True
            return redirect(request.args.get("next") or "/")
        error = "口令错误，请重试"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.pop("authed", None)
    return redirect(url_for("login"))

# ── 页面路由 ──
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/studio")
def studio_workbench():
    return render_template("index.html")

@app.route("/output/<path:filepath>")
def serve_output(filepath):
    """直接访问产物文件。"""
    return send_from_directory(os.path.join(REPO_ROOT, "output"), filepath)


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "auth": bool(STUDIO_TOKEN)})


# ── 基础 IO ──
def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def _write_json(path, data):
    # data/ 是运行时目录不入仓，克隆部署后首次写入时需自动创建
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

def _feishu_docs_path():
    return os.path.join(LOOP_DIR, "data", "backlog.json")

def _feishu_state_path():
    return os.path.join(LOOP_DIR, "data", "state.json")

CONFIG_PATH = os.path.join(LOOP_DIR, "config.env")
RUN_BACKLOG = os.path.join(LOOP_DIR, "pipeline", "run.py")
GATE_PY = os.path.join(ENGINE_DIR, "gate.py")
GENERATE_PY = os.path.join(ENGINE_DIR, "generate.py")


# ── Backlog API ──
@app.route("/api/backlog", methods=["GET"])
def get_backlog():
    docs_path = _feishu_docs_path()
    state_path = _feishu_state_path()
    docs = _read_json(docs_path).get("docs", []) if os.path.exists(docs_path) else []
    state = _read_json(state_path) if os.path.exists(state_path) else {}
    items = []
    for d in docs:
        tid = str(d.get("id"))
        st = state.get(tid, {})
        items.append({
            "id": tid, "title": d.get("title", tid),
            "token_kind": "wiki_token" if d.get("wiki_token") else ("doc_token" if d.get("doc_token") else None),
            "token": d.get("wiki_token") or d.get("doc_token"),
            "priority": d.get("priority", 99),
            "pending": st.get("status") not in ("done", "fetched"),
            "status": st.get("status", "pending"),
            "spec_text": d.get("spec_text", ""),
            "attempts": st.get("attempts"),
        })
    items.sort(key=lambda x: (x["priority"], x["id"]))
    return jsonify({"docs": items, "source": "feishu"})


@app.route("/api/backlog", methods=["POST"])
def add_backlog():
    data = request.get_json(force=True) or {}
    title = (data.get("title") or "").strip()
    spec_text = (data.get("spec_text") or "").strip()
    link = data.get("link", "")
    kind, token = (None, None)
    if link:
        import re
        m = re.search(r"(wiki|docx|docs)/([A-Za-z0-9]+)", link)
        if m:
            kind = "wiki_token" if m.group(1) == "wiki" else "doc_token"
            token = m.group(2)
    if not spec_text and not token:
        return jsonify({"ok": False, "error": "请填写需求描述或粘贴飞书链接"}), 400
    if not title:
        title = spec_text[:50] if spec_text else (token or "未命名需求")

    docs_path = _feishu_docs_path()
    cfg = _read_json(docs_path) if os.path.exists(docs_path) else {"docs": []}
    docs_list = cfg.setdefault("docs", [])
    nid = f"FS-{len(docs_list)+1:03d}"
    entry = {"id": nid, "title": title, "priority": int(data.get("priority", len(docs_list) + 1))}
    if kind and token:
        entry[kind] = token
    if spec_text:
        entry["spec_text"] = spec_text
    docs_list.append(entry)
    _write_json(docs_path, cfg)
    return jsonify({"ok": True, "id": nid, "entry": entry})


@app.route("/api/backlog/<tid>/reset", methods=["POST"])
def reset_backlog(tid):
    state_path = _feishu_state_path()
    state = _read_json(state_path) if os.path.exists(state_path) else {}
    if str(tid) in state:
        del state[str(tid)]
        _write_json(state_path, state)
        return jsonify({"ok": True, "id": tid, "reset": True})
    return jsonify({"ok": True, "id": tid, "reset": False, "note": "无状态记录"})


@app.route("/api/backlog/<tid>", methods=["DELETE"])
def delete_backlog(tid):
    docs_path = _feishu_docs_path()
    cfg = _read_json(docs_path) if os.path.exists(docs_path) else {"docs": []}
    docs_list = cfg.get("docs", [])
    remaining = [d for d in docs_list if str(d.get("id")) != str(tid)]
    cfg["docs"] = remaining
    _write_json(docs_path, cfg)
    state_path = _feishu_state_path()
    if os.path.exists(state_path):
        state = _read_json(state_path)
        if str(tid) in state:
            del state[str(tid)]
            _write_json(state_path, state)
    return jsonify({"ok": True, "id": tid})


# ── Config API ──
@app.route("/api/config", methods=["GET"])
def get_config():
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            for line in f:
                line = line.strip()
                if line.startswith("export "): line = line[7:]
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    cfg[k.strip()] = v.strip().strip('"').strip("'")
    return jsonify({"ok": True, "config": cfg})


@app.route("/api/config", methods=["POST"])
def save_config():
    data = request.get_json(force=True) or {}
    if not data:
        return jsonify({"ok": False, "error": "请求体为空"}), 400
    lines = []
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            lines = f.readlines()
    updated = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("export ") and "=" in stripped:
            k = stripped[7:].split("=", 1)[0].strip()
            if k in data:
                new_lines.append(f'export {k}="${{{k}:-{data[k]}}}"\n')
                updated.add(k)
                continue
        new_lines.append(line)
    for k, v in data.items():
        if k not in updated:
            new_lines.append(f'export {k}="${{{k}:-{v}}}"\n')
    with open(CONFIG_PATH, "w") as f:
        f.writelines(new_lines)
    return jsonify({"ok": True, "saved": list(data.keys())})


# ── Publish API ──
@app.route("/api/publish", methods=["POST"])
def publish_app():
    data = request.get_json(force=True) or {}
    out_dir = data.get("dir", "")
    message = data.get("message", "Loop 自动交付")
    if not out_dir or not os.path.isdir(out_dir):
        return jsonify({"ok": False, "error": "dir 参数无效"}), 400
    try:
        import publisher
        result = publisher.publish(out_dir, "main", message)
        return jsonify({"ok": result.get("pushed", False), "result": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/deploy", methods=["POST"])
def deploy_app():
    """部署产物到 ECS。body: {"dir": "output/xxx", "subdir": "sampleN", "port": "100N"}

    subdir/port 优先用 publisher 推送后回填的值(sampleN + port_base+N)，
    未传时回退产物目录名与 ECS_APP_PORT(仅适用于固定子目录模式)。"""
    data = request.get_json(force=True) or {}
    out_dir = data.get("dir", "")
    if not out_dir or not os.path.isdir(out_dir):
        return jsonify({"ok": False, "error": "dir 参数无效"}), 400
    try:
        import deployer
        app_port = int(data.get("port") or os.environ.get("ECS_APP_PORT", "5000"))
        subdir = data.get("subdir") or os.path.basename(out_dir)
        result = deployer.deploy(app_port, subdir=subdir)
        return jsonify({"ok": result.get("deployed", False), "url": result.get("url", ""), "result": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Trigger / Trace / Features ──
_trigger_state = {"running": False, "log": "", "exit_code": None}
_trigger_lock = __import__("threading").Lock()


@app.route("/api/trigger", methods=["POST"])
def trigger_delivery():
    if not _trigger_lock.acquire(blocking=False):
        return jsonify({"ok": False, "busy": True}), 409
    body = request.get_json(silent=True) or {}
    extra = {}
    only = str(body.get("task", "")).strip()
    if only:
        extra["HARNESS_ONLY_TASK"] = only
    _trigger_state.update({"running": True, "exit_code": None, "log": "", "started_at": time.strftime("%Y-%m-%d %H:%M:%S")})
    import threading as _th
    def _run_bg():
        try:
            import subprocess as _sp
            proc = _sp.Popen([sys.executable, RUN_BACKLOG], cwd=REPO_ROOT, env={**os.environ, **extra},
                            stdout=_sp.PIPE, stderr=_sp.STDOUT, text=True, bufsize=1)
            for line in proc.stdout or ():
                _trigger_state["log"] += line
            proc.wait()
            _trigger_state["exit_code"] = proc.returncode
        except Exception as exc:
            _trigger_state["log"] += f"\n触发失败: {exc}\n"
            _trigger_state["exit_code"] = -1
        finally:
            _trigger_state["running"] = False
            _trigger_state["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            _trigger_lock.release()
    _th.Thread(target=_run_bg, daemon=True).start()
    return jsonify({"ok": True, "started_at": _trigger_state["started_at"]})


@app.route("/api/trigger/status", methods=["GET"])
def trigger_status():
    return jsonify(_trigger_state)


# ── 引擎直驱：门禁 / 单用例生成（Python 子进程，替代 .sh 脚本）──
_engine_state = {"gate": {"running": False, "log": "", "exit_code": None},
                 "generate": {"running": False, "log": "", "exit_code": None}}
_engine_locks = {"gate": __import__("threading").Lock(),
                 "generate": __import__("threading").Lock()}


def _run_engine_bg(key, cmd, extra_env):
    """后台线程跑引擎子进程，实时把输出累积到 _engine_state[key].log。"""
    import subprocess as _sp
    state = _engine_state[key]
    try:
        proc = _sp.Popen(cmd, cwd=REPO_ROOT, env={**os.environ, **extra_env},
                         stdout=_sp.PIPE, stderr=_sp.STDOUT, text=True, bufsize=1)
        for line in proc.stdout or ():
            state["log"] += line
        proc.wait()
        state["exit_code"] = proc.returncode
    except Exception as exc:  # noqa: BLE001
        state["log"] += f"\n执行失败: {exc}\n"
        state["exit_code"] = -1
    finally:
        state["running"] = False
        state["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _engine_locks[key].release()


def _start_engine(key, cmd, extra_env):
    """抢锁并起后台线程；已在跑则返回 409。"""
    if not _engine_locks[key].acquire(blocking=False):
        return jsonify({"ok": False, "busy": True}), 409
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    _engine_state[key] = {"running": True, "log": "", "exit_code": None, "started_at": started}
    import threading as _th
    _th.Thread(target=_run_engine_bg, args=(key, cmd, extra_env), daemon=True).start()
    return jsonify({"ok": True, "started_at": started})


@app.route("/api/gate", methods=["POST"])
def run_gate():
    """跑门禁闭环 gate.py（自洽性 → Schema → 全用例生成验证）。
    body(可选): {"mode": "sample"|"real"}。"""
    body = request.get_json(silent=True) or {}
    extra = {}
    mode = str(body.get("mode", "")).strip()
    if mode:
        extra["HARNESS_MODE"] = mode
    return _start_engine("gate", [sys.executable, GATE_PY], extra)


@app.route("/api/generate", methods=["POST"])
def run_generate():
    """跑单个/指定用例的生成验证 generate.py。
    body(可选): {"case": "education", "mode": "sample"|"real"}。"""
    body = request.get_json(silent=True) or {}
    extra = {}
    case = str(body.get("case", "")).strip()
    if case:
        extra["HARNESS_CASES"] = case
    mode = str(body.get("mode", "")).strip()
    if mode:
        extra["HARNESS_MODE"] = mode
    return _start_engine("generate", [sys.executable, GENERATE_PY], extra)


@app.route("/api/gate/status", methods=["GET"])
def gate_status():
    return jsonify(_engine_state["gate"])


@app.route("/api/generate/status", methods=["GET"])
def generate_status():
    return jsonify(_engine_state["generate"])


@app.route("/api/trace", methods=["GET"])
def get_trace():
    try:
        import tracer
        return jsonify({"ok": True, "events": tracer.query(limit=int(request.args.get("limit", "100"))),
                        "metrics": tracer.metrics()})
    except ImportError:
        return jsonify({"ok": True, "events": [], "metrics": {}})


@app.route("/api/features", methods=["GET"])
def get_features():
    try:
        from guardrails import load_features
        return jsonify({"ok": True, "features": load_features()})
    except ImportError:
        return jsonify({"ok": False, "error": "guardrails 未找到"}), 500


@app.route("/api/features", methods=["POST"])
def toggle_features():
    data = request.get_json(force=True) or {}
    try:
        from guardrails import save_features
        return jsonify({"ok": True, "features": save_features(data)})
    except ImportError:
        return jsonify({"ok": False, "error": "guardrails 未找到"}), 500


@app.route("/api/knowledge", methods=["GET"])
def get_knowledge():
    try:
        from knowledge import load_runs, load_traces, analyze
        return jsonify({"ok": True, "knowledge": analyze(load_runs(), load_traces())})
    except ImportError:
        return jsonify({"ok": False, "error": "knowledge 未找到"}), 500


@app.route("/api/checks", methods=["GET"])
def list_checks():
    """全量检查注册表（按四象限/环节分组），供页面渲染 checklist 全景。
    可选参数：?quadrant=check-rule&category=security。"""
    try:
        from checker import get_checks, summary, QUADRANTS
        quadrant = request.args.get("quadrant") or None
        category = request.args.get("category") or None
        return jsonify({"ok": True,
                        "checks": get_checks(quadrant, category),
                        "summary": summary(),
                        "quadrants": QUADRANTS})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500


def _svg(body):
    """简笔画线条 icon：统一描边风格，随文字颜色(currentColor)。"""
    return ('<svg width="14" height="14" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
            'stroke-linejoin="round" style="vertical-align:-2px">%s</svg>' % body)


_PIPE_ICONS = {
    # 折角文档+段落线:Spec 编译
    "mumuspec": _svg('<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4"/><path d="M10 12h5M10 16h5"/>'),
    # 三节点连线图:多 Agent 协作
    "langgraph": _svg('<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="6" r="2.5"/>'
                      '<circle cx="12" cy="17" r="2.5"/><path d="M8.5 6h7M7 8.2l3.8 6.3M17 8.2l-3.8 6.3"/>'),
    # 信号灯:门禁
    "gate": _svg('<rect x="9" y="3" width="6" height="18" rx="3"/>'
                 '<circle cx="12" cy="7.5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="16.5" r="1"/>'),
    # 循环箭头:生成主循环
    "generate": _svg('<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v5h-5"/>'),
    # 滑杆:功能开关
    "features": _svg('<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="2.2"/><circle cx="15" cy="17" r="2.2"/>'),
}


@app.route("/api/pipeline", methods=["GET"])
def list_pipeline():
    """流水线各环节可枚举清单（除 checker 之外）：
    MumuSpec 六轮编译 / LangGraph 五 Agent / 门禁三阶段 / 生成主循环 / 功能开关。
    数据尽量从引擎源头实时提取，保证与代码一致。"""
    stages = []
    # ① MumuSpec 六轮 Skill（Spec 编译阶段展开）
    try:
        from mumuspec_compiler import SKILLS
        stages.append({
            "key": "mumuspec", "name": "MumuSpec 六轮编译", "icon": _PIPE_ICONS["mumuspec"],
            "desc": "自由文本需求 → 契约三件套（‘生成’前的 Spec 编译）",
            "toggle": "mumuspec",
            "items": [{"id": s["id"], "name": s["name"]} for s in SKILLS],
        })
    except Exception:  # noqa: BLE001
        pass
    # ② LangGraph 五 Agent（生成阶段内部展开）
    try:
        from langgraph_orchestrator import AGENTS
        stages.append({
            "key": "langgraph", "name": "LangGraph 多 Agent 协作", "icon": _PIPE_ICONS["langgraph"],
            "desc": "五 Agent 流水线：分析 → 生成 → 审查 → 测试 → 集成",
            "toggle": "langgraph",
            "items": [{"id": a["id"], "name": a["name"], "desc": a.get("desc", "")} for a in AGENTS],
        })
    except Exception:  # noqa: BLE001
        pass
    # ③ 门禁三阶段（gate.py 固定流程）
    stages.append({
        "key": "gate", "name": "门禁闭环", "icon": _PIPE_ICONS["gate"],
        "desc": "任一阶段失败即终止（python loop/engine/gate.py）",
        "items": [
            {"id": "1/3", "name": "Spec 自洽性校验", "desc": "compile_spec.py --check"},
            {"id": "2/3", "name": "派生数据 Schema", "desc": "build_schema.py"},
            {"id": "3/3", "name": "全用例生成 + 验证闭环", "desc": "generate.py"},
        ],
    })
    # ④ 生成主循环阶段（generate.py main）
    stages.append({
        "key": "generate", "name": "生成主循环", "icon": _PIPE_ICONS["generate"],
        "desc": "单用例的生成→验收→重试闭环（含护栏）",
        "items": [
            {"id": "S1", "name": "生成产物", "desc": "Maker 生成代码"},
            {"id": "S2", "name": "验收", "desc": "verify_ac.py 跑 AC/TC"},
            {"id": "S3", "name": "带反馈重生成", "desc": "未通过时回传失败日志，最多 %s 次" % os.environ.get("HARNESS_MAX_RETRY", "5")},
            {"id": "S4", "name": "卡死检测", "desc": "连续 3 次相同失败即终止"},
            {"id": "S5", "name": "确定性复跑", "desc": "两次生成产物指纹比对"},
            {"id": "S6", "name": "写运行记录", "desc": "output/runs.jsonl"},
        ],
    })
    # ⑤ 功能开关（guardrails）
    try:
        from guardrails import load_features
        feats = load_features()
        fmeta = {
            "reasoning_review": "LLM-as-Judge 代码审查",
            "reasoning_style": "LLM UI 还原度检查",
            "langgraph": "多 Agent 协作",
            "mumuspec": "MumuSpec 六轮编译",
            "cost_cap": "花费上限",
            "stall_detect": "卡死检测",
            "det_check": "确定性复跑",
        }
        stages.append({
            "key": "features", "name": "功能开关", "icon": _PIPE_ICONS["features"],
            "desc": "全局能力开关（可在设置页切换）",
            "items": [{"id": k, "name": fmeta.get(k, k), "on": bool(v)}
                      for k, v in feats.items()],
        })
    except Exception:  # noqa: BLE001
        pass
    return jsonify({"ok": True, "stages": stages})


# ── Swagger ──
@app.route("/api/swagger.json")
def swagger_json():
    host = request.host
    return jsonify({
        "openapi": "3.0.3",
        "info": {"title": "Loop Platform API", "version": "5.0.0"},
        "servers": [{"url": f"http://{host}"}],
        "paths": {
            "/api/maker/list": {"get": {"summary": "列出可用 Maker", "tags": ["Maker"]}},
            "/api/maker/run": {"post": {"summary": "异步生成代码", "tags": ["Maker"]}},
            "/api/maker/stream/<task_id>": {"get": {"summary": "SSE 流式推送状态", "tags": ["Maker"]}},
            "/api/maker/status": {"get": {"summary": "查询任务状态", "tags": ["Maker"]}},
            "/api/checker/<name>": {"post": {"summary": "运行指定 Checker", "tags": ["Checker"]}},
            "/api/checker/all": {"post": {"summary": "运行全部 Checker", "tags": ["Checker"]}},
            "/api/backlog": {"get": {"summary": "需求池列表"}, "post": {"summary": "新增需求", "tags": ["需求管理"]}},
            "/api/backlog/<id>": {"delete": {"summary": "移除需求", "tags": ["需求管理"]}},
            "/api/backlog/<id>/reset": {"post": {"summary": "重置状态", "tags": ["需求管理"]}},
            "/api/config": {"get": {"summary": "读取配置"}, "post": {"summary": "保存配置", "tags": ["设置"]}},
            "/api/publish": {"post": {"summary": "推送 GitHub", "tags": ["发布"]}},
            "/api/trigger": {"post": {"summary": "触发交付", "tags": ["交付"]}},
            "/api/trigger/status": {"get": {"summary": "交付状态", "tags": ["交付"]}},
            "/api/gate": {"post": {"summary": "跑门禁闭环(gate.py)", "tags": ["交付"]}},
            "/api/gate/status": {"get": {"summary": "门禁状态", "tags": ["交付"]}},
            "/api/generate": {"post": {"summary": "单用例生成验证(generate.py)", "tags": ["交付"]}},
            "/api/generate/status": {"get": {"summary": "生成状态", "tags": ["交付"]}},
            "/api/trace": {"get": {"summary": "Trace 事件", "tags": ["可观测"]}},
            "/api/features": {"get": {"summary": "功能开关"}, "post": {"summary": "设置开关", "tags": ["设置"]}},
            "/api/knowledge": {"get": {"summary": "知识积累", "tags": ["可观测"]}},
            "/api/checks": {"get": {"summary": "检查项全景(四象限/环节)", "tags": ["Checker"]}},
            "/api/pipeline": {"get": {"summary": "流程各环节清单(六轮/五Agent/门禁/生成/开关)", "tags": ["交付"]}},
            "/api/apps": {"get": {"summary": "已部署应用", "tags": ["运维"]}},
            "/healthz": {"get": {"summary": "健康检查"}},
        },
        "tags": [{"name": "Maker"}, {"name": "Checker"}, {"name": "需求管理"}, {"name": "设置"}, {"name": "发布"}, {"name": "交付"}, {"name": "可观测"}, {"name": "运维"}],
    })


@app.route("/swagger")
def swagger_ui():
    return render_template("swagger.html")


# ── 启动 ──
if __name__ == "__main__":
    port = int(os.environ.get("STUDIO_PORT", "5100"))
    host = os.environ.get("STUDIO_HOST", "127.0.0.1")
    debug = os.environ.get("STUDIO_DEBUG", "0") == "1"
    print(f"Loop 配置工作台: http://{host}:{port}  鉴权: {'ON' if STUDIO_TOKEN else 'OFF'}")
    # threaded=True：SSE 长连接(/api/maker/stream)与后台生成不再独占唯一 worker，
    # 否则 /output 静态请求会排队变慢。
    app.run(host=host, port=port, debug=debug, threaded=True)
