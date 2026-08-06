"""Checker 抽象基类。与 makers/base.py 同构。

F5: 统一五态检查模型，禁止无证据伪装为通过。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

# ── 五态检查结果 ──
# passed:   确定性验收通过
# failed:   确定性验收不通过
# unavailable: 证据缺失，无法判断（如未运行 /better-harness）
# indeterminate: 证据存在但模糊/不确定
# skipped:  该检查项不适用于当前场景
CheckStatus = Literal["passed", "failed", "unavailable", "indeterminate", "skipped"]


def status_from_bool(passed: bool, *, indeterminate: bool = False, skipped: bool = False) -> CheckStatus:
    """将布尔 pass 转为 CheckStatus。
    
    passed=True  → "passed"
    passed=False → "failed" (或 "indeterminate"/"skipped")
    """
    if passed:
        return "passed"
    if skipped:
        return "skipped"
    if indeterminate:
        return "indeterminate"
    return "failed"


@dataclass
class CheckerResult:
    """验证结果。F5: 增加 status 字段。"""
    pass_count: int = 0
    total_count: int = 0
    checks: list[dict] = field(default_factory=list)  # [{name, status, pass, detail}]
    all_pass: bool = False

    def summarize(self) -> dict[str, int]:
        """按 status 统计检查项分布。"""
        counts: dict[str, int] = {}
        for c in self.checks:
            s = c.get("status", "passed" if c.get("pass") else "failed")
            counts[s] = counts.get(s, 0) + 1
        return counts


class Checker(ABC):
    """验收器抽象基类。每个 Checker 实现 check() 方法。
    
    F5: 增加 run_id 参数以显式绑定报告，禁止跨任务猜测。
    """

    name: str = "abstract"

    @abstractmethod
    def check(self, target_dir: str, *, run_id: str = "") -> CheckerResult:
        """检查产物目录，返回验证结果。
        
        Args:
            target_dir: 产物目录路径
            run_id: 显式绑定 run_id，仅消费该 run_id 的报告。空字符串时返回 unavailable。
        """
        ...
