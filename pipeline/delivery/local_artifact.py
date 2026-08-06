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

    def deliver(self, context: RunContext, artifacts: ArtifactBundle) -> DeliveryResult:
        # 记录交付计划到本地
        plan_file = os.path.join(artifacts.output_dir, "delivery_plan.json")
        plan = {
            "run_id": context.run_id,
            "profile": context.profile,
            "task": context.task,
            "output_dir": artifacts.output_dir,
            "files": artifacts.files,
            "digest": artifacts.digest,
            "adapter": self.name,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        try:
            os.makedirs(artifacts.output_dir, exist_ok=True)
            with open(plan_file, "w") as f:
                json.dump(plan, f, indent=2, ensure_ascii=False)
        except OSError as e:
            return DeliveryResult(
                status="failed",
                reason=f"写入 delivery_plan.json 失败: {e}",
                location=plan_file,
                plan=plan,
            )

        return DeliveryResult(
            status="passed",
            location=plan_file,
            plan=plan,
            meta={"adapter": self.name},
        )
