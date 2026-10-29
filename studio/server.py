"""Loop Studio — Web 控制台后端。纯路由转发，业务逻辑在 api/ 和 engine/ 中。"""

import json, os, sys, time
from flask import Flask, abort, jsonify, redirect, render_template, request, send_from_directory, session, url_for

# 先以当前文件位置解析路径，确保 engine/ 可导入
STUDIO_DIR = os.path.dirname(os.path.abspath(__file__))
LOOP_DIR = os.path.dirname(STUDIO_DIR)
REPO_ROOT = LOOP_DIR  # 重构后 studio/ 直接在仓库根下
VUE_STUDIO_DIST_DIR = os.path.join(STUDIO_DIR, "web", "dist")
sys.path.insert(0, LOOP_DIR)
sys.path.insert(0, os.path.join(LOOP_DIR, "engine"))

# F2: 用 PlatformPaths 接管后续所有路径解析
from engine.core.paths import PlatformPaths, load_config, find_root

ENGINE_DIR = str(PlatformPaths.ENGINE_DIR)
sys.path.insert(0, str(PlatformPaths.ENGINE_DIR / "tools"))
sys.path.insert(0, str(PlatformPaths.PIPELINE_DIR))

# ── .env 加载（通过 PlatformPaths + load_config）──
def _load_env():
    """加载 .env，将密钥写入 os.environ。"""
    env_file = str(PlatformPaths.ENV_FILE)
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
    """Vue 是正式入口；原 Flask Studio 保留在显式的 /studio Legacy 路径。"""
    return redirect("/studio-vue/")


@app.route("/studio")
def studio_workbench():
    return render_template("index.html")


def _vue_hash_redirect(route: str):
    """将旧式路径深链稳定转换为 Vue Hash 路由，并保留查询参数。"""
    query = request.query_string.decode("ascii", errors="ignore")
    suffix = f"?{query}" if query else ""
    return redirect(f"/studio-vue/#{route}{suffix}")


@app.route("/studio-vue/intake")
def vue_intake():
    return _vue_hash_redirect("/intake")


@app.route("/studio-vue/plans")
def vue_plans():
    return _vue_hash_redirect("/plans")


@app.route("/studio-vue/governance")
def vue_governance():
    return _vue_hash_redirect("/governance")


@app.route("/studio-vue/requirements/<task_id>")
def vue_requirement(task_id):
    return _vue_hash_redirect(f"/requirements/{task_id}")


@app.route("/studio-vue/runs/<run_id>")
def vue_run(run_id):
    return _vue_hash_redirect(f"/runs/{run_id}")


@app.route("/studio-vue/", defaults={"asset_path": ""})
@app.route("/studio-vue/<path:asset_path>")
def vue_studio(asset_path):
    """独立提供正式 Vue Studio；禁用缓存，确保本地构建更新立即生效。"""
    if not os.path.isfile(os.path.join(VUE_STUDIO_DIST_DIR, "index.html")):
        return jsonify({"ok": False, "error": "Vue Studio 尚未构建；请执行 npm run build"}), 503
    if asset_path and os.path.isfile(os.path.join(VUE_STUDIO_DIST_DIR, asset_path)):
        response = send_from_directory(VUE_STUDIO_DIST_DIR, asset_path)
    elif asset_path and os.path.splitext(asset_path)[1]:
        # 资源路径错误不能回退成 HTML，否则浏览器会把 index.html 当作 JS/CSS 加载并造成空白页。
        abort(404)
    else:
        response = send_from_directory(VUE_STUDIO_DIST_DIR, "index.html")
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.route("/output/<path:filepath>")
def serve_output(filepath):
    """直接访问产物文件。"""
    return send_from_directory(str(PlatformPaths.OUTPUT_DIR), filepath)


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "auth": bool(STUDIO_TOKEN)})


# ── Profile Composer：仅编排草稿，不读取组件、不执行、不写入 ──
_COMPOSER_CATALOG = {
    "schema_version": 1,
    "stages": {
        "source": [{"id": "local_queue", "label": "本地需求队列", "description": "从受控本地队列读取已绑定需求。", "experimental": False, "capabilities": {"network": False, "model": False, "git": False, "publish": False, "deploy": False, "ssh": False}, "config_schema": {"type": "object", "additionalProperties": False, "properties": {"backlog_path": {"type": "string", "secret": False}, "state_path": {"type": "string", "secret": False}}}}, {"id": "jira", "label": "Jira 系统", "description": "从 Jira 项目拉取 Issue 作为需求，进入受控执行链（待接入）。", "experimental": True, "available": False, "capabilities": {"network": True, "model": False, "git": False, "publish": False, "deploy": False, "ssh": False}, "config_schema": {"type": "object", "additionalProperties": False, "properties": {"server": {"type": "string", "secret": False}, "project_key": {"type": "string", "secret": False}}}}],
        "compiler": [{"id": "simple", "label": "Simple Compiler", "description": "确定性本地 Spec 编译器。", "experimental": False, "capabilities": {"network": False, "model": False, "git": False, "publish": False, "deploy": False, "ssh": False}, "config_schema": {"type": "object", "additionalProperties": False}}, {"id": "mumuspec", "label": "MumuSpec Compiler", "description": "实验性本地编译器；当前会回退到 SimpleCompiler。", "experimental": True, "capabilities": {"network": False, "model": False, "git": False, "publish": False, "deploy": False, "ssh": False}, "config_schema": {"type": "object", "additionalProperties": False}}, {"id": "openspec", "label": "OpenSpec Compiler", "description": "按 OpenSpec 规范把需求编译为可验收的 Spec 与 Acceptance（待接入）。", "experimental": True, "available": False, "capabilities": {"network": False, "model": False, "git": False, "publish": False, "deploy": False, "ssh": False}, "config_schema": {"type": "object", "additionalProperties": False, "properties": {"spec_dir": {"type": "string", "secret": False}, "spec_format": {"type": "string", "secret": False}}}}],
        "maker": [{"id": "sample", "label": "Sample Maker", "description": "离线参考生成器，用于 fixture 回归。", "experimental": False, "capabilities": {"network": False, "model": False, "git": False, "publish": False, "deploy": False, "ssh": False}, "config_schema": {"type": "object", "additionalProperties": False}}, {"id": "deepseek", "label": "DeepSeek API Maker", "description": "需显式允许网络与模型调用的受控生成器。", "experimental": False, "capabilities": {"network": True, "model": True, "git": False, "publish": False, "deploy": False, "ssh": False}, "config_schema": {"type": "object", "additionalProperties": False}}],
        "checker": [{"id": "security", "label": "Security Checker", "description": "确定性安全与结构检查。", "experimental": False, "capabilities": {"network": False, "model": False, "git": False, "publish": False, "deploy": False, "ssh": False}, "config_schema": {"type": "object", "additionalProperties": False}}, {"id": "pages", "label": "Pages Contract Checker", "description": "验证冻结页面合同、页面文件和本地跳转。", "experimental": False, "capabilities": {"network": False, "model": False, "git": False, "publish": False, "deploy": False, "ssh": False}, "config_schema": {"type": "object", "additionalProperties": False}}, {"id": "runtime", "label": "Runtime Checker", "description": "运行时检查。", "experimental": False, "capabilities": {"network": False, "model": False, "git": False, "publish": False, "deploy": False, "ssh": False}, "config_schema": {"type": "object", "additionalProperties": False}}, {"id": "e2e", "label": "E2E Checker", "description": "端到端验收检查。", "experimental": False, "capabilities": {"network": False, "model": False, "git": False, "publish": False, "deploy": False, "ssh": False}, "config_schema": {"type": "object", "additionalProperties": False}}, {"id": "process", "label": "Process Checker", "description": "受证据约束的外部流程诊断检查。", "experimental": True, "capabilities": {"network": False, "model": False, "git": False, "publish": False, "deploy": False, "ssh": False}, "config_schema": {"type": "object", "additionalProperties": False}}],
        "delivery": [{"id": "local_artifact", "label": "本地制品", "description": "仅在本机保存受控制品；不发布、不部署。", "experimental": False, "capabilities": {"network": False, "model": False, "git": False, "publish": False, "deploy": False, "ssh": False}, "config_schema": {"type": "object", "additionalProperties": False}}, {"id": "github_workflow", "label": "GitHub Workflow", "description": "受控推送到固定仓库；仓库 Workflow 后续部署，ECS 健康不在本阶段推断。", "experimental": False, "capabilities": {"network": True, "model": True, "git": True, "publish": True, "deploy": True, "ssh": False}, "config_schema": {"type": "object", "additionalProperties": False, "properties": {"repo": {"type": "string", "secret": False}, "branch": {"type": "string", "secret": False}, "prefix": {"type": "string", "secret": False}, "port_base": {"type": "integer", "secret": False}, "workflow_deploy": {"type": "boolean", "secret": False}}}}],
    },
    "safeguards": ["预检不会读取队列、调用模型、执行检查、创建 Run Plan、写入 Profile 或触发网络/Git/SSH/发布/部署。", "浏览器草稿禁止填写 token、secret、password、credential 或 API key。", "预检通过后可直接保存到 Profile 库；实际外部执行仍须在新建需求页由用户点击“确认并执行”。"],
}
_COMPOSER_REQUIRED_POLICY = ("max_attempts", "allow_network", "allow_publish", "allow_deploy", "on_unavailable")
_COMPOSER_BOOLEAN_POLICY = ("allow_network", "allow_model", "allow_git", "allow_ssh", "allow_publish", "allow_deploy")
_COMPOSER_SECRET_MARKERS = ("secret", "token", "password", "credential", "api_key", "apikey", "private_key")


