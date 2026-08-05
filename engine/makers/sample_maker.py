"""Sample 离线 Maker（确定性，零密钥）。"""

import os
from pathlib import Path

from .base import Maker, MakerResult
from . import register


@register("sample")
class SampleMaker(Maker):
    name = "sample"
    type = "api"

    def generate(self, workdir: str, prompt: str,
                 feedback: str | None = None) -> MakerResult:
        # 检查是否有 Spec 形态的 manifest
        workdir_path = Path(workdir)
        # Sample 模式只在显式 enable 时工作
        return MakerResult(
            success=False,
            error="Sample 离线模式暂不可用，请使用 HARNESS_MODE=real 并确保 DEEPSEEK_API_KEY 已设置",
            output_dir=workdir,
        )
