#!/usr/bin/env python3
"""TODO 2 —— 门禁断言（执行校验）

规则：每加一条 assert_*，就是加一条「什么算通过」。
      python check.py 退出码 0 = 绿；非 0 = 红。

现在有 3 条待你补。断言写得越准，门禁越可信；
写死实现细节（比如要求某个变量名）会把正确实现判红 —— 那也是失败。
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "shared" / "fixture" / "pomodoro"
HTML = ROOT / "index.html"
JS = ROOT / "app.js"

def html():
    return HTML.read_text(encoding="utf-8")

def js():
    return JS.read_text(encoding="utf-8")

# ── 已经写好的两条（照抄格式即可） ──────────────────────────
def check_inputs():
    """页面里有 work-minutes / break-minutes 两个数字输入框"""
    h = html()
    for id_ in ("work-minutes", "break-minutes"):
        m = re.search(r'<input[^>]*id="%s"[^>]*>' % id_, h)
        if not m or 'type="number"' not in m.group(0):
            return False, f'没找到 id="{id_}" 的 number 输入框'
    return True, ""

def check_regression():
    """原有功能没被改坏"""
    j = js()
    if "setInterval" not in j:
        return False, "定时器没了"
    if "switchMode" not in j:
        return False, "自动切换 work↔break 没了"
    return True, ""

# ── 你要补的三条 ──────────────────────────────────────────
def check_reads_input():
    # TODO 2-1：app.js 真的去读了这两个控件
    # 提示：能通过 getElementById('work-minutes') 或 querySelector('#work-minutes') 读都算
    return False, "TODO：还没写"

def check_minutes_to_seconds():
    # TODO 2-2：读到分钟数后，乘以 60 换成秒
    return False, "TODO：还没写"

def check_fallback():
    # TODO 2-3：非法值（NaN / <= 0 / > 180）回退到默认值
    # 提示：要能同时识别 25、5 这种字面量，也要能识别 MAX_MINUTES = 180 这种常量
    return False, "TODO：还没写"

# ── 跑 ──────────────────────────────────────────────────
CHECKS = [
    ("两个数字输入框", check_inputs),
    ("原有功能没退化", check_regression),
    ("app.js 读了输入框", check_reads_input),
    ("分钟 × 60 换算", check_minutes_to_seconds),
    ("非法值回退", check_fallback),
]

def main():
    print(f"\n门禁：{ROOT}\n" + "─" * 56)
    bad = 0
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        print(("  ✅ " if ok else "  ❌ ") + name)
        if not ok:
            bad += 1
            if detail:
                print("       └─ " + detail)
    print("─" * 56)
    print(f"  {len(CHECKS) - bad}/{len(CHECKS)} 通过 —— " + ("门禁绿\n" if not bad else "门禁红\n"))
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