def _composer_diagnostic(path, code, message, severity="error"):
    return {"path": path, "code": code, "message": message, "severity": severity}


def _composer_catalog_copy():
    return json.loads(json.dumps(_COMPOSER_CATALOG))


def _composer_descriptor(stage, component_id):
    for descriptor in _COMPOSER_CATALOG["stages"][stage]:
        if descriptor["id"] == component_id:
            return {key: value for key, value in descriptor.items() if key != "config_schema"}
    return {"id": component_id, "label": "未知节点", "description": "不在服务端白名单中。", "experimental": False, "capabilities": {}}


def _composer_graph(profile):
    return {"stages": [
        {"id": "source", "label": "来源", "components": [_composer_descriptor("source", profile.source)]},
        {"id": "compiler", "label": "编译", "components": [_composer_descriptor("compiler", profile.compiler)]},
        {"id": "maker", "label": "生成", "components": [_composer_descriptor("maker", profile.maker)]},
        {"id": "checker", "label": "检查", "components": [_composer_descriptor("checker", item) for item in profile.checkers]},
        {"id": "delivery", "label": "交付", "components": [_composer_descriptor("delivery", profile.delivery)]},
    ]}


def _composer_preflight(raw_profile):
    """Pure draft validation. Do not call validate_profile() or any component factory here."""
    from engine.core.profiles import Profile, ProfileError
    diagnostics = []
    if not isinstance(raw_profile, dict):
        return None, diagnostics + [_composer_diagnostic("profile", "invalid_type", "profile 必须是对象")]
    try:
        profile = Profile.from_dict(raw_profile)
    except ProfileError as exc:
        return None, diagnostics + [_composer_diagnostic("profile", "invalid_shape", str(exc))]

    def known(stage, component_id, path):
        if component_id not in {item["id"] for item in _COMPOSER_CATALOG["stages"][stage]}:
            diagnostics.append(_composer_diagnostic(path, "unknown_component", f"{component_id or '空值'} 不在 {stage} 白名单中"))

    known("source", profile.source, "source.name")
    known("compiler", profile.compiler, "compiler")
    known("maker", profile.maker, "maker")
    known("delivery", profile.delivery, "delivery")
    if not profile.checkers:
        diagnostics.append(_composer_diagnostic("checkers", "empty_checkers", "至少选择一个 Checker"))
    for index, checker in enumerate(profile.checkers):
        known("checker", checker, f"checkers[{index}]")
    if len(set(profile.checkers)) != len(profile.checkers):
        diagnostics.append(_composer_diagnostic("checkers", "duplicate_checker", "Checker 不能重复"))
    if isinstance(profile.version, bool) or profile.version < 1:
        diagnostics.append(_composer_diagnostic("version", "invalid_version", "version 必须是大于 0 的整数"))
    if not profile.id or not profile.id[0].islower() or any(not (char.islower() or char.isdigit() or char == "-") for char in profile.id):
        diagnostics.append(_composer_diagnostic("id", "invalid_id", "id 只能使用小写字母、数字和连字符，且以字母开头"))

    policy = profile.policy
    for key in _COMPOSER_REQUIRED_POLICY:
        if key not in policy:
            diagnostics.append(_composer_diagnostic(f"policy.{key}", "required", "该策略字段必填；预检不会替草稿推断权限"))
    for key in _COMPOSER_BOOLEAN_POLICY:
        if key in policy and not isinstance(policy[key], bool):
            diagnostics.append(_composer_diagnostic(f"policy.{key}", "invalid_boolean", "必须是布尔值"))
    if isinstance(policy.get("max_attempts"), bool) or not isinstance(policy.get("max_attempts"), int) or policy.get("max_attempts", 0) < 1:
        diagnostics.append(_composer_diagnostic("policy.max_attempts", "invalid_attempts", "必须是大于 0 的整数"))
    if policy.get("on_unavailable") not in {"block", "review_required", "continue"}:
        diagnostics.append(_composer_diagnostic("policy.on_unavailable", "invalid_unavailable_policy", "必须是 block、review_required 或 continue"))
    for key in ("timeout_seconds", "cost_limit_yuan"):
        if key in policy and (isinstance(policy[key], bool) or not isinstance(policy[key], (int, float)) or policy[key] < 0):
            diagnostics.append(_composer_diagnostic(f"policy.{key}", "invalid_limit", "必须是非负数字"))

    for scope, config in (("source.config", profile.source_config), ("delivery_config", profile.delivery_config)):
        for key in config:
            if any(marker in key.lower() for marker in _COMPOSER_SECRET_MARKERS):
                diagnostics.append(_composer_diagnostic(f"{scope}.{key}", "secret_not_allowed", "草稿不接受密钥字段；凭据只能由服务端受控配置提供"))
    if profile.source_config and any(key not in {"backlog_path", "state_path"} for key in profile.source_config):
        diagnostics.append(_composer_diagnostic("source.config", "unsupported_source_config", "仅接受 backlog_path 与 state_path；不要在草稿中传递凭据"))

    allow = lambda key: policy.get(key) is True
    if profile.maker == "deepseek" and not (allow("allow_network") and allow("allow_model")):
        diagnostics.append(_composer_diagnostic("policy", "maker_policy_mismatch", "DeepSeek Maker 必须显式允许网络和模型调用"))
    if profile.maker == "sample" and (allow("allow_network") or allow("allow_model")):
        diagnostics.append(_composer_diagnostic("policy", "unused_permission", "Sample Maker 不需要网络或模型权限", "warning"))
    if profile.delivery == "local_artifact":
        if profile.delivery_config:
            diagnostics.append(_composer_diagnostic("delivery_config", "local_config_forbidden", "local_artifact 不接受 delivery_config"))
        if allow("allow_publish") or allow("allow_deploy"):
            diagnostics.append(_composer_diagnostic("policy", "local_delivery_policy", "local_artifact 禁止发布和部署"))
    if profile.delivery == "github_workflow":
        required = ("allow_network", "allow_model", "allow_git", "allow_publish", "allow_deploy")
        if not all(allow(key) for key in required):
            diagnostics.append(_composer_diagnostic("policy", "github_policy_required", "github_workflow 必须显式允许网络、模型、Git、发布和 Workflow 部署"))
        if allow("allow_ssh"):
            diagnostics.append(_composer_diagnostic("policy.allow_ssh", "github_ssh_forbidden", "github_workflow 禁止 SSH；ECS 仅由仓库 Workflow 接管"))
        allowed_config = {"repo", "branch", "prefix", "port_base", "workflow_deploy"}
        unknown_config = sorted(set(profile.delivery_config) - allowed_config)
        if unknown_config:
            diagnostics.append(_composer_diagnostic("delivery_config", "unsupported_delivery_config", f"不支持的交付配置: {', '.join(unknown_config)}"))
        if "workflow_deploy" in profile.delivery_config and profile.delivery_config["workflow_deploy"] is not True:
            diagnostics.append(_composer_diagnostic("delivery_config.workflow_deploy", "workflow_required", "GitHub Delivery 必须由仓库 Workflow 接管"))
    if profile.compiler == "mumuspec":
        diagnostics.append(_composer_diagnostic("compiler", "experimental_component", "MumuSpec 当前为实验性回退实现", "warning"))
    if profile.id == "fixture-local":
        expected = (profile.source == "local_queue" and profile.compiler == "simple" and profile.maker == "sample" and profile.checkers == ("security",) and profile.delivery == "local_artifact")
        forbidden = any(allow(key) for key in ("allow_network", "allow_model", "allow_git", "allow_ssh", "allow_publish", "allow_deploy"))
        if not expected or forbidden:
            diagnostics.append(_composer_diagnostic("profile", "fixture_baseline_reserved", "fixture-local 是保留的离线安全基线，不能通过草稿改造成外部执行组合"))
    return profile, diagnostics


