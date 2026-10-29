#!/usr/bin/env python3
"""自动验收：三个 TODO 有没有真的生效。python lab_check.py"""
import importlib.util, subprocess, sys, shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
FIX = DEMO / "shared" / "fixture" / "pomodoro"
SOL = DEMO / "shared" / "solution"

def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

results = []
def case(title, fn):
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"{type(e).__name__}: {e}"
    results.append((title, ok, detail))
    print(("  ✅ " if ok else "  ❌ ") + title)
    if not ok and detail:
        print("       └─ " + detail)

# ---------- TODO 1 ----------
tools = load("tools")

def t1_allow():
    if not tools.allowed(["npm", "test"]):
        return False, "npm test 还没进白名单"
    if not tools.allowed(["python", "check.py"]):
        return False, "python check.py 还没进白名单"
    return True, ""

def t1_deny():
    r = tools.run(["rm", "-rf", "/"])
    if not r.get("denied"):
        return False, "rm -rf / 居然没被拒！"
    return True, ""

def t1_injection():
    r = tools.run(["npm", "test; rm -rf /"])
    if not r.get("denied"):
        return False, "带 ; 的注入没有被拒"
    return True, ""

# ---------- TODO 2 ----------
def _run_gate():
    return subprocess.run([sys.executable, str(HERE / "check.py")],
                          capture_output=True, text=True).returncode

def t2_green_on_solution():
    backup = {p.name: p.read_text(encoding="utf-8") for p in FIX.glob("*.*")}
    try:
        for f in ("index.html", "app.js"):
            shutil.copy(SOL / f, FIX / f)
        code = _run_gate()
        if code != 0:
            return False, "正确实现（solution）被你的门禁判红了 → 断言太严或写错"
        return True, ""
    finally:
        for name, text in backup.items():
            (FIX / name).write_text(text, encoding="utf-8")

def t2_red_on_fixture():
    code = _run_gate()
    if code == 0:
        return False, "还没改的 fixture 居然判绿了 → 断言太松，门禁抓不住问题"
    return True, ""

# ---------- TODO 3 ----------
policy = load("policy")
def t3_escalate():
    b = policy.Budget(max_retries=2)
    seq = ["same"] * 5
    verdicts = [b.observe(s) for s in seq]
    if "escalate" not in verdicts:
        return False, "连续 5 次同一动作，没有升级"
    first = verdicts.index("escalate") + 1
    if first > 3:
        return False, f"第 {first} 次才升级，太晚了（应该第 3 次就升）"
    return True, ""

def t3_reset():
    b = policy.Budget(max_retries=2)
    b.observe("a"); b.observe("b"); b.observe("c")
    if b.observe("d") == "escalate":
        return False, "不同动作被当成重复了（忘了重置计数）"
    return True, ""

# ---------- 跑 ----------
print("\n" + "═" * 58)
print("  动手实验 · 自动验收")
print("═" * 58)
print("\n[TODO 1] 白名单（权限约束）")
case("允许 npm test / python check.py", t1_allow)
case("拒绝 rm -rf /", t1_deny)
case("拒绝带 ; 的注入", t1_injection)
print("\n[TODO 2] 门禁断言（执行校验）")
case("对正确实现判绿", t2_green_on_solution)
case("对未改的 fixture 判红", t2_red_on_fixture)
print("\n[TODO 3] 重试预算（终止判定）")
case("重复超限能升级", t3_escalate)
case("不同动作不误判", t3_reset)

ok = sum(1 for _, o, _ in results if o)
print("\n" + "═" * 58)
print(f"  {ok}/{len(results)} 项通过")
if ok == len(results):
    print("  🎉 三个闸门都接通了 —— 这套东西可以带回公司了")
else:
    print("  继续改，直到全绿。全绿之后再回答：这三条分别对应哪种能力？")
print("═" * 58 + "\n")
sys.exit(0 if ok == len(results) else 1)
