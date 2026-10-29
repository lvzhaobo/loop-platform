#!/usr/bin/env python3
"""一个会随修复变化的门禁：4 条规则，扫 target.txt。退出码 0 才算绿。"""
import sys
from pathlib import Path

T = Path(__file__).parent / "target.txt"
RULES = [
    ("ERR001", "禁止裸 raise Exception", lambda s: "raise Exception" not in s),
    ("ERR002", "禁止 print 调试",        lambda s: "print(" not in s),
    ("SEC001", "禁止硬编码密钥",         lambda s: "sk-" not in s),
    ("CFG001", "禁止 os.getenv 直接用",  lambda s: "os.getenv" not in s),
]

src = T.read_text(encoding="utf-8")
red = 0
for rid, desc, ok in RULES:
    if ok(src):
        print(f"GREEN {rid}  {desc}")
    else:
        red += 1
        print(f"RED   {rid}  {desc}")
print(f"\n通过 {len(RULES)-red}/{len(RULES)}")
sys.exit(0 if red == 0 else 1)
