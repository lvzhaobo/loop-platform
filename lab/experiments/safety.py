#!/usr/bin/env python3
"""试验 4-6：安全三件套的最小可复现验证（直接用 demo 的真实实现）"""
import subprocess, sys
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent / "demo"
PY = str(DEMO / "A-python")
sys.path.insert(0, PY)
import config, session, approve           # noqa: E402
from tools import Tools                    # noqa: E402


def hdr(n, t):
    print(f"\n{'═'*62}\n试验 {n}：{t}\n{'═'*62}")


cfg = config.load(); cfg["AUTO_YES"] = True
t = Tools(cfg, session.Session("/tmp/exp.jsonl"), approve.ask)

hdr(4, "门禁判据 —— 退出码才是判据，不是模型的话")
p = subprocess.run([sys.executable, str(DEMO / "shared" / "check.py")],
                   capture_output=True, text=True)
red = [l for l in p.stdout.splitlines() if l.strip().startswith(("1", "2", "3", "4", "5", "6", "7")) and "❌" in l]
print(f"  fixture 初始状态 → 退出码 {p.returncode}（1 = 红）")
for l in red[:3]:
    print("    " + l.strip()[:70])
print("  判据：returncode == 0   ← 这就是全部，没有别的解释空间")

hdr(5, "权限约束 —— 白名单 + 路径监狱（同一件事的两个入口）")
cases = [
    (["rm", "-rf", "src"],              False, "命令名不在白名单"),
    (["cat", "../../check.py"],         False, "参数路径越界（read_file 堵了，cat 也要堵）"),
    (["cat", "/etc/passwd"],            False, "绝对路径越界"),
    (["cat", "index.html"],             True,  "工作区内读文件"),
    (["python", "check.py"],            True,  "白名单内的命令"),
]
for argv, should, why in cases:
    r = t.call("run_command", {"argv": argv})
    got = not r.get("denied")
    mark = "✅" if got == should else "❌"
    print(f"  {mark} {' '.join(argv):<28} → {'放行' if got else '拒绝'}   （{why}）")
print("  判据：同一个能力有几个入口？cat 能读文件，read_file 也能读")

hdr(6, "终止判定 —— 三重预算，撞一个就停")
import loop as loopmod
import inspect
src = inspect.getsource(loopmod)
for key, label in [("MAX_STEPS", "步数预算"), ("MAX_RETRIES", "重试预算"), ("CMD_TIMEOUT", "单命令超时")]:
    hit = [l.strip() for l in src.splitlines() if key in l][:1]
    print(f"  {label:<12} {hit[0] if hit else '（在 config 里）'}")
print(f"  config: MAX_STEPS={cfg.get('MAX_STEPS')}  MAX_RETRIES={cfg.get('MAX_RETRIES')}  CMD_TIMEOUT={cfg.get('CMD_TIMEOUT')}")
print("  判据：不是'跑到绿'，是'跑到绿 或 撞预算'——两个出口都必须有")