@app.route("/api/profile-composer/catalog", methods=["GET"])
def profile_composer_catalog():
    return jsonify({"ok": True, "catalog": _composer_catalog_copy()})


@app.route("/api/profile-composer/preflight", methods=["POST"])
def profile_composer_preflight():
    data = request.get_json(silent=True)
    raw_profile = data.get("profile") if isinstance(data, dict) else None
    profile, diagnostics = _composer_preflight(raw_profile)
    valid = profile is not None and not any(item["severity"] == "error" for item in diagnostics)
    payload = {"ok": valid, "valid": valid, "normalized_profile": profile.to_dict() if profile else None,
               "component_graph": _composer_graph(profile) if profile else None, "diagnostics": diagnostics,
               "execution": {"performed": False, "writes": False, "network": False}}
    return jsonify(payload), (200 if valid else 400)


@app.route("/api/profile-composer/profiles", methods=["POST"])
def save_profile_composer_draft():
    """Register a preflighted Profile so it immediately becomes selectable in requirement intake."""
    from engine.core.profiles import ProfileError, persist_profile
    data = request.get_json(silent=True)
    raw_profile = data.get("profile") if isinstance(data, dict) else None
    profile, diagnostics = _composer_preflight(raw_profile)
    valid = profile is not None and not any(item["severity"] == "error" for item in diagnostics)
    if not valid:
        return jsonify({"ok": False, "error": "Profile 预检未通过", "valid": False, "diagnostics": diagnostics}), 400
    try:
        persist_profile(profile)
    except ProfileError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "profile": profile.to_dict(), "ref": profile.ref})


# ── Phase 3：只读 Profile / Run Plan API ──
def _execution_readiness(profile):
    """Report server capability availability without exposing any credential values."""
    data = profile.to_dict() if hasattr(profile, "to_dict") else profile
    blockers = []
    config = load_config()
    if data.get("maker") == "deepseek" and not config.get("DEEPSEEK_API_KEY", "").strip():
        blockers.append("服务端未配置 DEEPSEEK_API_KEY，不能调用 DeepSeek")
    if data.get("delivery") == "github_workflow":
        if not config.get("GITHUB_TOKEN", "").strip():
            blockers.append("服务端未配置 GITHUB_TOKEN，不能推送 GitHub")
        if not __import__("shutil").which("git"):
            blockers.append("服务端未找到 git 命令，不能执行 GitHub Delivery")
    return {"ready": not blockers, "blockers": blockers}


def _profile_payload(profile):
    """Expose server-adjudicated availability without leaking credentials or reimplementing policy in Vue."""
    payload = profile.to_dict() if hasattr(profile, "to_dict") else dict(profile)
    if not payload.get("valid", True):
        return payload
    payload["execution_readiness"] = _execution_readiness(payload)
    try:
        from engine.core.profiles import ProfileError, load_profile
        _studio_executable_profile(load_profile(str(payload["id"])))
        payload["execution_eligible"] = True
        payload["execution_blocker"] = ""
    except ProfileError as exc:
        # This is an informational UI projection only; the execution endpoint repeats the same gate.
        payload["execution_eligible"] = False
        payload["execution_blocker"] = str(exc)[:240]
    return payload


@app.route("/api/profiles", methods=["GET"])
def get_profiles():
    from engine.core.profiles import list_profiles
    return jsonify({"ok": True, "profiles": [_profile_payload(profile) for profile in list_profiles()]})


@app.route("/api/profiles/<profile_id>", methods=["GET"])
def get_profile(profile_id):
    from engine.core.profiles import ProfileError, load_profile, validate_profile
    try:
        profile = load_profile(profile_id)
        validate_profile(profile)
        return jsonify({"ok": True, "profile": _profile_payload(profile), "ref": profile.ref})
    except ProfileError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


def _studio_executable_profile(profile):
    """Use the executor's catalog-and-policy gate for every saved Profile."""
    from engine.core.profiles import validate_profile
    from engine.core.run_executor import ProfileRunExecutor

    validate_profile(profile)
    ProfileRunExecutor.validate_executable(profile)
    return profile


def _pending_profile_task(profile_id, task_id):
    """Resolve a pending task from its Profile source; never trust browser task content."""
    from engine.core.profiles import ProfileError, create_source_adapter, load_profile, validate_profile
    profile = _studio_executable_profile(load_profile(profile_id))
    validate_profile(profile)
    for task in create_source_adapter(profile).list_pending():
        if task.id == task_id and task.status == "pending" and task.profile_id == profile.id:
            return profile, task
    raise ProfileError(f"Profile {profile.id} 没有待执行任务 task_id={task_id}")


def _task_preview(task):
    """Convert only the normalized Adapter task fields required for a Run Plan."""
    return {
        "id": task.id, "title": task.title, "source": task.source,
        "case": task.case, "priority": task.priority,
        "spec_text": task.spec_text or "", "extra": task.extra,
    }


def _public_run_plan(plan):
    """Project a frozen Plan for the browser without returning its execution input body."""
    task = plan.get("task") if isinstance(plan.get("task"), dict) else {}
    profile = plan.get("profile") if isinstance(plan.get("profile"), dict) else {}
    delivery_config = profile.get("delivery_config") if isinstance(profile.get("delivery_config"), dict) else {}
    public_delivery_config = {key: delivery_config[key] for key in ("repo", "branch", "prefix", "port_base", "workflow_deploy")
                              if key in delivery_config}
    return {
        "schema_version": plan.get("schema_version", 1), "id": plan.get("id"), "run_id": plan.get("run_id"),
        "created_at": plan.get("created_at"), "status": plan.get("status"), "digest": plan.get("digest"),
        "profile": {"id": profile.get("id"), "ref": profile.get("ref"), "delivery": profile.get("delivery"),
                    "delivery_config": public_delivery_config},
        "task": {"id": task.get("id"), "title": _public_requirement_title(task, str(task.get("id") or "")),
                 "source": task.get("source"), "priority": task.get("priority", 99)},
        "components": plan.get("components", {}), "policy": plan.get("policy", {}),
    }


@app.route("/api/profiles/<profile_id>/pending-tasks", methods=["GET"])
def get_profile_pending_tasks(profile_id):
    """List pending, Profile-bound tasks for the reviewed Studio execution profiles."""
    from engine.core.profiles import ProfileError, create_source_adapter, load_profile, validate_profile
    try:
        profile = _studio_executable_profile(load_profile(profile_id))
        validate_profile(profile)
        tasks = [
            {"id": task.id, "title": task.title, "source": task.source,
             "priority": task.priority, "case": task.case, "profile_id": task.profile_id}
            for task in create_source_adapter(profile).list_pending()
            if task.status == "pending" and task.profile_id == profile.id
        ]
        return jsonify({"ok": True, "profile_id": profile.id, "tasks": tasks})
    except ProfileError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/run-plans", methods=["GET"])
def get_run_plans():
    from engine.core.profiles import list_run_plans
    try:
        limit = max(1, min(int(request.args.get("limit", "50")), 100))
    except ValueError:
        return jsonify({"ok": False, "error": "limit 必须是整数"}), 400
    return jsonify({"ok": True, "plans": [_public_run_plan(plan) for plan in list_run_plans(limit)]})


@app.route("/api/run-plans/<plan_id>", methods=["GET"])
def get_run_plan(plan_id):
    from engine.core.profiles import ProfileError, get_run_plan
    try:
        return jsonify({"ok": True, "plan": _public_run_plan(get_run_plan(plan_id))})
    except ProfileError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@app.route("/api/run-plans/freeze", methods=["POST"])
def freeze_run_plan():
    """Persist the exact server-resolved Plan that an official Studio user will review."""
    from engine.core.profiles import ProfileError, create_run_plan, persist_run_plan
    data = request.get_json(force=True) or {}
    try:
        profile_id = str(data.get("profile_id", "")).strip()
        task_id = str(data.get("task_id", "")).strip()
        if not profile_id or not task_id:
            raise ProfileError("profile_id 与 task_id 必填")
        profile, task = _pending_profile_task(profile_id, task_id)
        plan = create_run_plan(profile, _task_preview(task))
        persist_run_plan(plan)
        return jsonify({"ok": True, "plan": _public_run_plan(plan.to_dict())})
    except ProfileError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/run-plans/preview", methods=["POST"])
