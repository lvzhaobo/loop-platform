"""Adapter Registry — Phase 2。

任务来源适配器注册表。与 Compiler/Maker/Checker/Delivery 同构。
"""

from __future__ import annotations

from adapters.base import Task
from adapters.base import Adapter as BaseAdapter

_registry: dict[str, type[BaseAdapter]] = {}


def register(name: str):
    def decorator(cls):
        _registry[name] = cls
        return cls
    return decorator


def _load_builtins() -> None:
    """延迟加载内置 Provider，避免 Registry 空表依赖导入顺序。"""
    if "local_queue" not in _registry:
        from adapters import local_queue  # noqa: F401


def load_adapter(name: str, **config) -> BaseAdapter:
    _load_builtins()
    if name not in _registry:
        raise ValueError(f"未知 Adapter: {name}。支持: {', '.join(_registry.keys())}")
    return _registry[name](**config)


def list_adapters() -> list[str]:
    _load_builtins()
    return list(_registry.keys())
