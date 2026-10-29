#!/usr/bin/env python3
"""
门禁脚本（三装置共用）：python check.py
  - 全部通过 → 退出码 0
  - 任一失败 → 退出码 1

为什么它重要：它是三个装置里唯一不变量。
IDE、自研 Python、DSH 沙箱跑的都是这一份判断。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "fixture" / "pomodoro"
HTML = ROOT / "index.html"
JS = ROOT / "app.js"

checks = []
def check(name, hint=""):
    def deco(fn):
        checks.append((name, fn, hint))
        return fn
    return deco

def read(p):
    if not p.exists():
        raise FileNotFoundError(f"找不到 {p}")
    return p.read_text(encoding="utf-8")

# ---------- 1. 两个输入控件 ----------
@check("存在 work-minutes / break-minutes 两个数字输入框",
       "在 index.html 里加 <input id=\"work-minutes\" type=\"number\"> 和 break-minutes")
def _():
    h = read(HTML)
    for id_ in ("work-minutes", "break-minutes"):
        m = re.search(r'<input[^>]*id="%s"[^>]*>' % id_, h)
        if not m:
            return False, f'没找到 id="{id_}" 的 input'
        if 'type="number"' not in m.group(0):
            return False, f'{id_} 不是 type="number"'
    return True, ""

# ---------- 2. app.js 真的去读了控件 ----------
@check("app.js 从这两个控件读取数值",
       "用 document.getElementById('work-minutes').value 读，再用 Number() 转")
def _():
    js = read(JS)
    for id_ in ("work-minutes", "break-minutes"):
        if not re.search(r"getElementById\(\s*['\"]%s['\"]\s*\)|querySelector\(\s*['\"]#%s['\"]\s*\)" % (id_, id_), js):
            return False, f"app.js 里没有读取 {id_}"
    if "Number(" not in js and "parseInt(" not in js:
        return False, "读了 value 但没转成数字（Number / parseInt）"
    return True, ""

# ---------- 3. 分钟 → 秒 ----------
@check("按「分钟 × 60」换算成秒",
       "const w = Number(el.value) * 60 —— 别忘了乘 60")
def _():
    js = read(JS)
    if not re.search(r"\*\s*60", js):
        return False, "没找到 * 60 的换算"
    return True, ""

# ---------- 4. 非法值回退 ----------
@check("非法值（≤0 / >180 / NaN）回退到 25 / 5",
       "写一个 clampMinutes(v, fallback) 函数，if (isNaN(v) || v <= 0 || v > 180) return fallback")
def _():
    js = read(JS)
    has_upper = re.search(r">\s*180", js) or re.search(r"Math\.min\(\s*180", js)
    has_lower = re.search(r"<=\s*0", js) or re.search(r"<\s*1\b", js)
    has_nan = re.search(r"isNaN|Number\.isFinite|parseInt\([^)]*\)\s*\|\|", js)
    if not (has_upper and has_lower):
        return False, "没看到上下界判断（<=0 与 >180）"
    if not has_nan:
        return False, "没看到 NaN / 非数字的判断"
    return True, ""

# ---------- 5. 不回归：核心逻辑还在 ----------
@check("原有功能没被改坏（默认 25 / 5、自动切换、定时器）",
       "不要重写，只做加法")
def _():
    js = read(JS)
    problems = []
    if not (re.search(r"DEFAULT_WORK\s*=\s*25\b", js) or re.search(r"25\s*\*\s*60", js)):
        problems.append("默认工作时长不是 25 分钟")
    if not (re.search(r"DEFAULT_BREAK\s*=\s*5\b", js) or re.search(r"BREAK_SECONDS\s*=\s*5\s*\*\s*60", js)):
        problems.append("默认休息时长不是 5 分钟")
    if "setInterval" not in js:
        problems.append("定时器驱动没了")
    if "switchMode" not in js:
        problems.append("自动切换 work↔break 的逻辑没了")
    if problems:
        return False, "；".join(problems)
    return True, ""

# ---------- 6. 不引第三方库 ----------
@check("零依赖：没有引入外部脚本 / 框架",
       "这个工程要双击 index.html 就能跑")
def _():
    h = read(HTML)
    srcs = re.findall(r"<script[^>]*src=\"([^\"]+)\"", h)
    remote = [s for s in srcs if s.startswith("http://") or s.startswith("https://") or s.startswith("//")]
    if remote:
        return False, "引了外部脚本：" + ", ".join(remote)
    return True, ""

# ---------- 7. 门禁没被篡改（自我保护） ----------
@check("门禁自身未被修改（裁判不是选手）",
       "改 check.py 让检查通过 = 作弊")
def _():
    import hashlib
    expect = "让通过=作弊"   # 占位：真实项目里应比对校验和
    body = Path(__file__).read_text(encoding="utf-8")
    marker = "ALLOW_" + "EDIT_CHECK"   # 拆开写，避免匹配到自己这行
    if marker in body:
        return False, "检测到门禁被绕过标记"
    return True, hashlib.md5(body.encode()).hexdigest()[:8]

# ---------- 主程序 ----------
def main():
    print(f"\n门禁：{ROOT}\n" + "─" * 58)
    failed = 0
    for name, fn, hint in checks:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        print(("  ✅ " if ok else "  ❌ ") + name)
        if not ok:
            failed += 1
            if detail:
                print("       └─ " + detail)
            if hint:
                print("       └─ 提示：" + hint)
    total = len(checks)
    print("─" * 58)
    if failed:
        print(f"  {total - failed}/{total} 通过 —— 门禁红，不许合并\n")
        return 1
    print(f"  {total}/{total} 通过 —— 门禁绿，可以合并\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
