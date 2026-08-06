"""本地不可变证据库：内容与元数据均按 Run Plan scope 绑定。"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from engine.core.observability import EventError, EvidenceRef, verify_evidence_payload
from engine.core.paths import PlatformPaths

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe(value: str, label: str) -> None:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise EventError(f"{label} 非法")


class EvidenceStore:
    """只写一次的本地 evidence payload 存储，不暴露本机绝对路径。"""

    def __init__(self, root: Path | None = None):
        self.root = Path(root or (PlatformPaths.DATA_DIR / "evidence"))

    def put_json(self, value: Any, *, source: str, run_id: str, plan_digest: str, kind: str) -> EvidenceRef:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return self.put(payload, source=source, run_id=run_id, plan_digest=plan_digest, kind=kind)

    def put(self, payload: bytes, *, source: str, run_id: str, plan_digest: str, kind: str) -> EvidenceRef:
        _safe(run_id, "run_id"); _safe(kind, "evidence kind")
        if not isinstance(payload, bytes):
            raise EventError("evidence payload 必须是 bytes")
        digest = hashlib.sha256(payload).hexdigest()
        evidence_id = f"evidence-{kind}-{digest[:24]}"
        scope = {"run_id": run_id, "plan_digest": plan_digest, "kind": kind}
        ref = EvidenceRef(evidence_id, source, f"evidence://{run_id}/{evidence_id}", digest, _now(), scope)
        directory = self.root / run_id
        directory.mkdir(parents=True, exist_ok=True)
        payload_path = directory / f"{evidence_id}.bin"
        metadata_path = directory / f"{evidence_id}.json"
        metadata = {"schema_version": 1, "evidence": ref.to_dict()}
        self._create_immutable(payload_path, payload)
        self._create_immutable(metadata_path, (json.dumps(metadata, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        return ref

    @staticmethod
    def _create_immutable(path: Path, payload: bytes) -> None:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise EventError(f"evidence 已存在但内容不一致: {path.name}")
            return
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload); handle.flush(); os.fsync(handle.fileno())

    def payload(self, evidence: EvidenceRef) -> bytes:
        self._validate_ref(evidence)
        path = self.root / evidence.scope["run_id"] / f"{evidence.id}.bin"
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise EventError(f"evidence payload 不存在: {evidence.id}") from exc
        if not verify_evidence_payload(evidence, payload):
            raise EventError(f"evidence digest 校验失败: {evidence.id}")
        return payload

    def verify(self, evidence: EvidenceRef) -> bool:
        self.payload(evidence)
        metadata_path = self.root / evidence.scope["run_id"] / f"{evidence.id}.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            stored = EvidenceRef(**metadata["evidence"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise EventError(f"evidence metadata 无效: {evidence.id}") from exc
        if stored.to_dict() != evidence.to_dict():
            raise EventError(f"evidence metadata scope 不匹配: {evidence.id}")
        return True

    @staticmethod
    def _validate_ref(evidence: EvidenceRef) -> None:
        _safe(evidence.id, "evidence.id")
        _safe(evidence.scope["run_id"], "evidence.scope.run_id")
        if not evidence.uri.startswith("evidence://") or "\\" in evidence.uri:
            raise EventError("evidence.uri 必须是安全的 evidence URI")
