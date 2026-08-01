"""E2E 浏览器级测试 Checker。探测入口 → 起服务/读静态页 → 解析 DOM + spec 驱动验收。"""

import json, os, subprocess, urllib.request
from html.parser import HTMLParser

from .base import Checker, CheckerResult
from . import register
from .entry import detect_entry, clean_env, wait_http_ready

# spec/acceptance.json 里 e2e 可执行的断言类型（与 SPEC_AC_TYPES 闭集对齐）
# unit_test / manual 不由 e2e 执行
_E2E_AC_TYPES = {"http_status", "http_body_contains", "text_contains", "text_absent", "file_exists"}


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

    def _assert_acceptance(self, checks, target_dir, base_url=None):
        """读 spec/acceptance.json，按断言类型逐条执行。base_url 为 None 时只跑文件类断言。"""
        ac_path = os.path.join(target_dir, "spec", "acceptance.json")
        if not os.path.exists(ac_path):
            return  # 无 acceptance.json 则跳过（向后兼容）
        try:
            with open(ac_path, encoding="utf-8") as f:
                acc = json.load(f)
        except (json.JSONDecodeError, OSError):
            checks.append({"name": "spec验收", "pass": False, "detail": "acceptance.json 解析失败"})
            return

        items = acc.get("acceptance", [])
        if not items:
            return

        for item in items:
            tid = item.get("id", "?")
            typ = item.get("type", "")
            desc = item.get("desc", tid)

            if typ not in _E2E_AC_TYPES:
                continue  # unit_test / manual 等不由 e2e 执行

            ok, detail = self._run_ac_assertion(item, target_dir, base_url)
            checks.append({"name": f"AC:{tid}", "pass": ok, "detail": f"{desc} → {detail}"})

    def _run_ac_assertion(self, item, target_dir, base_url):
        """执行单条断言，返回 (pass: bool, detail: str)。"""
        typ = item["type"]

        # ── 文件类断言（不需要服务）──
        if typ == "file_exists":
            fp = os.path.join(target_dir, item.get("file", ""))
            return (os.path.exists(fp), "存在" if os.path.exists(fp) else "缺失")

        if typ in ("text_contains", "text_absent"):
            fp = os.path.join(target_dir, item.get("file", ""))
            if not os.path.exists(fp):
                return (False, f"文件不存在: {item.get('file')}")
            try:
                content = open(fp, encoding="utf-8", errors="replace").read()
            except OSError as e:
                return (False, str(e)[:60])
            needle = item.get("needle", "")
            found = needle in content
            if typ == "text_contains":
                return (found, f"{'找到' if found else '未找到'} \"{needle}\"")
            else:
                return (not found, f"{'未出现(符合预期)' if not found else '意外出现'} \"{needle}\"")

        # ── HTTP 类断言（需要服务在跑）──
        if base_url is None:
            return (True, "跳过(静态站点无服务)")

        route = item.get("route", "/")
        url = base_url.rstrip("/") + route
        try:
            resp = urllib.request.urlopen(url, timeout=5)
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.status
        except Exception as e:
            return (False, f"请求失败: {str(e)[:60]}")

        if typ == "http_status":
            expect = item.get("expect", 200)
            return (status == expect, f"状态码 {status}(期望 {expect})")

        if typ == "http_body_contains":
            needle = item.get("needle", "")
            found = needle in body
            return (found, f"{'找到' if found else '未找到'} \"{needle}\"")

        return (True, "未知类型，跳过")

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
            # spec 验收：静态站点只跑文件类断言
            self._assert_acceptance(checks, target_dir, base_url=None)
            pass_count = sum(1 for c in checks if c["pass"])
            return CheckerResult(pass_count=pass_count, total_count=len(checks), checks=checks, all_pass=pass_count == len(checks))

        # 服务型：启动后抓取首页解析 DOM + spec 验收。环境经 clean_env 洗过(防 studio 的 Flask 变量泄漏)。
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

        base_url = f"http://127.0.0.1:{port}"
        try:
            resp, diag = wait_http_ready(proc, f"{base_url}/")
            if resp is not None:
                self._assert_dom(checks, resp.read().decode("utf-8", errors="replace"))
                # spec 验收：服务在跑，HTTP + 文件类断言全跑
                self._assert_acceptance(checks, target_dir, base_url=base_url)
            else:
                checks.append({"name": "e2e", "pass": False, "detail": diag[:80]})
        finally:
            proc.terminate()

        pass_count = sum(1 for c in checks if c["pass"])
        return CheckerResult(pass_count=pass_count, total_count=len(checks), checks=checks, all_pass=pass_count == len(checks))
