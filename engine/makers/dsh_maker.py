"""DSH Maker —— 把 DSH（Cordis agent harness）当成一个可替换的代码生成器。

和 deepseek_api / cli_adapter 平级，实现同一个 Maker.generate() 接口。
Checkers 固定不动，换 DSH 只改 profile 里的 "maker": "dsh"。

调用约定（全部可用环境变量覆盖）：
    DSH_BIN=dsh                 可执行文件
    DSH_MAKER_PROFILE=headless  用的 profile（**不要用 DSH_PROFILE**，
                                那是用户全局的桌面 profile，会撞车）
    DSH_ARGS=""                 额外参数，空格分隔
    DSH_TIMEOUT=600             超时秒数
    DSH_BASE_URL                传给子进程的 DEEPSEEK_BASE_URL

⚠️ DeepSeek 的 DSH 走 **Messages（Anthropic 兼容）** 协议，不是 /chat/completions。
   base 必须是 https://api.deepseek.com/anthropic
   用 https://api.deepseek.com 会得到 HTTP_404: DeepSeek Messages request failed。

命令形如：
    dsh --profile headless "<prompt>"      # 在工作目录下执行
"""
from __future__ import annotations

import os
import shlex
import subprocess
import time
from pathlib import Path

from .base import Maker, MakerResult


class DshMaker(Maker):
    name = "dsh"
    type = "cli"

    def __init__(self, bin_path: str | None = None, profile: str | None = None,
                 extra_args: str | None = None, timeout: int | None = None,
                 model: str = "dsh"):
        self.bin_path = bin_path or os.environ.get("DSH_BIN", "dsh")
        self.profile = profile or os.environ.get("DSH_MAKER_PROFILE", "headless")
        self.extra_args = extra_args if extra_args is not None else os.environ.get("DSH_ARGS", "")
        self.timeout = int(timeout or os.environ.get("DSH_TIMEOUT", "600"))
        self.base_url = os.environ.get(
            "DSH_BASE_URL", "https://api.deepseek.com/anthropic")
        self.model = model

    def _argv(self, prompt: str) -> list[str]:
        argv = [self.bin_path, "--profile", self.profile]
        if self.extra_args:
            argv += shlex.split(self.extra_args)
        argv.append(prompt)
        return argv

    def generate(self, workdir: str, prompt: str,
                 feedback: str | None = None) -> MakerResult:
        wd = Path(workdir)
        wd.mkdir(parents=True, exist_ok=True)

        full = prompt if not feedback else (
            f"{prompt}\n\n## 上一轮验收失败，请修复\n```\n{feedback[:4000]}\n```")

        argv = self._argv(full)
        t0 = time.time()
        try:
            env = dict(os.environ)
            env["DEEPSEEK_BASE_URL"] = self.base_url   # 必须覆盖：环境里常带错误的 base
            proc = subprocess.run(argv, cwd=str(wd), capture_output=True,
                                  text=True, timeout=self.timeout, env=env)
        except FileNotFoundError:
            return MakerResult(success=False, model=self.model,
                               error=f"找不到可执行文件：{self.bin_path}（设 DSH_BIN 指定）")
        except subprocess.TimeoutExpired:
            return MakerResult(success=False, model=self.model,
                               error=f"DSH 超时（{self.timeout}s）")

        elapsed = time.time() - t0
        # stdout 是答案，stderr 是诊断（插件告警等）——分开，只把答案进 raw_output
        out = (proc.stdout or "").strip()
        diag = (proc.stderr or "").strip()
        if proc.returncode != 0 and not out:
            out = diag[-800:]

        files: dict[str, str] = {}
        for p in wd.rglob("*"):
            rel = p.relative_to(wd)
            # 跳过隐藏目录（.git / .dsh / .chrome-profile* 等）与依赖目录
            if p.is_file() and not any(part.startswith(".") or part in
                                       ("node_modules", "__pycache__") for part in rel.parts):
                try:
                    files[str(rel)] = p.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue

        if "Messages request failed (404)" in diag:
            diag = ("DeepSeek 的 DSH 走 Messages 协议，base 必须是 "
                    "https://api.deepseek.com/anthropic（现在用的是 "
                    f"{os.environ.get('DEEPSEEK_BASE_URL', '?')}）\n" + diag[-300:])
        if "MISSING_CREDENTIAL" in diag:
            diag = "缺少 DEEPSEEK_API_KEY（DSH 通过 credentials service 读）\n" + diag[-300:]

        ok = proc.returncode == 0 and bool(files)
        return MakerResult(
            success=ok, files=files, output_dir=str(wd),
            error="" if ok else f"退出码 {proc.returncode}；{diag[-500:]}",
            model=f"{self.model} ({self.profile})",
            cost_estimate_yuan=0.0,      # DSH 自己记账；这里不重复算
            raw_output=f"{out}\n[elapsed {elapsed:.1f}s]",
        )
