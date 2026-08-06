"""MumuSpecCompiler — 六轮详细编译。

Phase 2: 预留接口。完整实现需等 MumuSpec 六轮编译器就绪。
当前使用 SimpleCompiler 作为 fallback。
"""

from __future__ import annotations

from engine.core.contracts import RunContext, SpecBundle
from engine.compilers.base import Compiler, CompilerError
from engine.compilers.registry import register
from engine.compilers.registry import load_compiler


@register("mumuspec")
class MumuSpecCompiler(Compiler):
    """MumuSpec 六轮编译 — Phase 2 预留。

    在 MumuSpec 编译器就绪前，回退到 SimpleCompiler。
    真实实现需运行六轮：领域分析 → 用户故事 → 数据模型 → API → UI → 验收标准。
    """

    name = "mumuspec"

    def compile(self, context: RunContext, requirement: str) -> SpecBundle:
        # Phase 2: fallback 到 simple，Phase 3 Profile 中可配置
        # 当六轮编译器就绪后，切换此实现
        try:
            simple = load_compiler("simple")
            bundle = simple.compile(context, requirement)
            bundle.provenance = "mumuspec-fallback"
            bundle.meta["compiler"] = "mumuspec→simple"
            return bundle
        except Exception:
            raise CompilerError(
                "MumuSpec 六轮编译器尚未就绪，且 SimpleCompiler fallback 失败"
            )
