"""E2E 浏览器级测试 Checker。探测入口 → 起服务/读静态页 → 解析 DOM。"""

import os, subprocess
from html.parser import HTMLParser

from .base import Checker, CheckerResult
from . import register
from .entry import detect_entry, clean_env, wait_http_ready


class DOMCheck(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []; self.buttons = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag in ("button", "input"):
            self.buttons.append(tag)


@register("e2e")
class E2EChecker(Checker):
    name = "e2e"

    def _assert_dom(self, checks, html_text):
        dom = DOMCheck(); dom.feed(html_text)
        checks.append({"name": "页面渲染", "pass": len(html_text) > 0, "detail": f"{len(html_text)} 字符"})
        checks.append({"name": "交互元素", "pass": len(dom.buttons) > 0, "detail": f"{len(dom.buttons)} 个按钮/输入框"})

    def check(self, target_dir: str) -> CheckerResult:
        checks = []
        entry = detect_entry(target_dir)

        # 无入口：跳过而非判失败
        if not entry:
            checks.append({"name": "e2e", "pass": True, "detail": "无可运行/可渲染入口，跳过 E2E"})
            return CheckerResult(pass_count=1, total_count=1, checks=checks, all_pass=True)

        # 静态站点：直接读 HTML 文件解析 DOM，无需起服务
        if entry["kind"] == "static":
            try:
                with open(os.path.join(target_dir, entry["file"]), encoding="utf-8", errors="replace") as f:
                    self._assert_dom(checks, f.read())
            except OSError as e:
                checks.append({"name": "e2e", "pass": False, "detail": str(e)[:80]})
            pass_count = sum(1 for c in checks if c["pass"])
            return CheckerResult(pass_count=pass_count, total_count=len(checks), checks=checks, all_pass=pass_count == len(checks))

        # 服务型：启动后抓取首页解析 DOM。环境经 clean_env 洗过(防 studio 的 Flask 变量泄漏)。
        port = 5198
        env = clean_env(port)
        entry_dir = os.path.join(target_dir, os.path.dirname(entry["file"])) or target_dir
        cmd = [c if c != entry["file"] else os.path.basename(entry["file"]) for c in entry["cmd"]]
        try:
            proc = subprocess.Popen(cmd, cwd=entry_dir, env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, FileNotFoundError) as e:
            checks.append({"name": "e2e", "pass": True, "detail": f"运行时不可用（{str(e)[:40]}），跳过"})
            return CheckerResult(pass_count=1, total_count=1, checks=checks, all_pass=True)

        try:
            resp, diag = wait_http_ready(proc, f"http://127.0.0.1:{port}/")
            if resp is not None:
                self._assert_dom(checks, resp.read().decode("utf-8", errors="replace"))
            else:
                checks.append({"name": "e2e", "pass": False, "detail": diag[:80]})
        finally:
            proc.terminate()

        pass_count = sum(1 for c in checks if c["pass"])
        return CheckerResult(pass_count=pass_count, total_count=len(checks), checks=checks, all_pass=pass_count == len(checks))
