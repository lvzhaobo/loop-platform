"""Maker 抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class MakerResult:
    """Maker 生成结果。"""
    success: bool = False
    files: dict[str, str] = field(default_factory=dict)  # {相对路径: 内容}
    output_dir: str = ""
    error: str = ""
    model: str = ""
    cost_estimate_yuan: float = 0.0
    raw_output: str = ""  # LLM 原始输出（用于调试）


class Maker(ABC):
    """代码生成器抽象基类。

    所有 Maker 实现此接口。Checkcer 固定不动，Maker 随意换。
    """

    name: str = "abstract"
    type: str = "api"  # "api" | "cli"

    @abstractmethod
    def generate(self, workdir: str, prompt: str,
                 feedback: str | None = None) -> MakerResult:
        """生成代码到 workdir。

        Args:
            workdir: 产物输出目录（已创建）
            prompt: 完整的系统 prompt（含 rules + spec + constraints）
            feedback: 上一轮验证失败日志（用于回喂修复），首次生成时为 None

        Returns:
            MakerResult: 生成结果
        """
        ...
