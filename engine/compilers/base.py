"""Compiler 抽象基类 — Phase 2 Port。

需求文本 → SpecBundle（manifest.json + acceptance.json + spec 文件）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from engine.core.contracts import RunContext, SpecBundle


class Compiler(ABC):
    """需求编译器抽象基类。

    把一段自然语言需求编译为结构化 Spec 三件套。
    替换 Compiler 不要求修改下游 Maker。
    """

    name: str = "abstract"

    @abstractmethod
    def compile(self, context: RunContext, requirement: str) -> SpecBundle:
        """编译需求文本为 Spec 三件套。

        Args:
            context: 运行上下文（包含 workspace、task 等信息）
            requirement: 自然语言需求文本

        Returns:
            SpecBundle: 三件套路径 + provenance

        Raises:
            CompilerError: 编译失败（合同不合格、模型调用失败等）
        """
        ...


class CompilerError(Exception):
    """Compiler 编译错误。下游 Maker 不启动。"""
    pass
