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

import json
import os
import subprocess
import sys
import threading
import time

from flask import Flask, jsonify, render_template, request

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


def _run_backlog_bg():
    """后台线程:子进程跑 delivery-loop/run_backlog.sh(它自己 source config.env + .env),
    实时把输出累积到 _trigger_state['log']。锁在 /api/trigger 里 acquire,这里 finally 释放。"""
    env = dict(os.environ)
    for k, v in _DELIVERY_DEFAULTS.items():
        env.setdefault(k, v)  # 仅兜底:已导出的同名变量优先
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
    正在跑时返回 409(不排队),对齐 webhook 的 busy 语义。"""
    if not _trigger_lock.acquire(blocking=False):
        return jsonify({"ok": False, "busy": True, "reason": "上一批仍在运行"}), 409
    _trigger_state.update({
        "running": True, "exit_code": None,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": None, "log": "",
    })
    threading.Thread(target=_run_backlog_bg, daemon=True).start()
    return jsonify({"ok": True, "started_at": _trigger_state["started_at"]})


@app.route("/api/trigger/status", methods=["GET"])
def trigger_status():
    """前端轮询:回当前交付批次的运行状态与实时日志。"""
    return jsonify(_trigger_state)


if __name__ == "__main__":
    port = int(os.environ.get("STUDIO_PORT", "5100"))
    print(f"Harness-4 配置工作台: http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=True)
