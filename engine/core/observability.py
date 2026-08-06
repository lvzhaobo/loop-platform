"""Phase 4 事件与证据内核：append-only、可校验、无外部副作用。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from engine.core.contracts import VALID_CHECK_STATUSES
from engine.core.paths import PlatformPaths

_EVENT_STAGES = frozenset({"source", "compiler", "maker", "checker", "delivery"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_STAGE_DIGESTS = {
    "source": frozenset({"input"}),
    "compiler": frozenset({"input", "spec", "acceptance"}),
    "maker": frozenset({"input", "spec", "acceptance", "artifact"}),
    "checker": frozenset({"input", "spec", "acceptance", "artifact"}),
    "delivery": frozenset({"input", "spec", "acceptance", "artifact"}),
}


class EventError(ValueError):
    """事件或证据不满足事实合同。"""


def _require(value: Any, label: str) -> None:
    if not value:
        raise EventError(f"{label} 不能为空")


def _require_digest(value: str, label: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise EventError(f"{label} 必须是 SHA-256 hex digest")


def _require_timestamp(value: str, label: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise EventError(f"{label} 必须是 ISO-8601 时间") from exc


@dataclass(frozen=True)
class EvidenceRef:
    """一项不暴露本机路径的可验证证据引用。"""

    id: str
    source: str
    uri: str
    digest: str
    collected_at: str
    scope: dict[str, str]

    def __post_init__(self) -> None:
        for value, label in ((self.id, "evidence.id"), (self.source, "evidence.source"),
                             (self.uri, "evidence.uri")):
            _require(value, label)
        _require_digest(self.digest, "evidence.digest")
        _require_timestamp(self.collected_at, "evidence.collected_at")
        if not isinstance(self.scope, dict):
            raise EventError("evidence.scope 必须是对象")
        for key in ("run_id", "plan_digest", "kind"):
            _require(self.scope.get(key), f"evidence.scope.{key}")
        _require_digest(self.scope["plan_digest"], "evidence.scope.plan_digest")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunEvent:
    """某一交付阶段的不可变事实记录，而非历史日志的推断结果。"""

    event_id: str
    run_id: str
    sequence: int
    occurred_at: str
    stage: str
    status: str
    profile_ref: str
    task_id: str
    plan_digest: str
    digests: dict[str, str]
    component_versions: dict[str, str]
    attempt: int = 1
    evidence: tuple[EvidenceRef, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self) -> None:
        for value, label in ((self.event_id, "event_id"), (self.run_id, "run_id"),
                             (self.profile_ref, "profile_ref"), (self.task_id, "task_id")):
            _require(value, label)
        if not _SAFE_ID.fullmatch(self.event_id) or not _SAFE_ID.fullmatch(self.run_id):
            raise EventError("event_id 与 run_id 只能包含字母、数字、点、下划线和连字符")
        if not isinstance(self.sequence, int) or self.sequence < 1:
            raise EventError("sequence 必须是正整数")
        _require_timestamp(self.occurred_at, "occurred_at")
        if self.stage not in _EVENT_STAGES:
            raise EventError(f"未知 stage: {self.stage}")
        if self.status not in VALID_CHECK_STATUSES:
            raise EventError(f"无效 event status: {self.status}")
        _require_digest(self.plan_digest, "plan_digest")
        if not isinstance(self.attempt, int) or self.attempt < 1:
            raise EventError("attempt 必须是正整数")
        if not isinstance(self.digests, dict):
            raise EventError("digests 必须是对象")
        allowed_digests = _STAGE_DIGESTS[self.stage]
        unknown_digests = set(self.digests) - allowed_digests
        if unknown_digests:
            raise EventError(f"{self.stage} 事件不能声明未来阶段 digest: {sorted(unknown_digests)}")
        if "input" not in self.digests:
            raise EventError("digests 必须包含 input")
        if self.status == "passed" and not allowed_digests.issubset(self.digests):
            missing = sorted(allowed_digests - set(self.digests))
            raise EventError(f"{self.stage} 通过事件缺少 digest: {missing}")
        for key, value in self.digests.items():
            _require_digest(value, f"digests.{key}")
        if not all(isinstance(key, str) and isinstance(value, str) and value
                   for key, value in self.component_versions.items()):
            raise EventError("component_versions 必须是非空字符串映射")
        if self.status == "passed" and not self.evidence:
            raise EventError("passed 事件必须至少关联一项 evidence")
        for evidence in self.evidence:
            if evidence.scope["run_id"] != self.run_id:
                raise EventError("evidence 不能跨 run 引用")
            if evidence.scope["plan_digest"] != self.plan_digest:
                raise EventError("evidence.plan_digest 必须绑定当前 Run Plan")

    def to_dict(self) -> dict[str, Any]:
        content = asdict(self)
        content["evidence"] = [item.to_dict() for item in self.evidence]
        return content


def event_from_dict(value: dict[str, Any]) -> RunEvent:
    """将 JSONL 记录严格解析为受验证的 RunEvent。"""
    try:
        data = dict(value)
        data["evidence"] = tuple(EvidenceRef(**item) for item in data.get("evidence", ()))
        return RunEvent(**data)
    except (TypeError, ValueError) as exc:
        raise EventError(f"无效 RunEvent: {exc}") from exc


def verify_evidence_payload(evidence: EvidenceRef, payload: bytes) -> bool:
    """校验证据内容，不执行 URI、不访问网络或文件系统。"""
    return hashlib.sha256(payload).hexdigest() == evidence.digest
