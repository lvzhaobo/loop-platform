#!/usr/bin/env python3
"""Loop 轮询式自动触发器（替代 poll.sh）。

守护进程模式: python loop/pipeline/trigger/poll.py
单次模式:     python loop/pipeline/trigger/poll.py --once
"""

import os
import subprocess
import sys
import time
from pathlib import Path

TRIGGER_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = TRIGGER_DIR.parent
LOOP_DIR = PIPELINE_DIR.parent
ROOT = LOOP_DIR.parent
LOCK_FILE = PIPELINE_DIR / ".trigger.lock"

INTERVAL = int(os.environ.get("HARNESS_TRIGGER_INTERVAL", "300"))


def acquire_lock() -> bool:
    """创建锁文件，已存在则返回 False。"""
    try:
        LOCK_FILE.mkdir(exist_ok=False)
        (LOCK_FILE / "pid").write_text(str(os.getpid()))
        return True
    except FileExistsError:
        return False


def release_lock():
    """删除锁文件。"""
    try:
        (LOCK_FILE / "pid").unlink(missing_ok=True)
        LOCK_FILE.rmdir()
    except Exception:
        pass


def run_once():
    """运行一批交付。"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    if not acquire_lock():
        print(f"[poll {ts}] 上一批仍在运行，本轮跳过")
        return
    try:
        print(f"[poll {ts}] ▶ 触发一批")
        proc = subprocess.run(
            [sys.executable, str(PIPELINE_DIR / "run.py")],
            cwd=str(ROOT),
        )
        print(f"[poll {time.strftime('%H:%M:%S')}] ✔ 本批结束 (exit={proc.returncode})")
    finally:
        release_lock()


if __name__ == "__main__":
    if "--once" in sys.argv:
        run_once()
    else:
        print(f"[poll] 守护进程模式，间隔 {INTERVAL}s。Ctrl-C 停止。")
        try:
            while True:
                run_once()
                time.sleep(INTERVAL)
        except KeyboardInterrupt:
            print("\n[poll] 收到退出信号，停止。")
