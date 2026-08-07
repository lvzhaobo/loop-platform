"""Checker 注册表。与 makers/__init__.py 同构。"""

from .base import Checker, CheckerResult

_registry: dict[str, type[Checker]] = {}


def register(name: str):
    def decorator(cls):
        _registry[name] = cls
        return cls
    return decorator


def load_checker(name: str = "security", **kwargs) -> Checker:
    """工厂：按名称加载 Checker。"""
    if not _registry:
        from . import security  # noqa: F401
        from . import runtime  # noqa: F401
        from . import e2e  # noqa: F401
        from . import process  # noqa: F401
        from . import pages  # noqa: F401

    if name == "all":
        from .all_checker import AllChecker
        return AllChecker()

    if name in _registry:
        return _registry[name](**kwargs)

    raise ValueError(f"未知 Checker: {name}。支持: {', '.join(_registry.keys())}")


def list_checkers() -> list[str]:
    if not _registry:
        from . import security, runtime, e2e, process, pages  # noqa: F401
    return list(_registry.keys())
