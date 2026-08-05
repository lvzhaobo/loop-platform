"""Maker 插件化：可插拔代码生成器。

用法:
  from makers import load_maker
  maker = load_maker("deepseek")       # DeepSeek API
  maker = load_maker("claude-code")    # Claude Code CLI
  maker = load_maker("qoder")          # Qoder CLI
  maker = load_maker("copilot")        # Copilot CLI
  maker = load_maker("sample")         # 离线参考生成器

  result = maker.generate(workdir, prompt, feedback=None)
"""

from .base import Maker, MakerResult

_registry: dict[str, type[Maker]] = {}


def register(name: str):
    """装饰器：注册 Maker。"""
    def decorator(cls):
        _registry[name] = cls
        return cls
    return decorator


def load_maker(name: str | None = None, **kwargs) -> Maker:
    """工厂：按名称加载 Maker。默认 deepseek。"""
    name = name or "deepseek"
    if name == "sample":
        from . import sample_maker  # noqa: F811
        return _registry["sample"](**kwargs)

    # 延迟导入，避免循环依赖和无用加载
    if "deepseek" not in _registry:
        from . import deepseek_api  # noqa: F401
    if "cli" not in _registry:
        from . import cli_adapter  # noqa: F401

    if name in _registry:
        return _registry[name](**kwargs)

    # CLI 型 Maker 统一走 cli_adapter
    if name in ("claude-code", "qoder", "copilot", "claude", "cursor"):
        return _registry["cli"](command=name, **kwargs)

    raise ValueError(f"未知 Maker: {name}。支持: {', '.join(_registry.keys())}")
