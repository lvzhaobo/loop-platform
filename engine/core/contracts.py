"""Phase 2 共享合同 — 所有 Port 之间交换的数据结构。

RunContext → SpecBundle → (Maker) → ArtifactBundle → CheckReport → DeliveryResult

所有 Result 必须可 JSON 序列化。status ∈ {passed, failed, unavailable, indeterminate, skipped}。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from engine.checkers.base import CheckStatus


# ══════════════════════════════════════════════════════════════════════
# 运行上下文
# ══════════════════════════════════════════════════════════════════════

@dataclass
class RunContext:
    """一次交付运行的完整上下文。每个 run_id 唯一。"""
    run_id: str                                     # 唯一运行标识
    profile: str                                    # Profile 名称
    workspace: str                                  # 仓库根路径
    task: str                                       # 用例/任务名
    hashes: dict[str, str] = field(default_factory=dict)  # {"input": sha, "spec": sha}
    attempt: int = 1                                # 重试次数
    started_at: str = ""                            # ISO 时间戳
    component_versions: dict[str, str] = field(default_factory=dict)  # {"compiler": "0.1.0"}


# ══════════════════════════════════════════════════════════════════════
# Spec 契约包
# ══════════════════════════════════════════════════════════════════════

@dataclass
class SpecBundle:
    """Compiler 产出：编译后的结构化 Spec 三件套。"""
    spec_path: str              # 主 spec 文件路径
    manifest_path: str          # manifest.json 路径
    acceptance_path: str        # acceptance.json 路径
    provenance: str = "simple"  # 编译器来源："simple" | "mumuspec"
    meta: dict = field(default_factory=dict)  # 额外元数据

    def validate(self) -> bool:
        """三件套文件是否都存在且可读。"""
        import os
        return all(os.path.isfile(p) for p in [
            self.spec_path, self.manifest_path, self.acceptance_path
        ])

    def to_dict(self) -> dict:
        return {
            "spec_path": self.spec_path,
            "manifest_path": self.manifest_path,
            "acceptance_path": self.acceptance_path,
            "provenance": self.provenance,
            "meta": self.meta,
        }


# ══════════════════════════════════════════════════════════════════════
# 制品包
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ArtifactBundle:
    """Maker 产出：生成代码的打包描述。"""
    output_dir: str                                 # 产物目录路径
    files: list[str] = field(default_factory=list)  # 相对文件路径列表
    digest: str = ""                                # 全量文件 SHA256
    meta: dict = field(default_factory=dict)        # {model, cost_estimate_yuan, ...}

    def to_dict(self) -> dict:
        return {
            "output_dir": self.output_dir,
            "files": self.files,
            "digest": self.digest,
            "meta": self.meta,
        }


# ══════════════════════════════════════════════════════════════════════
# 检查报告
# ══════════════════════════════════════════════════════════════════════

@dataclass
class CheckReport:
    """Checker 汇总报告。status 为整体判定。"""
    status: CheckStatus = "unavailable"
    checks: list[dict] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)  # status 分布统计

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "checks": self.checks,
            "evidence": self.evidence,
            "summary": self.summary,
        }


# ══════════════════════════════════════════════════════════════════════
# 交付结果
# ══════════════════════════════════════════════════════════════════════

@dataclass
class DeliveryResult:
    """Delivery 产出：交付操作结果。status ∈ {passed, failed, plan_only}"""
    status: str = "plan_only"           # passed | failed | plan_only
    location: str = ""                  # 目标路径/分支/URL
    reason: str = ""                    # 失败原因
    plan: dict = field(default_factory=dict)  # dry-run 计划
    meta: dict = field(default_factory=dict)  # {adapter, duration, ...}

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "location": self.location,
            "reason": self.reason,
            "plan": self.plan,
            "meta": self.meta,
        }


# ══════════════════════════════════════════════════════════════════════
# 运行事件（Phase 4 预备）
# ══════════════════════════════════════════════════════════════════════

@dataclass
class RunEvent:
    """一次完整 run 的总结事件。Phase 2 先定义结构，Phase 4 接入 runs.jsonl。"""
    run_id: str
    profile: str
    task: str
    spec_bundle: dict = field(default_factory=dict)
    artifact_bundle: dict = field(default_factory=dict)
    check_report: dict = field(default_factory=dict)
    delivery_result: dict = field(default_factory=dict)
    attempt: int = 1
    started_at: str = ""
    finished_at: str = ""
    cost_estimate_yuan: float = 0.0
    duration_seconds: float = 0.0
    status: CheckStatus = "unavailable"

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "profile": self.profile,
            "task": self.task,
            "spec_bundle": self.spec_bundle,
            "artifact_bundle": self.artifact_bundle,
            "check_report": self.check_report,
            "delivery_result": self.delivery_result,
            "attempt": self.attempt,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "cost_estimate_yuan": self.cost_estimate_yuan,
            "duration_seconds": self.duration_seconds,
            "status": self.status,
        }
