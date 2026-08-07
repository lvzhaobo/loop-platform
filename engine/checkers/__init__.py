"""Checker 注册表。与 makers/__init__.py 同构。"""

from .base import Checker, CheckerResult

_registry: dict[str, type[Checker]] = {}


def register(name: str):
    def decorator(cls):
        _registry[name] = cls
        return cls
    return decorator


def _load_builtin_checkers() -> None:
    """Import every built-in Checker even when one was imported directly first."""
    from . import security, runtime, e2e, process, pages  # noqa: F401


def load_checker(name: str = "security", **kwargs) -> Checker:
    """工厂：按名称加载 Checker。"""
    _load_builtin_checkers()

    if name == "all":
        from .all_checker import AllChecker
        return AllChecker()

    if name in _registry:
        return _registry[name](**kwargs)

    raise ValueError(f"未知 Checker: {name}。支持: {', '.join(_registry.keys())}")


def list_checkers() -> list[str]:
    _load_builtin_checkers()
    return list(_registry.keys())
