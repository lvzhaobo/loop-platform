"""由版本化 RunEvent 构建的只读、脱敏 observability 投影。"""
from __future__ import annotations

from collections import Counter
from typing import Any

from engine.core.contracts import VALID_CHECK_STATUSES
from engine.core.evidence_store import EvidenceStore
from engine.core.event_store import EventStore
from engine.core.observability import EventError

STAGES = ("source", "compiler", "maker", "checker", "delivery")


class ObservabilityProjection:
    """以 append-only EventStore 与 EvidenceStore 投影安全、可复算的只读运营事实。"""

    def __init__(self, event_store: EventStore | None = None):
        self.event_store = event_store or EventStore(evidence_store=EvidenceStore())

    def list_runs(self, limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
        if status and status not in VALID_CHECK_STATUSES:
            raise EventError(f"无效 status: {status}")
        summaries = [self._summary(self.run(run_id)) for run_id in self._run_ids()]
        if status:
            summaries = [item for item in summaries if item["status"] == status]
        return sorted(summaries, key=lambda item: (item["last_occurred_at"], item["run_id"]), reverse=True)[:limit]

    def run(self, run_id: str) -> dict[str, Any]:
        path = self.event_store._path(run_id)
        if not path.is_file():
            raise EventError(f"RunEvent 不存在: {run_id}")
        try:
            events = self.event_store.read(run_id, verify_evidence=False)
        except EventError:
            return self._untrusted(run_id)
        if not events:
            return self._untrusted(run_id)

        projected, evidence_states = [], []
        for event in events:
            evidence_integrity = self._evidence_integrity(event)
            evidence_states.append(evidence_integrity)
            status = event.status
            if evidence_integrity == "indeterminate":
                status = "indeterminate"
            elif evidence_integrity == "unavailable":
                status = "unavailable"
            projected.append({
                "event_id": event.event_id, "sequence": event.sequence,
                "occurred_at": event.occurred_at, "stage": event.stage,
                "status": status, "original_status": event.status, "attempt": event.attempt,
                "evidence_integrity": evidence_integrity,
                "evidence": [{"digest": item.digest, "collected_at": item.collected_at,
                              "integrity": evidence_integrity} for item in event.evidence],
            })

        if "indeterminate" in evidence_states:
            integrity, status = "indeterminate", "indeterminate"
        elif "unavailable" in evidence_states:
            integrity, status = "unavailable", "unavailable"
        else:
            integrity, status = "verified", projected[-1]["status"]
        return {"schema_version": 1, "run_id": run_id, "status": status,
                "integrity": integrity, "events": projected}

    def lifecycle(self, limit: int = 100) -> list[dict[str, Any]]:
        runs = self._runs(limit)
        return [self._stage_summary(stage, runs) for stage in STAGES]

    def governance_coverage(self, limit: int = 100) -> dict[str, Any]:
        runs = self._runs(limit)
        return {
            "schema_version": 1,
            "source": "verified-event-projection",
            "coverage_scope": "evidence-backed-stage-coverage",
            "run_count": len(runs),
            "stages": [self._stage_summary(stage, runs) for stage in STAGES],
            "limitations": [
                "仅覆盖已记录的 RunEvent 与 EvidenceRef，不能推断未记录的治理控制。",
                "CI、审批、Review、外部诊断与历史兼容日志尚未接入该投影。",
            ],
        }

    def _runs(self, limit: int) -> list[dict[str, Any]]:
        """与 list_runs 使用同一份按最后事件时间排序后的运行窗口。"""
        summaries = [self._summary(self.run(run_id)) for run_id in self._run_ids()]
        summaries.sort(key=lambda item: (item["last_occurred_at"], item["run_id"]), reverse=True)
        return [self.run(item["run_id"]) for item in summaries[:limit]]

    def _run_ids(self) -> list[str]:
        """只接受 EventStore 可安全读取的 run 文件；非法文件名不会污染整个投影。"""
        run_ids = []
        for path in self.event_store.root.glob("*.jsonl"):
            if not path.is_file():
                continue
            try:
                self.event_store._path(path.stem)
            except EventError:
                continue
            run_ids.append(path.stem)
        return sorted(run_ids)

    def _evidence_integrity(self, event: Any) -> str:
        """缺证据是 unavailable；任一校验失败均为 indeterminate。"""
        if not event.evidence or not self.event_store.evidence_store:
            return "unavailable"
        try:
            for evidence in event.evidence:
                self.event_store.evidence_store.verify(evidence)
        except EventError:
            return "indeterminate"
        return "verified"

    @staticmethod
    def _latest_by_stage(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        latest = {}
        for event in events:
            previous = latest.get(event["stage"])
            if previous is None or event["sequence"] > previous["sequence"]:
                latest[event["stage"]] = event
        return latest

    @classmethod
    def _summary(cls, run: dict[str, Any]) -> dict[str, Any]:
        events = run.get("events", [])
        latest = events[-1] if events else {}
        stages = cls._latest_by_stage(events)
        return {
            "run_id": run["run_id"], "status": run["status"], "integrity": run["integrity"],
            "event_count": len(events), "last_occurred_at": latest.get("occurred_at", ""),
            "stage_statuses": {stage: stages[stage]["status"] for stage in STAGES if stage in stages},
        }

    @staticmethod
    def _untrusted(run_id: str) -> dict[str, Any]:
        return {"schema_version": 1, "run_id": run_id, "status": "indeterminate",
                "integrity": "indeterminate", "events": []}

    @classmethod
    def _stage_summary(cls, stage: str, runs: list[dict[str, Any]]) -> dict[str, Any]:
        statuses = Counter()
        recorded = indeterminate = 0
        for run in runs:
            if run["integrity"] == "indeterminate":
                indeterminate += 1
                continue
            event = cls._latest_by_stage(run.get("events", [])).get(stage)
            if event is not None:
                recorded += 1
                statuses[event["status"]] += 1
        not_reached = len(runs) - recorded - indeterminate
        return {
            "stage": stage, "run_count": len(runs), "recorded_runs": recorded,
            "not_reached_runs": not_reached, "indeterminate_runs": indeterminate,
            "status_counts": {status: statuses[status] for status in sorted(VALID_CHECK_STATUSES)},
        }
