"""Checker API 路由。F5: 使用 PlatformPaths + run_id 转发。"""

import os, sys
from flask import Blueprint, request, jsonify

checker_bp = Blueprint("checker", __name__)
LOOP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(LOOP_DIR, "engine"))


def _default_target_dir(name: str) -> str:
    """默认目标目录：process checker 用项目根，其余需显式指定。"""
    if name == "process":
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return ""


@checker_bp.route("/<name>", methods=["POST"])
def checker_run(name):
    """运行指定 Checker。F5: 接受 run_id 显式绑定。"""
    data = request.get_json(force=True) or {}
    out_dir = data.get("dir", _default_target_dir(name))
    run_id = data.get("run_id", "")

    if not out_dir or not os.path.isdir(out_dir):
        return jsonify({"ok": False, "error": "dir 参数无效"}), 400

    try:
        from checkers import load_checker
        checker = load_checker(name)
        result = checker.check(out_dir, run_id=run_id)
        return jsonify({"ok": result.all_pass, "name": name,
                        "pass": result.pass_count, "total": result.total_count,
                        "checks": result.checks,
                        "status_summary": result.summarize()})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@checker_bp.route("/all", methods=["POST"])
def checker_all():
    """运行全部 Checker。F5: 接受 run_id 转发。"""
    data = request.get_json(force=True) or {}
    out_dir = data.get("dir", "")
    run_id = data.get("run_id", "")
    if not out_dir or not os.path.isdir(out_dir):
        return jsonify({"ok": False, "error": "dir 参数无效"}), 400
    try:
        from checkers.all_checker import AllChecker
        result = AllChecker().check(out_dir, run_id=run_id)
        return jsonify({"ok": result.all_pass, "pass": result.pass_count,
                        "total": result.total_count, "checks": result.checks,
                        "status_summary": result.summarize()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
