"""由版本化 RunEvent 构建的只读、脱敏 observability 投影。"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from engine.core.contracts import VALID_CHECK_STATUSES
from engine.core.evidence_store import EvidenceStore
from engine.core.event_store import EventStore
from engine.core.observability import EventError
from engine.core.paths import PlatformPaths

STAGES = ("source", "compiler", "maker", "checker", "delivery")
_GITHUB_REPOSITORY = re.compile(r"^github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)\.git$")
_COMMIT_SHA = re.compile(r"^[0-9a-f]{7,64}$", re.IGNORECASE)
_SAFE_STATUS = re.compile(r"^[a-z_]{1,32}$")


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

    def _delivery_fact(self, event: Any, evidence_integrity: str) -> dict[str, Any] | None:
        """Expose only audited GitHub facts from a verified DeliveryResult evidence payload."""
        if event.stage != "delivery" or event.status != "passed" or evidence_integrity != "verified":
            return None
        evidence_store = self.event_store.evidence_store
        if not evidence_store:
            return None
        try:
            payload = json.loads(evidence_store.payload(event.evidence[0]).decode("utf-8"))
            plan = payload.get("plan") if isinstance(payload, dict) else None
            meta = payload.get("meta") if isinstance(payload, dict) else None
            if payload.get("status") != "passed" or not isinstance(plan, dict) or plan.get("adapter") != "github_workflow":
                return None
            match = _GITHUB_REPOSITORY.fullmatch(str(plan.get("repo", "")))
            branch = plan.get("branch")
            if not match or not isinstance(branch, str) or not branch or len(branch) > 200:
                return None
        except (EventError, UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError):
            return None
        repository_url = f"https://github.com/{match.group(1)}/{match.group(2)}"
        result = {"type": "github_workflow", "status": "passed", "repository_url": repository_url, "branch": branch}
        location = self._safe_url(payload.get("location"), host="github.com")
        if location and location.startswith(repository_url + "/tree/"):
            result["location_url"] = location
        commit_sha = plan.get("commit_sha")
        if isinstance(commit_sha, str) and _COMMIT_SHA.fullmatch(commit_sha):
            result["commit_sha"] = commit_sha
            result["commit_url"] = f"{repository_url}/commit/{commit_sha}"
        if isinstance(meta, dict):
            for key in ("workflow_status", "ecs_health"):
                value = meta.get(key)
                if isinstance(value, str) and _SAFE_STATUS.fullmatch(value):
                    result[key] = value
            deployment_url = self._safe_url(meta.get("deployment_url"))
            if deployment_url:
                result["deployment_url"] = deployment_url
        return result

    @staticmethod
    def _safe_url(value: Any, *, host: str | None = None) -> str | None:
        if not isinstance(value, str) or len(value) > 2048:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return None
        if host and parsed.hostname != host:
            return None
        if parsed.query or parsed.fragment:
            return None
        return value

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

        projected, evidence_states, delivery_candidates = [], [], []
        for event in events:
            evidence_integrity = self._evidence_integrity(event)
            evidence_states.append(evidence_integrity)
            if event.stage == "delivery":
                delivery_candidates.append((event, evidence_integrity))
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
        delivery = next((fact for event, evidence_integrity in reversed(delivery_candidates)
                         if (fact := self._delivery_fact(event, evidence_integrity)) is not None), None)
        task = self._frozen_task(run_id, events)
        artifact = self._artifact_preview(run_id, events)
        return {"schema_version": 1, "run_id": run_id, "status": status, "integrity": integrity,
                "events": projected, "task": task, "artifact": artifact, "delivery": delivery}

    @staticmethod
    def _frozen_task(run_id: str, events: list[Any]) -> dict[str, Any] | None:
        """只在冻结 Plan 与同一 RunEvent 任务绑定一致时公开需求内容。"""
        task_ids = {event.task_id for event in events}
        plan_digests = {event.plan_digest for event in events}
        if len(task_ids) != 1 or len(plan_digests) != 1:
            return None
        try:
            path = PlatformPaths.RUN_PLANS_DIR / f"{run_id}.json"
            plan = json.loads(path.read_text(encoding="utf-8"))
            task = plan["task"]
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if plan.get("run_id") != run_id or plan.get("digest") != next(iter(plan_digests)):
            return None
        if str(task.get("id", "")) != next(iter(task_ids)):
            return None
        profile = plan.get("profile") if isinstance(plan.get("profile"), dict) else {}
        return {
            "id": str(task["id"]),
            "title": str(task.get("title", task["id"])),
            "priority": task.get("priority", 99),
            "profile_id": str(profile.get("id", "")),
        }

    @staticmethod
    def _artifact_preview(run_id: str, events: list[Any]) -> dict[str, Any] | None:
        """按受控 Maker 输出约定解析实际存在的本地入口，不扫描无关目录。"""
        artifact_digest = ""
        for event in events:
            if event.stage == "maker" and event.status == "passed":
                artifact_digest = event.digests.get("artifact", "")
        if not artifact_digest:
            return None
        output_root = PlatformPaths.OUTPUT_DIR.resolve()
        relative_dir = Path(f"maker-{run_id}")
        output_dir = (output_root / relative_dir).resolve()
        try:
            output_dir.relative_to(output_root)
        except ValueError:
            return None
        if not output_dir.is_dir():
            return {"digest": artifact_digest, "file_count": 0, "preview_url": None}
        files = [path for path in output_dir.rglob("*") if path.is_file()]
        entry = output_dir / "index.html"
        preview_url = f"/output/{(relative_dir / 'index.html').as_posix()}" if entry.is_file() else None
        return {"digest": artifact_digest, "file_count": len(files), "preview_url": preview_url}

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
            "task": run.get("task"), "artifact": run.get("artifact"),
        }

    @staticmethod
    def _untrusted(run_id: str) -> dict[str, Any]:
        return {"schema_version": 1, "run_id": run_id, "status": "indeterminate",
                "integrity": "indeterminate", "events": [], "task": None, "artifact": None, "delivery": None}

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
