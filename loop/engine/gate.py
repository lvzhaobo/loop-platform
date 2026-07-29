#!/usr/bin/env python3
"""Loop 门禁：自洽性 → 派生 Schema → 全用例生成验证闭环。

替代 gate.sh。任一环节失败返回非 0。
用法: python loop/engine/gate.py
"""

import subprocess
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
LOOP_DIR = ENGINE_DIR.parent

# 1. 自洽性
print("========== 门禁 1/3：Spec 自洽性校验 ==========")
proc = subprocess.run(
    [sys.executable, str(ENGINE_DIR / "tools" / "compile_spec.py"), "--check"],
    cwd=str(LOOP_DIR.parent),
)
if proc.returncode != 0:
    print("❌ 自洽性检查失败")
    sys.exit(1)

# 2. Schema 派生
print("========== 门禁 2/3：派生数据 Schema ==========")
proc = subprocess.run(
    [sys.executable, str(ENGINE_DIR / "tools" / "build_schema.py")],
    cwd=str(LOOP_DIR.parent),
)
if proc.returncode != 0:
    print("❌ Schema 派生失败")
    sys.exit(1)

# 3. 全用例生成+验证
print("========== 门禁 3/3：全用例生成 + 验证闭环 ==========")
proc = subprocess.run(
    [sys.executable, str(ENGINE_DIR / "generate.py")],
    cwd=str(LOOP_DIR.parent),
)
if proc.returncode == 0:
    print("🎉 门禁全部通过")
else:
    print("❌ 门禁未通过")
    sys.exit(1)
