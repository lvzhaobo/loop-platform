"""Checker 抽象基类。与 makers/base.py 同构。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class CheckerResult:
    """验证结果。"""
    pass_count: int = 0
    total_count: int = 0
    checks: list[dict] = field(default_factory=list)  # [{name, pass, detail}]
    all_pass: bool = False


class Checker(ABC):
    """验收器抽象基类。每个 Checker 实现 check() 方法。"""

    name: str = "abstract"

    @abstractmethod
    def check(self, target_dir: str) -> CheckerResult:
        """检查产物目录，返回验证结果。"""
        ...