def preview_run_plan():
    """Create a no-write Preview; safe Studio requests resolve their task from the Adapter."""
    from engine.core.profiles import ProfileError, create_run_plan, load_profile
    data = request.get_json(force=True) or {}
    try:
        profile_id = str(data.get("profile_id", ""))
        task_id = str(data.get("task_id", "")).strip()
        if task_id:
            profile, task = _pending_profile_task(profile_id, task_id)
            task = _task_preview(task)
        else:
            profile = load_profile(profile_id)
            task = data.get("task") or {}
        return jsonify({"ok": True, "plan": _public_run_plan(create_run_plan(profile, task).to_dict())})
    except ProfileError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/profile-runs/confirm", methods=["POST"])
def confirm_profile_run():
    """Claim one reviewed Plan and return its Run id before the external pipeline begins."""
    from engine.core.profiles import Profile, ProfileError, claim_run_plan, get_run_plan
    from engine.core.run_executor import ProfileRunExecutor
    data = request.get_json(force=True) or {}
    if data.get("confirmed") is not True:
        return jsonify({"ok": False, "error": "必须显式传入 confirmed=true"}), 400
    profile_id = str(data.get("profile_id", "")).strip()
    task_id = str(data.get("task_id", "")).strip()
    plan_id = str(data.get("plan_id", "")).strip()
    plan_digest = str(data.get("plan_digest", "")).strip()
    if not profile_id or not task_id or not plan_id or not plan_digest:
        return jsonify({"ok": False, "error": "profile_id、task_id、plan_id 与 plan_digest 必填"}), 400
    try:
        plan = get_run_plan(plan_id)
        if plan.get("digest") != plan_digest:
            raise ProfileError("Run Plan digest 不匹配，必须重新审阅")
        if plan.get("profile", {}).get("id") != profile_id or plan.get("task", {}).get("id") != task_id:
            raise ProfileError("Run Plan 与确认的 Profile 或任务不一致，必须重新审阅")
        readiness = _execution_readiness(Profile.from_dict({
            key: value for key, value in plan["profile"].items() if key != "ref"
        }))
        if not readiness["ready"]:
            raise ProfileError("当前执行环境未就绪：" + "；".join(readiness["blockers"]))
        claim = claim_run_plan(plan_id)
    except ProfileError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    def run_claimed_plan():
        from engine.core.profiles import update_run_execution_claim
        try:
            update_run_execution_claim(plan_id, "running")
            result = ProfileRunExecutor().execute_plan(plan_id)
            terminal_reason = "执行已完成。" if result.status == "passed" else "执行未完成；请查看已记录的阶段状态与证据摘要。"
            update_run_execution_claim(plan_id, result.status, reason=terminal_reason)
        except Exception:
            update_run_execution_claim(plan_id, "failed", reason="受控运行异常终止；请查看 Run Detail")

    from threading import Thread
    worker = Thread(target=run_claimed_plan, name=f"loop-run-{claim['run_id']}", daemon=True)
    worker.start()
    return jsonify({"ok": True, "accepted": True, "run": {
        "run_id": claim["run_id"], "status": "queued", "event_count": 0,
    }}), 202


@app.route("/api/profile-runs/<run_id>/state", methods=["GET"])
def get_profile_run_state(run_id):
    """Expose minimal queue state until the verified event projection has a first event."""
    from engine.core.profiles import ProfileError, get_run_execution_claim, get_run_plan
    try:
        plan = get_run_plan(run_id)
        claim = get_run_execution_claim(run_id)
        if claim.get("run_id") not in {None, plan.get("run_id")}:
            raise ProfileError("Run 执行领取记录与冻结 Plan 不一致")
        return jsonify({"ok": True, "run_id": plan["run_id"], "state": claim.get("state", "planned"),
                        "updated_at": claim.get("updated_at"), "reason": claim.get("reason")})
    except ProfileError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@app.route("/api/profile-runs/<run_id>/retry-delivery", methods=["POST"])
def retry_profile_delivery(run_id):
    """明确确认后仅重试失败的 GitHub Delivery；不会重新调用模型。"""
    from engine.core.profiles import ProfileError
    from engine.core.run_executor import ProfileRunExecutor
    data = request.get_json(force=True) or {}
    if data.get("confirmed") is not True:
        return jsonify({"ok": False, "error": "必须显式传入 confirmed=true"}), 400
    try:
        result = ProfileRunExecutor().retry_delivery(run_id)
    except ProfileError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception:
        return jsonify({"ok": False, "error": "Delivery 重试异常终止；请查看 Run 证据"}), 500
    return jsonify({"ok": result.status == "passed", "run": result.to_dict()})


