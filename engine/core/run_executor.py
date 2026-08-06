"""受 Profile 与证据合同约束的离线参考执行器。"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
from typing import Any

from engine.core.compat import check_with_context, make_with_context
from engine.core.evidence_store import EvidenceStore
from engine.core.event_store import EventStore
from engine.core.observability import RunEvent
from engine.core.profiles import (Profile, ProfileError, create_run_plan,
                                  create_source_adapter, load_profile,
                                  persist_run_plan, run_context, validate_profile)
from engine.core.paths import PlatformPaths


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _file_digest(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _task_dict(task: Any) -> dict[str, Any]:
    return {"id": task.id, "title": task.title, "source": task.source,
            "case": task.case, "priority": task.priority,
            "spec_text": task.spec_text or "", "extra": task.extra}


def _redact_paths(value: Any) -> Any:
    if isinstance(value, dict): return {key: _redact_paths(item) for key, item in value.items()}
    if isinstance(value, list): return [_redact_paths(item) for item in value]
    if isinstance(value, str):
        if Path(value).is_absolute(): return "<local-path>"
        return value.replace(str(PlatformPaths.ROOT), "<workspace>")
    return value


@contextmanager
def _fixture_environment():
    original = os.environ.get("HARNESS_MODE")
    os.environ["HARNESS_MODE"] = "sample"
    try: yield
    finally:
        if original is None: os.environ.pop("HARNESS_MODE", None)
        else: os.environ["HARNESS_MODE"] = original


@dataclass(frozen=True)
class ExecutionResult:
    run_id: str
    plan_digest: str
    task_id: str
    status: str
    event_count: int
    reason: str = ""
    delivery: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "plan_digest": self.plan_digest, "task_id": self.task_id,
                "status": self.status, "event_count": self.event_count,
                "reason": self.reason, "delivery": self.delivery or {}}


class ProfileRunExecutor:
    """执行受控 Profile；仅允许白名单组合，并为每阶段持久证据后追加事件。"""

    def __init__(self, evidence_store: EvidenceStore | None = None, event_store: EventStore | None = None):
        self.evidence_store = evidence_store or EvidenceStore()
        self.event_store = event_store or EventStore(evidence_store=self.evidence_store)

    def execute(self, profile_id: str, *, task_id: str = "", max_tasks: int = 1) -> list[ExecutionResult]:
        if isinstance(max_tasks, bool) or not isinstance(max_tasks, int) or max_tasks < 1:
            raise ProfileError("max_tasks 必须是大于 0 的整数")
        profile = load_profile(profile_id)
        validate_profile(profile)
        self._validate_executable(profile)
        adapter = create_source_adapter(profile)
        pending = [task for task in adapter.list_pending() if task.status == "pending"]
        if task_id:
            tasks = [task for task in pending if task.id == task_id]
            if tasks and getattr(tasks[0], "profile_id", None) != profile.id:
                raise ProfileError(f"任务 {task_id} 未绑定到 Profile {profile.id}")
        else:
            tasks = [task for task in pending if getattr(task, "profile_id", None) == profile.id]
        tasks = tasks[:max_tasks]
        if not tasks:
            raise ProfileError(f"Profile {profile_id} 没有待执行任务，或任务未绑定到该 Profile")
        return [self._execute_task(profile, adapter, task) for task in tasks]

    @staticmethod
    def _validate_executable(profile: Profile) -> None:
        if profile.id == "fixture-local":
            if profile.source != "local_queue" or profile.compiler != "simple" or profile.maker != "sample":
                raise ProfileError("fixture-local 的离线组件组合不匹配")
            if profile.delivery != "local_artifact" or profile.checkers != ("security",):
                raise ProfileError("fixture-local 的验证或交付组件不匹配")
            prohibited = ("allow_network", "allow_publish", "allow_deploy", "allow_model", "allow_git", "allow_ssh")
            if any(profile.policy.get(name, False) for name in prohibited):
                raise ProfileError("fixture-local 真实执行禁止网络、模型、Git、SSH、发布与部署")
            return
        if profile.id == "deepseek-github":
            if profile.source != "local_queue" or profile.compiler != "simple" or profile.maker != "deepseek":
                raise ProfileError("deepseek-github 的组件组合不匹配")
            if profile.delivery != "github_workflow" or profile.checkers != ("security", "e2e"):
                raise ProfileError("deepseek-github 的检查或交付组件不匹配")
            required = ("allow_network", "allow_model", "allow_git", "allow_publish", "allow_deploy")
            if not all(profile.policy.get(name) is True for name in required) or profile.policy.get("allow_ssh", False):
                raise ProfileError("deepseek-github 必须显式允许模型/GitHub Workflow，且禁止 SSH")
            return
        raise ProfileError("当前真实执行仅允许 fixture-local 或 deepseek-github Profile")

    def _execute_task(self, profile: Profile, adapter: Any, task: Any) -> ExecutionResult:
        plan = create_run_plan(profile, _task_dict(task)); persist_run_plan(plan)
        context = run_context(plan); sequence = 1; digests = {"input": plan.input_digest}
        versions = self._component_versions(profile)

        def record(stage: str, status: str, payload: Any, kind: str, details: dict[str, Any] | None = None) -> None:
            nonlocal sequence
            evidence = self.evidence_store.put_json(_redact_paths(payload), source=stage,
                                                    run_id=context.run_id, plan_digest=plan.digest, kind=kind)
            event = RunEvent(event_id=f"{context.run_id}-{sequence}", run_id=context.run_id,
                             sequence=sequence, occurred_at=_now(), stage=stage, status=status,
                             profile_ref=context.profile, task_id=task.id, plan_digest=plan.digest,
                             digests=dict(digests), component_versions=versions, attempt=context.attempt,
                             evidence=(evidence,), details=details or {})
            self.event_store.append(event); sequence += 1

        source_snapshot = {"task": {key: value for key, value in _task_dict(task).items() if key not in {"spec_text", "extra"}},
                           "input_digest": plan.input_digest}
        record("source", "passed", source_snapshot, "source-snapshot")
        adapter.report(task.id, "running", run_id=context.run_id, plan_digest=plan.digest)
        try:
            # 统一走确定性 SimpleCompiler，避免一次 Run 额外发起未纳入预算的 Spec 模型调用；
            # DeepSeek Maker 仍接收冻结的原始需求并执行真实代码生成。
            with _fixture_environment():
                from engine.compilers import load_compiler
                spec = load_compiler(profile.compiler).compile(context, task.spec_text or task.title)
            if not spec.validate(): raise ProfileError("Compiler 返回的 SpecBundle 未通过三件套校验")
            digests.update({"spec": _file_digest(spec.spec_path), "acceptance": _file_digest(spec.acceptance_path)})
            record("compiler", "passed", {"spec": digests["spec"], "acceptance": digests["acceptance"],
                                             "manifest": _file_digest(spec.manifest_path), "provenance": spec.provenance}, "spec-bundle")
        except Exception as exc:
            record("compiler", "failed", {"error": str(exc)[:500]}, "compiler-diagnostic", {"reason": str(exc)[:200]})
            return self._failed(adapter, task, context, plan.digest, sequence - 1, "failed", str(exc))

        try:
            artifacts = make_with_context(
                context, spec, maker_name=profile.maker, requirement=task.spec_text or task.title,
                timeout_seconds=profile.policy.get("timeout_seconds"),
                cost_limit_yuan=profile.policy.get("cost_limit_yuan"),
            )
            if not artifacts.digest: raise ProfileError("Maker 未返回 artifact digest")
            digests["artifact"] = artifacts.digest
            record("maker", "passed", {"artifact_digest": artifacts.digest, "files": sorted(artifacts.files),
                                          "meta": artifacts.meta}, "artifact-manifest")
        except Exception as exc:
            record("maker", "failed", {"error": str(exc)[:500]}, "maker-diagnostic", {"reason": str(exc)[:200]})
            return self._failed(adapter, task, context, plan.digest, sequence - 1, "failed", str(exc))
        try:
            report = check_with_context(context, artifacts, checker_names=list(profile.checkers))
            record("checker", report.status, report.to_dict(), "check-report", {"status": report.status})
        except Exception as exc:
            record("checker", "unavailable", {"error": str(exc)[:500]}, "checker-diagnostic", {"reason": str(exc)[:200]})
            return self._failed(adapter, task, context, plan.digest, sequence - 1, "unavailable", str(exc))
        if report.status != "passed":
            return self._failed(adapter, task, context, plan.digest, sequence - 1, report.status,
                                "确定性检查未通过；Delivery 未执行")
        try:
            from pipeline.delivery import load_delivery
            result = load_delivery(profile.delivery, **profile.delivery_config).deliver(context, artifacts)
            event_status = "passed" if result.status == "passed" else "failed"
            record("delivery", event_status, result.to_dict(), "delivery-result", {"status": result.status})
        except Exception as exc:
            record("delivery", "failed", {"error": str(exc)[:500]}, "delivery-diagnostic", {"reason": str(exc)[:200]})
            return self._failed(adapter, task, context, plan.digest, sequence - 1, "failed", str(exc))
        if result.status != "passed":
            return self._failed(adapter, task, context, plan.digest, sequence - 1, "failed", result.reason)
        adapter.report(task.id, "done", run_id=context.run_id, plan_digest=plan.digest,
                       artifact_digest=artifacts.digest, check_status=report.status, delivery=_redact_paths(result.to_dict()))
        return ExecutionResult(context.run_id, plan.digest, task.id, "passed", sequence - 1, delivery=_redact_paths(result.to_dict()))

    @staticmethod
    def _component_versions(profile: Profile) -> dict[str, str]:
        prefix = f"declared:{profile.ref}:"
        return {"source": prefix + profile.source, "compiler": prefix + profile.compiler,
                "maker": prefix + profile.maker, "checker": prefix + ",".join(profile.checkers),
                "delivery": prefix + profile.delivery}

    @staticmethod
    def _failed(adapter: Any, task: Any, context: Any, plan_digest: str, event_count: int, status: str, reason: str) -> ExecutionResult:
        adapter.report(task.id, "failed", run_id=context.run_id, plan_digest=plan_digest,
                       check_status=status, reason=reason[:300])
        return ExecutionResult(context.run_id, plan_digest, task.id, status, event_count, reason[:300])
