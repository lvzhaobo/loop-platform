"""Checker API 路由。"""

import os, sys
from flask import Blueprint, request, jsonify

checker_bp = Blueprint("checker", __name__)
LOOP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(LOOP_DIR, "engine"))


@checker_bp.route("/<name>", methods=["POST"])
def checker_run(name):
    """运行指定 Checker。process checker 不需要 dir 参数（读项目根目录）。"""
    data = request.get_json(force=True) or {}
    out_dir = data.get("dir", "")
    # process checker 不需要 dir，用项目根目录即可
    if name == "process":
        if not out_dir:
            out_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if not os.path.isdir(out_dir):
            out_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    else:
        if not out_dir or not os.path.isdir(out_dir):
            return jsonify({"ok": False, "error": "dir 参数无效"}), 400
    try:
        from checkers import load_checker
        checker = load_checker(name)
        result = checker.check(out_dir)
        return jsonify({"ok": result.all_pass, "name": name,
                        "pass": result.pass_count, "total": result.total_count,
                        "checks": result.checks})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@checker_bp.route("/all", methods=["POST"])
def checker_all():
    """运行全部 Checker。"""
    data = request.get_json(force=True) or {}
    out_dir = data.get("dir", "")
    if not out_dir or not os.path.isdir(out_dir):
        return jsonify({"ok": False, "error": "dir 参数无效"}), 400
    try:
        from checkers.all_checker import AllChecker
        result = AllChecker().check(out_dir)
        return jsonify({"ok": result.all_pass, "pass": result.pass_count,
                        "total": result.total_count, "checks": result.checks})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
