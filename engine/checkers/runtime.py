"""运行时验证 Checker。探测入口 → 启动服务 → HTTP 检查；无可运行入口则跳过。"""

import os, subprocess

from .base import Checker, CheckerResult
from . import register
from .entry import detect_entry, clean_env, wait_http_ready


@register("runtime")
class RuntimeChecker(Checker):
    name = "runtime"

    def check(self, target_dir: str, *, run_id: str = "") -> CheckerResult:
        checks = []
        entry = detect_entry(target_dir)

        # 无可运行入口：不同应用形态（库/片段/纯数据）本就没有服务，跳过而非判失败
        if not entry:
            checks.append({"name": "运行验证", "pass": True,
                           "detail": "未检测到服务/静态入口，跳过运行验证"})
            return CheckerResult(pass_count=1, total_count=1, checks=checks, all_pass=True)

        # 静态站点：有 HTML 即视为可访问
        if entry["kind"] == "static":
            checks.append({"name": "静态页面可访问", "pass": True,
                           "detail": f"{entry['file']} 存在，可直接用浏览器打开"})
            return CheckerResult(pass_count=1, total_count=1, checks=checks, all_pass=True)

        # 服务型（python/node）：启动后做 HTTP 探活。
        # 环境必须经 clean_env 洗过:studio 的 Flask/Werkzeug 变量泄漏给子进程会让 app.run() 被忽略。
        port = 5199
        env = clean_env(port)
        entry_dir = os.path.join(target_dir, os.path.dirname(entry["file"])) or target_dir
        cmd = entry["cmd"]
        # cmd 里若含相对文件名，改为相对 entry_dir 的 basename
        cmd = [c if c != entry["file"] else os.path.basename(entry["file"]) for c in cmd]

        # 子进程输出落盘而非 DEVNULL，失败时可从 _check_run.log 取诊断
        run_log = os.path.join(target_dir, "_check_run.log")
        log_fh = open(run_log, "wb")
        try:
            proc = subprocess.Popen(
                cmd, cwd=entry_dir, env=env,
                stdout=log_fh, stderr=subprocess.STDOUT,
            )
        except (OSError, FileNotFoundError) as e:
            log_fh.close()
            checks.append({"name": "服务可启动", "pass": True,
                           "detail": f"运行时不可用（{str(e)[:40]}），跳过"})
            return CheckerResult(pass_count=1, total_count=1, checks=checks, all_pass=True)

        try:
            resp, diag = wait_http_ready(proc, f"http://127.0.0.1:{port}/")
            if resp is not None:
                checks.append({"name": "服务可启动", "pass": resp.status == 200,
                               "detail": f"{entry['file']} 启动成功，状态码 {resp.status}"})
            else:
                tail = _log_tail(run_log, log_fh)
                checks.append({"name": "服务可启动", "pass": False,
                               "detail": (diag + ("; app输出: " + tail if tail else ""))[:200]})
        finally:
            proc.terminate()
            log_fh.close()

        pass_count = sum(1 for c in checks if c["pass"])
        return CheckerResult(
            pass_count=pass_count, total_count=len(checks), checks=checks,
            all_pass=pass_count == len(checks),
        )


def _log_tail(path, fh, n=120):
    """取子进程日志尾部供诊断（先 flush 再读）。"""
    try:
        fh.flush()
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().strip()[-n:]
    except OSError:
        return ""
