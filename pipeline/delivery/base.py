"""Delivery 抽象基类 — Phase 2 Port。

ArtifactBundle → DeliveryResult。
默认不产生 Git/网络/SSH 调用；真实 delivery 需显式 Profile + 确认策略。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from engine.core.contracts import RunContext, ArtifactBundle, DeliveryResult


class Delivery(ABC):
    """制品交付抽象基类。

    先实现无副作用的 local_artifact，再将 publisher/deployer 包为 adapters。
    """

    name: str = "abstract"

    @abstractmethod
    def deliver(self, context: RunContext, artifacts: ArtifactBundle) -> DeliveryResult:
        """交付制品。

        Args:
            context: 运行上下文
            artifacts: 制品包

        Returns:
            DeliveryResult: 交付结果（plan_only 表示仅输出计划，未实际执行）
        """
        ...

    def plan(self, context: RunContext, artifacts: ArtifactBundle) -> DeliveryResult:
        """Dry-run：输出交付计划但不执行写操作。默认同 deliver。"""
        return self.deliver(context, artifacts)
