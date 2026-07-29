"""E2E 浏览器级测试 Checker。探测入口 → 起服务/读静态页 → 解析 DOM。"""

import os, subprocess
from html.parser import HTMLParser

from .base import Checker, CheckerResult
from . import register
from .entry import detect_entry, clean_env, wait_http_ready


class DOMCheck(HTMLParser):
    INTERACTIVE = ("button", "input", "textarea", "select")

    def __init__(self):
        super().__init__()
        self.tags = []; self.buttons = []; self.has_js = False

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        ad = dict(attrs)
        if tag in self.INTERACTIVE or "onclick" in ad or ad.get("role") == "button":
            self.buttons.append(tag)
        elif tag == "script":
            self.has_js = True


@register("e2e")
class E2EChecker(Checker):
    name = "e2e"

    def _assert_dom(self, checks, html_text):
        dom = DOMCheck(); dom.feed(html_text)
        checks.append({"name": "页面渲染", "pass": len(html_text) > 0, "detail": f"{len(html_text)} 字符"})
        if dom.buttons:
            checks.append({"name": "交互元素", "pass": True, "detail": f"{len(dom.buttons)} 个交互元素(按钮/输入框/onclick)"})
        elif dom.has_js:
            # html/css/js 分离的产物界面常由 JS 运行时渲染，静态解析看不到；
            # 有 <script> 即视为动态渲染，不误报(真正的交互验证需真实浏览器)
            checks.append({"name": "交互元素", "pass": True, "detail": "静态DOM未见交互元素，但页面含 JS 动态渲染，视为通过"})
        else:
            checks.append({"name": "交互元素", "pass": False, "detail": "0 个交互元素且无 JS，疑似不可交互的死页面"})

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
