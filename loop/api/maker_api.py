"""Maker API 路由。"""

import json, os, sys, threading, time, uuid as _uuid
from flask import Blueprint, request, Response, jsonify

maker_bp = Blueprint("maker", __name__)
LOOP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_DIR = os.path.join(LOOP_DIR, "engine")
sys.path.insert(0, ENGINE_DIR)
sys.path.insert(0, os.path.join(LOOP_DIR))

_maker_tasks: dict[str, dict] = {}


@maker_bp.route("/run", methods=["POST"])
def maker_run():
    """异步启动代码生成。"""
    data = request.get_json(force=True) or {}
    prompt = data.get("prompt", "")
    maker_name = data.get("maker", "deepseek")
    if not prompt:
        return jsonify({"ok": False, "error": "prompt 参数不能为空"}), 400

    task_id = str(_uuid.uuid4())[:8]
    _maker_tasks[task_id] = {"status": "pending", "maker": maker_name, "started_at": time.time()}

    def _run():
        try:
            from makers import load_maker
            maker = load_maker(maker_name)
            ts = time.strftime("%Y%m%d-%H%M%S")
            tmpdir = os.path.join(os.path.dirname(LOOP_DIR), "output", f"maker-{ts}-{task_id}")
            os.makedirs(tmpdir, exist_ok=True)
            result = maker.generate(tmpdir, prompt)
            _maker_tasks[task_id]["status"] = "done" if result.success else "failed"
            _maker_tasks[task_id]["files"] = list(result.files.keys()) if result.files else []
            _maker_tasks[task_id]["output_dir"] = result.output_dir
            _maker_tasks[task_id]["error"] = result.error if not result.success else ""
            _maker_tasks[task_id]["cost_yuan"] = result.cost_estimate_yuan
        except Exception as e:
            _maker_tasks[task_id]["status"] = "failed"
            _maker_tasks[task_id]["error"] = str(e)
        _maker_tasks[task_id]["finished_at"] = time.time()

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "task_id": task_id, "maker": maker_name})


@maker_bp.route("/status", methods=["GET"])
def maker_status():
    task_id = request.args.get("task", "")
    if not task_id or task_id not in _maker_tasks:
        return jsonify({"ok": False, "error": "task_id 不存在"}), 404
    return jsonify(_maker_tasks[task_id])


@maker_bp.route("/stream/<task_id>", methods=["GET"])
def maker_stream(task_id):
    def generate():
        while True:
            data = _maker_tasks.get(task_id, {})
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            if data.get("status") in ("done", "failed"):
                break
            time.sleep(1)
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@maker_bp.route("/list", methods=["GET"])
def maker_list():
    import shutil
    makers = [{"name": "deepseek", "type": "api", "status": "available" if os.environ.get("DEEPSEEK_API_KEY") else "no_key"}]
    for cmd, label in [("claude", "Claude Code"), ("qoder", "Qoder"), ("copilot-cli", "Copilot")]:
        makers.append({"name": cmd, "type": "cli", "label": label,
                       "status": "available" if shutil.which(cmd) else "not_installed"})
    return jsonify({"ok": True, "makers": makers})
