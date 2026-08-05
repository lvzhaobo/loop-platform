"""CLI 型 Maker 适配器（Claude Code / Qoder CLI / Copilot）。

通过子进程调用外部 CLI agent，交出 workdir + prompt，agent 自己读写文件。

调用前初始化项目级 Agent 配置（.qoder/ 或 .claude/），让 CLI 的 session
历史记录留在生成目录中——这样 Better Harness 可以拿到完整的 Agent 行为证据。
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from .base import Maker, MakerResult
from . import register


# ── Agent 配置初始化 ──

_QODER_SETTINGS = json.dumps({
    "permissions": {
        "allow": ["Bash(git:*)", "Read", "Write", "SearchReplace", "Glob", "Grep"]
    }
}, indent=2)

_CLAUDE_SETTINGS = json.dumps({
    "permissions": {
        "allow": ["Bash(git:*)", "Read", "Write", "Edit", "Glob", "Grep"]
    }
}, indent=2)


def _init_agent_config(workdir: str, command: str):
    """在 workdir 中初始化 Agent 项目配置，确保 CLI 的 session 记录留在这里。

    - qodercli → .qoder/settings.json
    - claude   → .claude/settings.json + .claude/CLAUDE.md 引用 AGENTS.md
    - 其他     → 不做初始化（无 session 能力）
    """
    wp = Path(workdir)
    if command in ("qoder", "qodercli"):
        qd = wp / ".qoder"
        qd.mkdir(exist_ok=True)
        (qd / "settings.json").write_text(_QODER_SETTINGS)
    elif command in ("claude", "claude-code"):
        cd = wp / ".claude"
        cd.mkdir(exist_ok=True)
        (cd / "settings.json").write_text(_CLAUDE_SETTINGS)
        # CLAUDE.md 让 claude 自动读取项目上下文
        (wp / "CLAUDE.md").write_text(
            "# CLAUDE.md\n\n此项目由 Loop 平台自动生成。"
            "请读取 AGENTS.md 获取完整规格，按规格生成所有代码文件。\n"
        )


# ── 命令映射 ──

def _build_cmd(command: str, workdir: str) -> list[str]:
    """根据 command 名称构造子进程调用参数。"""
    cmd_map = {
        "claude": [
            "claude", "-p",
            "按 AGENTS.md 和 CLAUDE.md 的规格生成全部代码文件到当前目录。"
            "先用 Glob 确认当前目录的文件结构，再用 Write 逐个写入。",
            "--permission-mode", "bypassPermissions",
            "--output-format", "json",
        ],
        "claude-code": [
            "claude", "-p",
            "按 AGENTS.md 和 CLAUDE.md 的规格生成全部代码文件到当前目录。"
            "先用 Glob 确认当前目录的文件结构，再用 Write 逐个写入。",
            "--permission-mode", "bypassPermissions",
            "--output-format", "json",
        ],
        "qoder": [
            "qodercli", "-p",
            "读 AGENTS.md，按规格生成全部代码文件到当前目录。",
            "-w", workdir,
            "--permission-mode", "auto",
            "--output-format", "json",
        ],
        "copilot": ["copilot-cli", "generate", "--workspace", workdir],
        "cursor": ["cursor-agent", "--cwd", workdir],
    }
    return cmd_map.get(command, [
        "claude", "-p", "按 AGENTS.md 生成代码",
        "--permission-mode", "bypassPermissions",
    ])


# ── Maker ──

@register("cli")
class CLIMaker(Maker):
    name = "cli"
    type = "cli"

    def __init__(self, command="claude", **kwargs):
        self.command = command  # "claude" | "claude-code" | "qoder" | "copilot" | "cursor"

    def generate(self, workdir: str, prompt: str,
                 feedback: str | None = None) -> MakerResult:
        workdir_path = Path(workdir)
        workdir_path.mkdir(parents=True, exist_ok=True)

        # 1. 写入 AGENTS.md（prompt = spec + constraints + rules）
        agents_path = workdir_path / "AGENTS.md"
        agents_path.write_text(prompt)

        # 2. 初始化 Agent 项目配置 → CLI session 记录留在生成目录
        _init_agent_config(workdir, self.command)

        # 3. 构造调用命令
        cmd = _build_cmd(self.command, workdir)
        maker_label = "qodercli" if self.command == "qoder" else self.command

        try:
            result = subprocess.run(
                cmd, cwd=workdir, capture_output=True, text=True, timeout=300
            )
            # 扫描生成的文件
            files = {}
            skip_prefixes = (".qoder", ".claude", "__pycache__", "node_modules")
            skip_names = {"AGENTS.md", "CLAUDE.md"}
            for f in workdir_path.rglob("*"):
                if f.is_file() and f.name not in skip_names:
                    if any(part in skip_prefixes for part in f.parts):
                        continue
                    rel = str(f.relative_to(workdir_path))
                    files[rel] = f.read_text()
            if not files:
                return MakerResult(
                    success=False,
                    error=f"CLI 完成后工作目录无文件生成。stdout: {result.stdout[:200]}",
                    output_dir=workdir,
                    model=maker_label,
                )
            return MakerResult(
                success=result.returncode == 0,
                files=files,
                output_dir=workdir,
                model=maker_label,
                raw_output=result.stdout[:2000] + result.stderr[:500],
            )
        except subprocess.TimeoutExpired:
            return MakerResult(
                success=False, error="CLI 执行超时（300s）",
                output_dir=workdir, model=maker_label,
            )
        except FileNotFoundError:
            return MakerResult(
                success=False,
                error=f"未找到命令 '{self.command}'。请安装对应 CLI 工具。",
                output_dir=workdir,
                model=maker_label,
            )
