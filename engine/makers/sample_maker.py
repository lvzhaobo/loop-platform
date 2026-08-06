"""Sample 离线 Maker（确定性、零密钥、零网络）。"""

from __future__ import annotations

from pathlib import Path

from . import register
from .base import Maker, MakerResult


@register("sample")
class SampleMaker(Maker):
    """生成受控的最小番茄钟制品，专用于 fixture-local Profile。"""

    name = "sample"
    type = "local"

    def generate(self, workdir: str, prompt: str,
                 feedback: str | None = None) -> MakerResult:
        output = Path(workdir)
        output.mkdir(parents=True, exist_ok=True)
        files = {
            "index.html": """<!doctype html>
<html lang=\"zh-CN\"><meta charset=\"utf-8\"><title>番茄钟</title>
<body><main><h1>番茄钟</h1><output id=\"timer\">25:00</output>
<button id=\"start\" type=\"button\">开始</button></main></body></html>\n""",
            "README.md": "# fixture-local 产物\n\n由 SampleMaker 离线生成；不调用模型或网络。\n",
        }
        for relative, content in files.items():
            (output / relative).write_text(content, encoding="utf-8")
        return MakerResult(
            success=True,
            files=files,
            output_dir=str(output),
            model="sample-deterministic",
            cost_estimate_yuan=0.0,
        )