def _run_artifact_payload(run_id):
    """Return only the artifact directory bound to this immutable Run Plan."""
    from engine.core.profiles import ProfileError, get_run_plan

    get_run_plan(run_id)  # validates the id, existence, and frozen-plan digest first
    artifact_dir = (PlatformPaths.OUTPUT_DIR / f"maker-{run_id}").resolve()
    output_root = PlatformPaths.OUTPUT_DIR.resolve()
    if output_root not in artifact_dir.parents or not artifact_dir.is_dir():
        return {
            "available": False,
            "relative_path": f"output/maker-{run_id}",
            "file_count": 0,
            "files": [],
            "preview_url": None,
            "open_local_supported": sys.platform == "darwin",
        }
    files = []
    for path in sorted(artifact_dir.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        relative = path.relative_to(artifact_dir).as_posix()
        files.append({
            "path": relative,
            "bytes": path.stat().st_size,
            "url": f"/output/maker-{run_id}/{relative}",
        })
    index = artifact_dir / "index.html"
    return {
        "available": True,
        "relative_path": f"output/maker-{run_id}",
        "file_count": len(files),
        "files": files[:500],
        "truncated": len(files) > 500,
        "preview_url": f"/output/maker-{run_id}/index.html" if index.is_file() else None,
        "open_local_supported": sys.platform == "darwin",
    }


@app.route("/api/profile-runs/<run_id>/artifact", methods=["GET"])
def get_profile_run_artifact(run_id):
    """Expose the generated local artifact path and file tree for one verified Run."""
    from engine.core.profiles import ProfileError
    try:
        return jsonify({"ok": True, "artifact": _run_artifact_payload(run_id)})
    except ProfileError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@app.route("/api/profile-runs/<run_id>/artifact/open", methods=["POST"])
def open_profile_run_artifact(run_id):
    """Open only this run-bound output directory in Finder when Studio runs locally on macOS."""
    from engine.core.profiles import ProfileError
    try:
        artifact = _run_artifact_payload(run_id)
        if not artifact["available"]:
            return jsonify({"ok": False, "error": "该 Run 尚未生成本地产物"}), 404
        if sys.platform != "darwin":
            return jsonify({"ok": False, "error": "仅本机 macOS Studio 支持在 Finder 中打开目录"}), 400
        import subprocess
        target = PlatformPaths.ROOT / artifact["relative_path"]
        completed = subprocess.run(["open", str(target)], capture_output=True, text=True, timeout=5)
        if completed.returncode:
            return jsonify({"ok": False, "error": "无法打开 Finder 目录"}), 500
        return jsonify({"ok": True, "relative_path": artifact["relative_path"]})
    except ProfileError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


# ── Phase 4：只读 RunEvent / Evidence 投影 API ──
def _observability_limit():
    try:
        return max(1, min(int(request.args.get("limit", "50")), 100))
    except ValueError:
        return None


def _observability_error(exc):
    status = 404 if "不存在" in str(exc) else 400
    return jsonify({"ok": False, "error": str(exc)}), status


@app.route("/api/observability/runs", methods=["GET"])
def get_observability_runs():
    from engine.core.observability import EventError
    from engine.core.observability_projection import ObservabilityProjection
    limit = _observability_limit()
    if limit is None:
        return jsonify({"ok": False, "error": "limit 必须是整数"}), 400
    try:
        runs = ObservabilityProjection().list_runs(limit, request.args.get("status") or None)
        return jsonify({"ok": True, "schema_version": 1, "source": "verified-event-projection", "runs": runs})
    except EventError as exc:
        return _observability_error(exc)


@app.route("/api/observability/runs/<run_id>", methods=["GET"])
def get_observability_run(run_id):
    from engine.core.observability import EventError
    from engine.core.observability_projection import ObservabilityProjection
    try:
        return jsonify({"ok": True, "run": ObservabilityProjection().run(run_id)})
    except EventError as exc:
        return _observability_error(exc)


@app.route("/api/observability/lifecycle", methods=["GET"])
def get_observability_lifecycle():
    from engine.core.observability import EventError
    from engine.core.observability_projection import ObservabilityProjection
    limit = _observability_limit()
    if limit is None:
        return jsonify({"ok": False, "error": "limit 必须是整数"}), 400
    try:
        stages = ObservabilityProjection().lifecycle(limit)
    except EventError as exc:
        return _observability_error(exc)
    return jsonify({"ok": True, "schema_version": 1, "source": "verified-event-projection",
                    "stages": stages})


@app.route("/api/observability/governance-coverage", methods=["GET"])
def get_governance_coverage():
    from engine.core.observability import EventError
    from engine.core.observability_projection import ObservabilityProjection
    limit = _observability_limit()
    if limit is None:
        return jsonify({"ok": False, "error": "limit 必须是整数"}), 400
    try:
        coverage = ObservabilityProjection().governance_coverage(limit)
    except EventError as exc:
        return _observability_error(exc)
    return jsonify({"ok": True, "coverage": coverage})


# ── 只读 WBS 投影：实现计划 ↔ 验收判据 的关联缺口 ──
_WBS_PLAN_REL = os.path.join("mumuspec", "12-implementation-plan.md")
_WBS_FILE_REL = os.path.join("spec", "wbs.json")


def _wbs_case_entries():
    """扫 cases/，按磁盘现状给每个 case 定 WBS 状态。

    GET 不跑编译：编译会写 spec/wbs.json，读接口不应有副作用。因此未编译的
    case 只报状态和原因，不替它生成。区分「没计划」和「有计划未编」很有必要：
    后者跑一次工具就能补齐，前者得先回去补 MumuSpec 第 12 轮。
    """
    cases_dir = str(PlatformPaths.CASES_DIR)
    if not os.path.isdir(cases_dir):
        return []
    entries = []
    for name in sorted(os.listdir(cases_dir)):
        cdir = os.path.join(cases_dir, name)
        if not os.path.isdir(cdir):
            continue
        wbs_path = os.path.join(cdir, _WBS_FILE_REL)
        has_plan = os.path.isfile(os.path.join(cdir, _WBS_PLAN_REL))
        if os.path.isfile(wbs_path):
            try:
                payload = _read_json(wbs_path)
            except (json.JSONDecodeError, OSError) as exc:
                entries.append({"name": name, "status": "unreadable", "reason": str(exc)})
                continue
            findings = payload.get("findings", {})
            entries.append({
                "name": name, "status": "compiled", "source": payload.get("source"),
                "summary": payload.get("summary", {}),
                "uncovered_ac": findings.get("uncovered_ac", []),
                "dangling_ac": findings.get("dangling_ac", []),
                "plan_only_routes": findings.get("plan_only_routes", []),
                "ac_declaration": findings.get("ac_declaration"),
            })
        elif has_plan:
            entries.append({"name": name, "status": "plan_not_compiled"})
        else:
            entries.append({"name": name, "status": "no_plan"})
    return entries


@app.route("/api/observability/wbs", methods=["GET"])
def get_observability_wbs():
    entries = _wbs_case_entries()
    counts = {}
    for item in entries:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return jsonify({
        "ok": True, "schema_version": 1, "source": "cases/* " + _WBS_FILE_REL,
        "counts": counts,
        "gap_total": sum(1 for i in entries if i["status"] == "compiled" and (
            i.get("uncovered_ac") or i.get("dangling_ac") or i.get("plan_only_routes")
            or i.get("ac_declaration"))),
        "cases": entries,
        "limitations": ["只读已落盘的 wbs.json；本接口不跑编译，不反映计划文件的新于产物"],
    })


@app.route("/api/observability/wbs/<name>", methods=["GET"])
def get_observability_wbs_case(name):
    if os.sep in name or ".." in name:
        return jsonify({"ok": False, "error": "case 名不合法"}), 400
    wbs_path = os.path.join(str(PlatformPaths.CASES_DIR), name, _WBS_FILE_REL)
    if not os.path.isfile(wbs_path):
        has_plan = os.path.isfile(os.path.join(str(PlatformPaths.CASES_DIR), name, _WBS_PLAN_REL))
        hint = ("有 12-plan，跑 engine/tools/wbs_compiler.py --name " + name + " 可生成"
                if has_plan else "无 mumuspec/12-implementation-plan.md，无法编译 WBS")
        return jsonify({"ok": False, "error": f"wbs.json 不存在：{hint}"}), 404
    try:
        return jsonify({"ok": True, "wbs": _read_json(wbs_path)})
    except (json.JSONDecodeError, OSError) as exc:
        return jsonify({"ok": False, "error": f"wbs.json 解析失败：{exc}"}), 500


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

# Phase 2: 统一改用 PlatformPaths，取消 LOOP_DIR 拼接
def _feishu_docs_path():
    return str(PlatformPaths.DATA_DIR / "backlog.json")

def _feishu_state_path():
    return str(PlatformPaths.DATA_DIR / "state.json")

CONFIG_PATH = str(PlatformPaths.CONFIG_FILE)
RUN_BACKLOG = str(PlatformPaths.PIPELINE_DIR / "run.py")
GATE_PY = str(PlatformPaths.ENGINE_DIR / "gate.py")
GENERATE_PY = str(PlatformPaths.ENGINE_DIR / "generate.py")


# ── Requirements API ──
# Backlog text and document tokens are execution inputs, not Studio read-model fields.
# Keep them in the persisted queue and immutable Run Plan only; never reflect them through
# a browser GET endpoint, where historical content might contain credentials or private data.
_SENSITIVE_TITLE_MARKERS = ("api_key", "apikey", "token", "password", "credential", "secret", "private_key")
_REQUIREMENT_BODY_SUMMARY = "需求正文仅在服务端冻结 Plan 中受控使用，正式列表不展示原文。"


def _public_requirement_title(doc, task_id):
    title = str(doc.get("title") or "").strip()
    if not title or any(marker in title.lower() for marker in _SENSITIVE_TITLE_MARKERS):
        return f"需求 {task_id}"
    return title[:120]


def _public_backlog_entry(doc, task_state):
    task_id = str(doc.get("id", ""))
    state = task_state if isinstance(task_state, dict) else {}
    return {
        "id": task_id,
        "title": _public_requirement_title(doc, task_id),
        "priority": doc.get("priority", 99),
        "profile_id": str(doc.get("profile_id") or ""),
        "pending": state.get("status") not in ("done", "fetched"),
        "status": state.get("status", "pending"),
        "attempts": state.get("attempts"),
    }


@app.route("/api/requirements", methods=["GET"])
def get_requirements():
    """Return public requirement metadata, verified Runs, and no persisted requirement body."""
    from engine.core.observability_projection import ObservabilityProjection

    docs_path, state_path = _feishu_docs_path(), _feishu_state_path()
    docs = _read_json(docs_path).get("docs", []) if os.path.exists(docs_path) else []
    state = _read_json(state_path) if os.path.exists(state_path) else {}
    runs_by_task = {}
    for run in ObservabilityProjection().list_runs(limit=100):
        task = run.get("task") or {}
        task_id = task.get("id")
        if task_id:
            runs_by_task.setdefault(task_id, []).append(run)

    requirements = []
    for doc in docs:
        task_id = str(doc.get("id", ""))
        task_runs = runs_by_task.get(task_id, [])
        requirement = _public_backlog_entry(doc, state.get(task_id, {}))
        requirement.update({
            "description": _REQUIREMENT_BODY_SUMMARY,
            "runs": task_runs,
            "latest_run_id": task_runs[0]["run_id"] if task_runs else None,
        })
        requirements.append(requirement)
    return jsonify({"ok": True, "source": "backlog-and-verified-runs", "requirements": requirements})


# ── Backlog API ──
@app.route("/api/backlog", methods=["GET"])
def get_backlog():
    """Compatibility read endpoint with the same no-body/no-token public projection."""
    docs_path = _feishu_docs_path()
    state_path = _feishu_state_path()
    docs = _read_json(docs_path).get("docs", []) if os.path.exists(docs_path) else []
    state = _read_json(state_path) if os.path.exists(state_path) else {}
    items = [_public_backlog_entry(doc, state.get(str(doc.get("id", "")), {})) for doc in docs]
    items.sort(key=lambda item: (item["priority"], item["id"]))
    return jsonify({"docs": items, "source": "feishu"})


@app.route("/api/compat/overview", methods=["GET"])
def compatibility_overview():
    """Return a reviewed, read-only projection for the isolated Vue preview.

    This intentionally does not delegate the legacy API payloads to the browser:
    backlog text/tokens, Profile policy, Run Plan details and arbitrary trace data
    remain server-side until versioned observability contracts are available.
    """
    docs_path = _feishu_docs_path()
    state_path = _feishu_state_path()
    raw_docs = _read_json(docs_path).get("docs", []) if os.path.exists(docs_path) else []
    states = _read_json(state_path) if os.path.exists(state_path) else {}
    backlog = []
    for doc in raw_docs:
        item_id = str(doc.get("id", ""))
        state = states.get(item_id, {})
        backlog.append({
            "id": item_id,
            "title": str(doc.get("title") or item_id),
            "priority": doc.get("priority", 99),
            "profile_id": str(doc.get("profile_id") or ""),
            "pending": state.get("status") not in ("done", "fetched"),
            "status": str(state.get("status") or "pending"),
            "attempts": state.get("attempts"),
        })
    backlog.sort(key=lambda item: (item["priority"], item["id"]))

    from engine.core.profiles import list_profiles, list_run_plans
    profiles = [{
        "id": item.get("id"), "ref": item.get("ref"),
        "description": item.get("description"), "source": item.get("source"),
        "compiler": item.get("compiler"), "maker": item.get("maker"),
        "checkers": item.get("checkers"), "delivery": item.get("delivery"),
        "valid": item.get("valid", False),
    } for item in list_profiles()]
    plans = [{
        "id": item.get("id"), "run_id": item.get("run_id"),
        "created_at": item.get("created_at"), "status": item.get("status"),
        "digest": item.get("digest"), "profile_ref": (item.get("profile") or {}).get("ref", ""),
    } for item in list_run_plans(50)]

    try:
        from checker import get_checks
        checks = [{
            "id": item.get("id"), "name": item.get("name"),
            "quadrant": item.get("quadrant"), "quadrant_label": item.get("quadrant_label"),
            "category": item.get("category"), "mock": bool(item.get("mock")),
            "auto": bool(item.get("auto")), "active": bool(item.get("active")),
        } for item in get_checks()]
    except Exception:  # Legacy checker availability must not make unsupported claims.
        checks = []

    events, pagination = [], {"limit": 100, "offset": 0, "has_more": False}
    try:
        import tracer
        raw_events = tracer.query(limit=100, event_type=None, offset=0)
        for event in raw_events:
            if event.get("event") == "case_done" and event.get("result") in ("pass", "fail"):
                events.append({key: event.get(key) for key in (
                    "_ts", "event", "case", "task", "run_id", "profile", "result", "attempts", "elapsed"
                )})
    except ImportError:
        pass

    return jsonify({
        "ok": True, "schema_version": 1, "source": "legacy-flask-compatible",
        "backlog": backlog, "profiles": profiles, "run_plans": plans, "checks": checks,
        "trace": {"events": events, "pagination": pagination},
    })


@app.route("/api/backlog", methods=["POST"])
def add_backlog():
    data = request.get_json(force=True) or {}
    title = (data.get("title") or "").strip()
    spec_text = (data.get("spec_text") or "").strip()
    link = data.get("link", "")
    profile_id = str(data.get("profile_id", "")).strip()
    kind, token = (None, None)
    if link:
        import re
        m = re.search(r"(wiki|docx|docs)/([A-Za-z0-9]+)", link)
        if m:
            kind = "wiki_token" if m.group(1) == "wiki" else "doc_token"
            token = m.group(2)
    if not spec_text and not token:
        return jsonify({"ok": False, "error": "请填写需求描述或粘贴飞书链接"}), 400
    if profile_id:
        from engine.core.profiles import ProfileError, load_profile
        try:
            _studio_executable_profile(load_profile(profile_id))
        except ProfileError as exc:
            return jsonify({"ok": False, "error": f"Profile 当前不可执行: {exc}"}), 400

    docs_path = _feishu_docs_path()
    cfg = _read_json(docs_path) if os.path.exists(docs_path) else {"docs": []}
    docs_list = cfg.setdefault("docs", [])
    nid = f"FS-{len(docs_list)+1:03d}"
    if not title:
        title = f"需求 {nid}"
    entry = {"id": nid, "title": title, "priority": int(data.get("priority", len(docs_list) + 1))}
    if profile_id:
        entry["profile_id"] = profile_id
    if kind and token:
        entry[kind] = token
    if spec_text:
        entry["spec_text"] = spec_text
    docs_list.append(entry)
    _write_json(docs_path, cfg)
    return jsonify({"ok": True, "id": nid, "entry": _public_backlog_entry(entry, {})})


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


# ── Better Harness 流程分析 ──
_QODER_CLI = None

def _find_qodercli():
    """查找 Qoder Desktop 内置的 qodercli（v1.x），fallback 到 PATH 里的旧版。"""
    global _QODER_CLI
    if _QODER_CLI and os.path.isfile(_QODER_CLI):
        return _QODER_CLI
    candidates = [
        "/Applications/QoderWork.app/Contents/Resources/bin/qodercli",
        "/Applications/QoderWake.app/Contents/Resources/payload/qodercli",
        "/usr/local/bin/qodercli",
    ]
    for c in candidates:
        if os.path.isfile(c):
            _QODER_CLI = c
            return c
    # 最后试 which
    import shutil
    found = shutil.which("qodercli")
    if found:
        _QODER_CLI = found
    return _QODER_CLI

_bh_state = {"running": False, "log": "", "success": False, "error": None}
_bh_lock = __import__("threading").Lock()


def _run_bh_bg(target_dir=None):
    """后台线程：调 Qoder CLI 在指定目录跑 /better-harness。
    target_dir: 要分析的项目目录（Loop 生成的代码），留空则分析平台自身。"""
    import subprocess as _sp
    cwd = os.path.abspath(target_dir) if target_dir else REPO_ROOT
    cli = _find_qodercli()
    state = _bh_state
    if not cli:
        state["error"] = "未找到 qodercli（请安装 Qoder Desktop 或将 qodercli 加入 PATH）"
        state["running"] = False
        return
    try:
        state["log"] = f"[$ qodercli /better-harness] 开始分析（cwd={cwd}）…\n"
        proc = _sp.Popen(
            [cli, "-p", "--permission-mode", "bypass_permissions", "-w", cwd, "/better-harness"],
            cwd=cwd, stdout=_sp.PIPE, stderr=_sp.STDOUT, text=True, bufsize=1,
        )
        for line in proc.stdout or ():
            state["log"] += line
        proc.wait()
        state["success"] = proc.returncode == 0
        if proc.returncode != 0:
            state["error"] = f"qodercli 退出码 {proc.returncode}"
        # 检查产物
        bh_dir = os.path.join(cwd, ".qoder", "better-harness")
        if os.path.isdir(bh_dir):
            state["log"] += f"\n✅ 诊断产物目录: {bh_dir}"
        else:
            state["log"] += "\n⚠ 未找到 .qoder/better-harness 产物目录"
    except FileNotFoundError:
        state["error"] = f"qodercli 不可用: {cli}"
    except Exception as exc:
        state["error"] = str(exc)
    finally:
        state["running"] = False
        state["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _bh_lock.release()


@app.route("/api/better-harness/analyze", methods=["POST"])
def bh_analyze():
    """触发 Better Harness 流程分析（后台运行 qodercli /better-harness）。
    body(可选): {"dir": "output/maker-xxx"} → 分析指定目录（生成的代码项目）
              留空 → 分析 Loop 平台自身"""
    if not _bh_lock.acquire(blocking=False):
        return jsonify({"ok": False, "busy": True, "message": "上一次分析尚未完成"}), 409
    import threading as _th
    body = request.get_json(silent=True) or {}
    target_dir = body.get("dir", "").strip() or None
    _bh_state.update({"running": True, "log": "", "success": False, "error": None,
                       "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "target_dir": target_dir or str(REPO_ROOT)})
    _th.Thread(target=_run_bh_bg, args=(target_dir,), daemon=True).start()
    return jsonify({"ok": True, "started_at": _bh_state["started_at"],
                    "target_dir": _bh_state["target_dir"]})


@app.route("/api/better-harness/status", methods=["GET"])
def bh_status():
    """查询 Better Harness 分析状态"""
    return jsonify(_bh_state)


@app.route("/api/better-harness/report", methods=["GET"])
def bh_report():
    """返回 Better Harness 诊断报告。
    ?dir=<path> → 查指定生成项目目录
    无参 → 查 Loop 平台本身"""
    target_dir = request.args.get("dir", "").strip()
    if target_dir:
        # 相对路径 → 绝对路径
        if not os.path.isabs(target_dir):
            target_dir = os.path.join(REPO_ROOT, target_dir)
        if not os.path.isdir(target_dir):
            return jsonify({"ok": False, "error": f"目录不存在: {target_dir}", "findings": None, "canvas": None}), 404
        search_root = target_dir
    else:
        search_root = REPO_ROOT

    report_data = {"ok": False, "error": "未找到 Better Harness 诊断报告", "findings": None, "canvas": None, "dir": target_dir or REPO_ROOT}
    bh_dir = os.path.join(search_root, ".qoder", "better-harness")

    # 查找最新 findings.json
    findings_path = None
    findings_ts = ""
    if os.path.isdir(bh_dir):
        for date_dir in sorted(os.listdir(bh_dir), reverse=True):
            dp = os.path.join(bh_dir, date_dir)
            if not os.path.isdir(dp):
                continue
            for ts_dir in sorted(os.listdir(dp), reverse=True):
                fp = os.path.join(dp, ts_dir, "findings.json")
                if os.path.isfile(fp) and ts_dir > findings_ts:
                    findings_ts = ts_dir
                    findings_path = fp

    if findings_path:
        try:
            with open(findings_path, encoding="utf-8") as f:
                report_data["findings"] = json.load(f)
            canvas_path = os.path.join(os.path.dirname(findings_path), "canvas.json")
            if os.path.isfile(canvas_path):
                with open(canvas_path, encoding="utf-8") as f:
                    report_data["canvas"] = json.load(f)
            report_data["ok"] = True
            report_data["error"] = None
            report_data["report_time"] = os.path.basename(os.path.dirname(findings_path))
        except (json.JSONDecodeError, OSError) as e:
            report_data["error"] = f"读取报告文件失败: {e}"
            return jsonify(report_data), 500
    return jsonify(report_data)


@app.route("/api/better-harness/projects", methods=["GET"])
def bh_projects():
    """扫描 output/ 目录，返回有 findings.json 的生成项目列表。
    前端拿来自动选最新项目显示报告。"""
    output_dir = str(PlatformPaths.OUTPUT_DIR)
    projects = []
    if not os.path.isdir(output_dir):
        return jsonify({"ok": True, "projects": projects})
    for entry in sorted(os.listdir(output_dir), reverse=True):
        dp = os.path.join(output_dir, entry)
        if not os.path.isdir(dp):
            continue
        bh_dir = os.path.join(dp, ".qoder", "better-harness")
        if not os.path.isdir(bh_dir):
            continue
        # 找最新 findings.json
        latest_ts = ""
        latest_path = None
        for date_dir in sorted(os.listdir(bh_dir), reverse=True):
            ddp = os.path.join(bh_dir, date_dir)
            if not os.path.isdir(ddp):
                continue
            for ts_dir in sorted(os.listdir(ddp), reverse=True):
                fp = os.path.join(ddp, ts_dir, "findings.json")
                if os.path.isfile(fp) and ts_dir > latest_ts:
                    latest_ts = ts_dir
                    latest_path = fp
        if latest_path:
            try:
                with open(latest_path, encoding="utf-8") as f:
                    findings = json.load(f)
                dims = findings.get("summary", {}).get("dimensions", [])
                avg_score = int(sum(d.get("score", 0) for d in dims) / len(dims)) if dims else 0
                projects.append({
                    "name": entry,
                    "dir": os.path.relpath(dp, REPO_ROOT),
                    "score": avg_score,
                    "findings_count": len(findings.get("findings", [])),
                    "report_time": latest_ts,
                })
            except (json.JSONDecodeError, OSError):
                pass
    return jsonify({"ok": True, "projects": projects})


@app.route("/api/output/projects", methods=["GET"])
def output_projects():
    """分页扫描 output/ 目录，返回生成项目列表及是否还有下一页。"""
    output_dir = os.path.join(REPO_ROOT, "output")
    projects = []
    has_more = False
    try:
        limit = max(1, min(int(request.args.get("limit", "24")), 100))
        requested_offset = max(0, int(request.args.get("offset", "0")))
    except ValueError:
        return jsonify({"ok": False, "error": "limit 和 offset 必须是整数"}), 400
    offset = requested_offset
    if not os.path.isdir(output_dir):
        return jsonify({"ok": True, "projects": projects,
                        "pagination": {"limit": limit, "offset": requested_offset, "has_more": False}})

    # 读 runs.jsonl 元数据（按 dir 名索引，也索引 case 名用于模糊匹配 maker-*）
    runs_meta = {}
    runs_by_case = {}
    runs_path = os.path.join(output_dir, "runs.jsonl")
    if os.path.isfile(runs_path):
        try:
            with open(runs_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        run = json.loads(line)
                        d = run.get("dir", "")
                        d = d.replace("output/", "") if d.startswith("output/") else d
                        entry_meta = {
                            "case": run.get("case", ""),
                            "result": run.get("result", ""),
                            "attempts": run.get("attempts", 0),
                            "determinism": run.get("determinism", ""),
                            "model": run.get("model", ""),
                            "cost_yuan": run.get("cost_yuan"),
                            "finished_at": run.get("finished_at", run.get("ts", "")),
                            "dir": d,
                        }
                        runs_meta[d] = entry_meta
                        # 也按 case 名索引（取最后一次）
                        c = run.get("case", "")
                        if c:
                            runs_by_case[c] = entry_meta
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

    for entry in sorted(os.listdir(output_dir), reverse=True):
        dp = os.path.join(output_dir, entry)
        if not os.path.isdir(dp):
            continue

        # Better Harness 报告（先检查，决定是否保留该项目）
        better_harness_score = None
        better_harness_findings_count = None
        better_harness_report_time = None
        has_better_harness = False
        better_harness_dir = os.path.join(dp, ".qoder", "better-harness")
        if os.path.isdir(better_harness_dir):
            for date_dir in sorted(os.listdir(better_harness_dir), reverse=True):
                ddp = os.path.join(better_harness_dir, date_dir)
                if not os.path.isdir(ddp):
                    continue
                for ts_dir in sorted(os.listdir(ddp), reverse=True):
                    fp = os.path.join(ddp, ts_dir, "findings.json")
                    if os.path.isfile(fp):
                        try:
                            with open(fp, encoding="utf-8") as f:
                                findings = json.load(f)
                            dims = findings.get("summary", {}).get("dimensions", [])
                            better_harness_score = int(sum(d.get("score", 0) for d in dims) / len(dims)) if dims else 0
                            better_harness_findings_count = len(findings.get("findings", []))
                            better_harness_report_time = ts_dir
                            has_better_harness = True
                        except (json.JSONDecodeError, OSError):
                            pass
                        break
                if has_better_harness:
                    break

        # 只显示 maker-* 目录，或有 BH 报告的旧格式目录
        is_maker = entry.startswith("maker-")
        if not is_maker and not has_better_harness:
            continue

        # 先分页，再读取项目内的文件、Git、prompt 和诊断详情；避免历史量大时
        # 对本页之外的每一个项目进行递归扫描。
        if offset:
            offset -= 1
            continue
        if len(projects) >= limit:
            has_more = True
            break

        # 文件数 + 文件列表（顶层文件）
        try:
            all_files = []
            for root, _, files in os.walk(dp):
                for f in files:
                    all_files.append(os.path.relpath(os.path.join(root, f), dp))
            file_count = len(all_files)
        except OSError:
            all_files = []
            file_count = 0

        # 技术栈检测
        top_files = [f for f in all_files if "/" not in f]
        has_app_py = "app.py" in top_files
        has_requirements = "requirements.txt" in top_files
        has_index_html = "index.html" in top_files
        if has_app_py and has_requirements:
            tech_stack = "Python Flask"
        elif has_index_html and not has_app_py:
            tech_stack = "HTML 单页"
        elif has_app_py:
            tech_stack = "Python"
        elif has_index_html:
            tech_stack = "HTML + Flask"
        else:
            tech_stack = "通用"

        # 读取 _prompt.txt → 需求描述
        requirement = ""
        prompt_path = os.path.join(dp, "_prompt.txt")
        if os.path.isfile(prompt_path):
            try:
                with open(prompt_path, encoding="utf-8") as f:
                    raw = f.read(2048)
                # 统一处理真实换行和字面 \n
                raw = raw.replace("\\n", "\n")
                lines = raw.split("\n")
                # 取第一个有效行（跳过系统提示行、空白行）
                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if stripped.startswith("你是代码生成器") or stripped.startswith("你是一个") or stripped.startswith("你是"):
                        continue
                    if stripped.startswith("<<<FILE") or stripped.startswith("<<<ENDFILE"):
                        continue
                    if stripped.startswith("用 <<<FILE") or stripped.startswith("请用"):
                        continue
                    requirement = stripped[:200]
                    break
                if not requirement:
                    # 回退：取第一个非空行
                    for line in lines:
                        s = line.strip()
                        if s:
                            requirement = s[:200]
                            break
            except OSError:
                pass

        # 生成时间戳：从目录名提取
        # maker-20260729-234132-xxx → 2026-07-29 23:41
        # 20260724-193006-education → 2026-07-24 19:30
        gen_time = ""
        ts_part = entry.replace("maker-", "")  # 处理 maker- 和旧格式
        if len(ts_part) >= 15 and ts_part[8] == "-":
            # maker-YYYYMMDD-HHMMSS-hash
            try:
                date_str = ts_part[:8]
                time_str = ts_part[9:15]
                gen_time = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}"
            except (ValueError, IndexError):
                pass
        elif len(ts_part) >= 13 and ts_part[8] == "-":
            # YYYYMMDD-HHMMSS-case (旧格式)
            try:
                date_str = ts_part[:8]
                time_str = ts_part[9:15]
                gen_time = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}"
            except (ValueError, IndexError):
                pass

        # LLM 原始输出大小（粗略成本指标）
        llm_size = 0
        llm_path = os.path.join(dp, "_llm_raw.txt")
        if os.path.isfile(llm_path):
            try:
                llm_size = os.path.getsize(llm_path)
            except OSError:
                pass

        # 验证结果（_verify.log 存在则读取）
        verify_result = ""
        verify_path = os.path.join(dp, "_verify.log")
        if os.path.isfile(verify_path):
            try:
                with open(verify_path, encoding="utf-8") as f:
                    vtext = f.read(1024)
                if "PASS" in vtext.upper():
                    verify_result = "pass"
                elif "FAIL" in vtext.upper():
                    verify_result = "fail"
                else:
                    verify_result = "partial"
            except OSError:
                pass

        # Git 提交状态 + remote URL（检查 .git 目录）
        git_dir = os.path.join(dp, ".git")
        git_committed = os.path.isdir(git_dir)
        git_remote_url = ""
        if git_committed:
            git_config = os.path.join(git_dir, "config")
            if os.path.isfile(git_config):
                try:
                    with open(git_config, encoding="utf-8") as f:
                        in_remote = False
                        for line in f:
                            line = line.strip()
                            if line.startswith("[remote"):
                                in_remote = True
                            elif line.startswith("[") and in_remote:
                                in_remote = False
                            elif in_remote and line.startswith("url "):
                                url = line.split("=", 1)[-1].strip()
                                # 处理各种 URL 格式
                                if url.startswith("https://") or url.startswith("http://"):
                                    git_remote_url = url.rstrip("/")
                                elif url.startswith("git@"):
                                    # git@github.com:user/repo.git → https://github.com/user/repo
                                    git_remote_url = "https://" + url.replace(":", "/", 1).replace("git@", "").replace(".git", "")
                                break
                except OSError:
                    pass

        # 尝试匹配 runs.jsonl（先精确匹配目录名，再按 case 名模糊匹配）
        meta = runs_meta.get(entry, {})
        if not meta and requirement:
            # 模糊匹配：用 _prompt 关键词在 runs_by_case 中找
            for case_name, case_meta in runs_by_case.items():
                if case_name.lower() in requirement.lower():
                    meta = case_meta
                    break

        projects.append({
            "name": entry,
            "dir": os.path.relpath(dp, REPO_ROOT),
            "case": meta.get("case", ""),
            "result": meta.get("result", ""),
            "attempts": meta.get("attempts", 0),
            "determinism": meta.get("determinism", ""),
            "model": meta.get("model", ""),
            "cost_yuan": meta.get("cost_yuan"),
            "finished_at": meta.get("finished_at", ""),
            "file_count": file_count,
            "gen_time": gen_time,
            "requirement": requirement,
            "tech_stack": tech_stack,
            "llm_size": llm_size,
            "verify_result": verify_result,
            "git_committed": git_committed,
            "git_remote_url": git_remote_url,
            "has_better_harness": has_better_harness,
            "better_harness_score": better_harness_score,
            "better_harness_findings_count": better_harness_findings_count,
            "better_harness_report_time": better_harness_report_time,
        })
    return jsonify({"ok": True, "projects": projects,
                    "pagination": {"limit": limit, "offset": requested_offset,
                                   "has_more": has_more}})


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
        try:
            limit = max(1, min(int(request.args.get("limit", "100")), 100))
            offset = max(0, int(request.args.get("offset", "0")))
        except ValueError:
            return jsonify({"ok": False, "error": "limit 和 offset 必须是整数"}), 400
        event_type = request.args.get("event", "").strip() or None
        # 多取一条，以无状态的 JSONL 兼容层准确得出是否存在下一页。
        events = tracer.query(limit=limit + 1, event_type=event_type, offset=offset)
        has_more = len(events) > limit
        if has_more:
            events = events[1:]
        return jsonify({"ok": True, "events": events, "metrics": tracer.metrics(),
                        "pagination": {"limit": limit, "offset": offset, "has_more": has_more}})
    except ImportError:
        return jsonify({"ok": True, "events": [], "metrics": {},
                        "pagination": {"limit": 0, "offset": 0, "has_more": False}})


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


# ── Spec 编译 ──
@app.route("/api/spec/compile", methods=["POST"])
def spec_compile():
    """运行 MumuSpec 六轮编译（mock 或真实 LLM），返回生成的 Spec 文档。

    无 DEEPSEEK_API_KEY 时强制 mock（内置样例）；有 key 且未显式 mock 时走真实 LLM。
    """
    import subprocess
    data = request.get_json(silent=True) or {}
    requirement = (data.get("requirement") or "").strip()
    name = (data.get("name") or "spec-demo").strip() or "spec-demo"
    has_key = bool(os.environ.get("DEEPSEEK_API_KEY") or load_config().get("DEEPSEEK_API_KEY", "").strip())
    use_mock = bool(data.get("mock", not has_key))
    if not use_mock and not requirement:
        return jsonify({"ok": False, "error": "真实 LLM 模式需要提供需求文本"}), 400

    root = find_root()
    cli = str(root / "engine" / "tools" / "mumuspec_compiler.py")
    cmd = [sys.executable, cli, "--name", name]
    if use_mock:
        cmd.append("--mock")
    else:
        cmd.extend(["--text", requirement])
    try:
        proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=1800)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": f"编译执行失败: {exc}"}), 500
    if proc.returncode != 0:
        return jsonify({"ok": False, "error": (proc.stderr or proc.stdout or "编译失败")[-1200:]}), 500

    case_dir = root / "cases" / name
    docs = []
    for sub in ("mumuspec", "spec"):
        subdir = case_dir / sub
        if not subdir.is_dir():
            continue
        for f in sorted(subdir.iterdir()):
            if not f.is_file():
                continue
            try:
                content = f.read_text(encoding="utf-8")
            except Exception:  # noqa: BLE001
                content = f.read_text(encoding="utf-8", errors="ignore")
            docs.append({"path": f"{sub}/{f.name}", "name": f.name, "content": content})

    if not docs:
        return jsonify({"ok": False, "error": "编译未产出文档"}), 500
    return jsonify({"ok": True, "name": name, "mock": use_mock, "docs": docs})


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



# ── 设计稿层：原型 29 页 + 覆盖度（只读，不影响正式路径）──
DESIGN_DIR = os.path.join(STUDIO_DIR, "design")
if DESIGN_DIR not in sys.path:
    sys.path.insert(0, DESIGN_DIR)


@app.route("/design")
def design_prototype():
    """29 页设计稿：右上角可切「真实平台视图」，未接后端的菜单置灰。"""
    return send_from_directory(DESIGN_DIR, "proto2.html")


@app.route("/design/v12")
def design_v12():
    """29 页设计稿原版（全部可点，给客户演示用）。"""
    return send_from_directory(DESIGN_DIR, "v12.html")


@app.route("/api/coverage")
def api_coverage():
    """哪些页面真有后端 —— 原型据此决定菜单是否置灰。"""
    from coverage import build_coverage
    return jsonify(build_coverage(app))


# ── 启动 ──
if __name__ == "__main__":
    port = int(os.environ.get("STUDIO_PORT", "5101"))
    host = os.environ.get("STUDIO_HOST", "127.0.0.1")
    debug = os.environ.get("STUDIO_DEBUG", "0") == "1"
    print(f"Loop 配置工作台: http://{host}:{port}  鉴权: {'ON' if STUDIO_TOKEN else 'OFF'}")
    # threaded=True：SSE 长连接(/api/maker/stream)与后台生成不再独占唯一 worker，
    # 否则 /output 静态请求会排队变慢。
    app.run(host=host, port=port, debug=debug, threaded=True)
