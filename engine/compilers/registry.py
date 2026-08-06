"""Compiler Registry — Phase 2。

与 Maker/Checker 同构：@register("name") 装饰器 + load_compiler(name)。
"""

from __future__ import annotations

from .base import Compiler

_registry: dict[str, type[Compiler]] = {}


def register(name: str):
    """装饰器：注册 Compiler 子类。"""
    def decorator(cls):
        _registry[name] = cls
        return cls
    return decorator


def load_compiler(name: str) -> Compiler:
    """按名称加载 Compiler 实例。"""
    if name not in _registry:
        raise ValueError(f"未知 Compiler: {name}。支持: {', '.join(_registry.keys())}")
    return _registry[name]()


def list_compilers() -> list[str]:
    """列出所有已注册 Compiler 名称。"""
    return list(_registry.keys())
