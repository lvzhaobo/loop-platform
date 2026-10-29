#!/usr/bin/env python3
"""把 fixture 复位成"门禁红"的初始状态。演示前来一次。"""
import shutil, subprocess, sys
from pathlib import Path

DEMO = Path(__file__).resolve().parent
INIT = DEMO / "shared" / "_initial"
FIX = DEMO / "shared" / "fixture"

for src in sorted(INIT.rglob("*")):
    if src.is_file():
        rel = src.relative_to(INIT)
        dst = FIX / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"  复位 {rel}")

for name in ("check.py", "check-cs.py"):
    p = DEMO / "shared" / name
    if not p.exists():
        continue
    r = subprocess.run([sys.executable, str(p)], capture_output=True, text=True)
    last = [l for l in r.stdout.strip().splitlines() if "通过" in l]
    print(f"  {name:<12} → {last[-1].strip() if last else '?'}")

# 清掉上一轮的会话与缓存
for d in (DEMO / "runs", *(DEMO.rglob("__pycache__"))):
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
print("  已清理会话与缓存")
