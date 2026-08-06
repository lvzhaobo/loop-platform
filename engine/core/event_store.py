"""Append-only RunEvent JSONL 存储及只读重放。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Iterable

from engine.core.evidence_store import EvidenceStore
from engine.core.observability import EventError, RunEvent, event_from_dict
from engine.core.paths import PlatformPaths

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class EventStore:
    """以单个 run 一个 JSONL 文件持久化阶段事实，拒绝改写、跳号与跨 run 数据。"""

    def __init__(self, root: Path | None = None, evidence_store: EvidenceStore | None = None):
        self.root = Path(root or PlatformPaths.RUN_EVENTS_DIR)
        self.evidence_store = evidence_store

    def append(self, event: RunEvent) -> Path:
        self._validate_event(event)
        path = self._path(event.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a+", encoding="utf-8") as handle:
            self._lock(handle)
            try:
                handle.seek(0)
                existing = self._parse_lines(handle, event.run_id)
                expected = len(existing) + 1
                if event.sequence != expected:
                    raise EventError(f"event sequence 必须为 {expected}，收到 {event.sequence}")
                if any(item.event_id == event.event_id for item in existing):
                    raise EventError(f"event_id 已存在: {event.event_id}")
                handle.seek(0, os.SEEK_END)
                handle.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush(); os.fsync(handle.fileno())
            finally:
                self._unlock(handle)
        return path

    def read(self, run_id: str, *, verify_evidence: bool = False) -> list[RunEvent]:
        path = self._path(run_id)
        if not path.exists():
            raise EventError(f"RunEvent 不存在: {run_id}")
        with open(path, encoding="utf-8") as handle:
            events = self._parse_lines(handle, run_id)
        if verify_evidence:
            if not self.evidence_store:
                raise EventError("读取证据验证需要 EvidenceStore")
            for event in events:
                for evidence in event.evidence:
                    self.evidence_store.verify(evidence)
        return events

    def replay(self, run_id: str) -> dict:
        events = self.read(run_id, verify_evidence=True)
        latest = events[-1]
        return {"run_id": run_id, "verified": True, "event_count": len(events),
                "status": latest.status, "events": [event.to_dict() for event in events]}

    def _path(self, run_id: str) -> Path:
        if not isinstance(run_id, str) or not _SAFE_ID.fullmatch(run_id):
            raise EventError("run_id 非法")
        return self.root / f"{run_id}.jsonl"

    def _validate_event(self, event: RunEvent) -> None:
        if not isinstance(event, RunEvent):
            raise EventError("只能追加 RunEvent")
        if self.evidence_store:
            for evidence in event.evidence:
                self.evidence_store.verify(evidence)

    @staticmethod
    def _parse_lines(lines: Iterable[str], expected_run_id: str) -> list[RunEvent]:
        events: list[RunEvent] = []
        ids: set[str] = set()
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                raise EventError(f"RunEvent JSONL 包含空行: {number}")
            try:
                event = event_from_dict(json.loads(line))
            except json.JSONDecodeError as exc:
                raise EventError(f"RunEvent JSON 无效: 第 {number} 行") from exc
            if event.run_id != expected_run_id:
                raise EventError("RunEvent 文件含跨 run 记录")
            if event.sequence != number:
                raise EventError(f"RunEvent sequence 不连续: 第 {number} 行")
            if event.event_id in ids:
                raise EventError(f"RunEvent event_id 重复: {event.event_id}")
            ids.add(event.event_id); events.append(event)
        return events

    @staticmethod
    def _lock(handle) -> None:
        try:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except ImportError:  # pragma: no cover - Windows fallback
            pass

    @staticmethod
    def _unlock(handle) -> None:
        try:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except ImportError:  # pragma: no cover - Windows fallback
            pass
