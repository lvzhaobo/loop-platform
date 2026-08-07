"""Delivery Registry — Phase 2。

与 Compiler/Maker/Checker 同构。
"""

from __future__ import annotations

from .base import Delivery

_registry: dict[str, type[Delivery]] = {}


def register(name: str):
    def decorator(cls):
        _registry[name] = cls
        return cls
    return decorator


def load_delivery(name: str, **config) -> Delivery:
    if name not in _registry:
        raise ValueError(f"未知 Delivery: {name}。支持: {', '.join(_registry.keys())}")
    return _registry[name](**config)


def list_deliveries() -> list[str]:
    return list(_registry.keys())
