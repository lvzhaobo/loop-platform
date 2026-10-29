#!/usr/bin/env python3
"""模拟"修一轮"：每次只修一条，按 FIX_MODE 决定怎么修。

FIX_MODE=good  → 逐条修好（试验 1：应该收敛）
FIX_MODE=crash → 修好一条同时弄坏另一条（试验 2：应该触发回归停止）
FIX_MODE=noop  → 假装在修，实际不改（试验 3：应该触发不收敛停止）
"""
import os
from pathlib import Path

T = Path(__file__).parent / "target.txt"
mode = os.environ.get("FIX_MODE", "good")
src = T.read_text(encoding="utf-8")

# 按顺序修好的一条
patches = [
    ("raise Exception", "raise RuntimeError"),
    ("print(", "LOG.info("),
    ("sk-demo-123456", "${API_KEY}"),          # 修好 SEC001，但引入 os.getenv 依赖
    ("os.getenv", "settings.get"),
]

if mode == "noop":
    pass
elif mode == "crash":
    # 修好第一条，同时故意弄坏第二条：重新塞一个 print(
    src = src.replace("raise Exception", "raise RuntimeError", 1)
    if "print(" not in src:
        src += "\nprint('debug')\n"
elif mode == "good":
    for a, b in patches:
        if a in src:
            src = src.replace(a, b, 1)
            break
T.write_text(src, encoding="utf-8")
