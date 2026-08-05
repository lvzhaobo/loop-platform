#!/usr/bin/env python3
"""一键环境准备：创建 venv 并安装验证所需依赖(Flask)。

替代 setup.sh。用法: python loop/setup.py
"""

import os
import subprocess
import sys
import venv
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parent
ROOT = LOOP_DIR.parent
VENV_DIR = ROOT / ".venv"


def _venv_python(venv_dir: Path) -> Path:
    """返回 venv 内的 python 可执行文件路径(跨平台)。"""
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def main() -> int:
    if not VENV_DIR.exists():
        print("创建虚拟环境 .venv ...")
        venv.create(str(VENV_DIR), with_pip=True)

    py = str(_venv_python(VENV_DIR))
    subprocess.run([py, "-m", "pip", "install", "-q", "--upgrade", "pip"],
                   check=False)
    proc = subprocess.run([py, "-m", "pip", "install", "-q", "Flask==3.0.*"])
    if proc.returncode != 0:
        print("❌ Flask 安装失败")
        return proc.returncode

    print("✅ 环境就绪(Flask 已安装)。")
    print("下一步:")
    print("  离线冒烟:           HARNESS_MODE=sample python loop/engine/gate.py")
    print("  真实生成:           source .env && python loop/engine/gate.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
