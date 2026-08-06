"""LocalArtifactDelivery — 零副作用交付。

仅记录交付结果到本地，不产生 Git push / SSH / 网络 / ECS 调用。
默认 Profile 使用此 adapter。
"""

from __future__ import annotations

import json
import os
import time

from engine.core.contracts import RunContext, ArtifactBundle, DeliveryResult
from pipeline.delivery.base import Delivery
from pipeline.delivery.registry import register


@register("local_artifact")
class LocalArtifactDelivery(Delivery):
    """本地制品交付：仅记录到 output/，不发布。"""

    name = "local_artifact"

    def _plan(self, context: RunContext, artifacts: ArtifactBundle) -> tuple[str, dict]:
        plan_file = os.path.join(artifacts.output_dir, "delivery_plan.json")
        return plan_file, {
            "run_id": context.run_id,
            "profile": context.profile,
            "task": context.task,
            "output_dir": artifacts.output_dir,
            "files": artifacts.files,
            "digest": artifacts.digest,
            "adapter": self.name,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def plan(self, context: RunContext, artifacts: ArtifactBundle) -> DeliveryResult:
        """仅返回交付预览；不创建目录，也不写入计划文件。"""
        plan_file, plan = self._plan(context, artifacts)
        return DeliveryResult(
            status="plan_only",
            location=plan_file,
            plan=plan,
            meta={"adapter": self.name, "dry_run": True},
        )

    def deliver(self, context: RunContext, artifacts: ArtifactBundle) -> DeliveryResult:
        """将已批准的本地计划写入制品目录；不触发任何外部交付。"""
        plan_file, plan = self._plan(context, artifacts)
        try:
            os.makedirs(artifacts.output_dir, exist_ok=True)
            with open(plan_file, "w", encoding="utf-8") as handle:
                json.dump(plan, handle, indent=2, ensure_ascii=False)
        except OSError as exc:
            return DeliveryResult(
                status="failed",
                reason=f"写入 delivery_plan.json 失败: {exc}",
                location=plan_file,
                plan=plan,
            )

        return DeliveryResult(
            status="passed",
            location=plan_file,
            plan=plan,
            meta={"adapter": self.name},
        )
