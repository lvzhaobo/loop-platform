#!/usr/bin/env python3
"""Loop 主入口：从需求池取任务 → 调引擎 → 回写状态。

替代 run.sh / run_backlog.sh。
用法: python pipeline/run.py
"""

import subprocess
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
LOOP_DIR = PIPELINE_DIR.parent
ROOT = LOOP_DIR.parent

if __name__ == "__main__":
    proc = subprocess.run(
        [sys.executable, str(PIPELINE_DIR / "orchestrator.py")],
        cwd=str(ROOT),
    )
    sys.exit(proc.returncode)
