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


def load_adapter(name: str) -> BaseAdapter:
    if name not in _registry:
        raise ValueError(f"未知 Adapter: {name}。支持: {', '.join(_registry.keys())}")
    return _registry[name]()


def list_adapters() -> list[str]:
    return list(_registry.keys())
