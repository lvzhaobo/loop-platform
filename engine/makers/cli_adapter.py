"""CLI 型 Maker 适配器（Claude Code / Qoder / Copilot）。

通过子进程调用外部 CLI agent，交出 workdir + prompt，agent 自己读写文件。
"""

import os
import subprocess
import tempfile
from pathlib import Path

from .base import Maker, MakerResult
from . import register


@register("cli")
class CLIMaker(Maker):
    name = "cli"
    type = "cli"

    def __init__(self, command="claude", **kwargs):
        self.command = command  # "claude" | "qoder" | "copilot" | "claude-code"

    def generate(self, workdir: str, prompt: str,
                 feedback: str | None = None) -> MakerResult:
        # 写入 prompt 到 AGENTS.md
        workdir_path = Path(workdir)
        workdir_path.mkdir(parents=True, exist_ok=True)
        agents_path = workdir_path / "AGENTS.md"
        agents_path.write_text(prompt)

        # 映射命令
        cmd_map = {
            "claude": ["claude", "-p", "按 AGENTS.md 生成代码到当前目录"],
            "claude-code": ["claude", "-p", "按 AGENTS.md 生成代码到当前目录"],
            "qoder": ["qoder", "work", "--dir", workdir],
            "copilot": ["copilot-cli", "generate", "--workspace", workdir],
            "cursor": ["cursor-agent", "--cwd", workdir],
        }
        cmd = cmd_map.get(self.command, ["claude", "-p", "按 AGENTS.md 生成代码"])

        try:
            result = subprocess.run(
                cmd, cwd=workdir, capture_output=True, text=True, timeout=300
            )
            # 扫描生成的文件
            files = {}
            for f in workdir_path.rglob("*"):
                if f.is_file() and f.name != "AGENTS.md" and "__pycache__" not in f.parts:
                    rel = str(f.relative_to(workdir_path))
                    files[rel] = f.read_text()
            if not files:
                return MakerResult(
                    success=False,
                    error=f"CLI 完成后工作目录无文件生成。stdout: {result.stdout[:200]}",
                    output_dir=workdir,
                )
            return MakerResult(
                success=result.returncode == 0,
                files=files,
                output_dir=workdir,
                raw_output=result.stdout[:2000] + result.stderr[:500],
            )
        except subprocess.TimeoutExpired:
            return MakerResult(success=False, error="CLI 执行超时（300s）", output_dir=workdir)
        except FileNotFoundError:
            return MakerResult(
                success=False,
                error=f"未找到命令 '{self.command}'。请安装对应 CLI 工具。",
                output_dir=workdir,
            )
