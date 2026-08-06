#!/usr/bin/env python3
"""Loop 主入口：从需求池取任务 → 调引擎 → 回写状态。

替代 run.sh / run_backlog.sh。
用法：
    python pipeline/run.py                 # legacy 兼容入口
    python pipeline/run.py --profile fixture-local  # Profile / Run Plan 入口
"""

import subprocess
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
ROOT = PIPELINE_DIR.parent

if __name__ == "__main__":
    proc = subprocess.run(
        [sys.executable, str(PIPELINE_DIR / "orchestrator.py"), *sys.argv[1:]],
        cwd=str(ROOT),
    )
    sys.exit(proc.returncode)
