"""受 Profile 与证据合同约束的离线参考执行器。"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
from typing import Any

from adapters.base import Task
from engine.core.compat import check_with_context, make_with_context
from engine.core.contracts import ArtifactBundle
from engine.core.evidence_store import EvidenceStore
from engine.core.event_store import EventStore
from engine.core.observability import RunEvent
from engine.core.profiles import (Profile, ProfileError, RunPlan, create_run_plan,
                                  create_source_adapter, get_run_plan, load_profile,
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
        self.validate_executable(profile)
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

    def execute_plan(self, plan_id: str) -> ExecutionResult:
        """Execute exactly one persisted, reviewed Plan; never rebuild it from mutable inputs."""
        raw_plan = get_run_plan(plan_id)
        plan = RunPlan(**raw_plan)
        profile_data = dict(plan.profile)
        profile_data.pop("ref", None)
        profile = Profile.from_dict(profile_data)
        validate_profile(profile)
        self.validate_executable(profile)
        adapter = create_source_adapter(profile)
        tasks = [task for task in adapter.list_pending()
                 if task.id == plan.task["id"] and task.status == "pending" and task.profile_id == profile.id]
        if not tasks:
            raise ProfileError(f"冻结 Run Plan {plan_id} 对应的任务已不再处于待执行状态")
        task = tasks[0]
        if _task_dict(task) != plan.task:
            raise ProfileError(f"冻结 Run Plan {plan_id} 的任务快照已变化，必须重新审阅")
        return self._execute_task(profile, adapter, task, plan=plan)

    def retry_delivery(self, run_id: str) -> ExecutionResult:
        """只重试已失败 Run 的 Delivery；复用冻结 Plan 与制品，绝不重跑模型或 Checker。"""
        raw_plan = get_run_plan(run_id)
        plan = RunPlan(**raw_plan)
        profile_data = dict(plan.profile)
        profile_data.pop("ref", None)
        profile = Profile.from_dict(profile_data)
        validate_profile(profile)
        self.validate_executable(profile)
        events = self.event_store.read(run_id, verify_evidence=True)
        if not events or events[-1].stage != "delivery" or events[-1].status != "failed":
            raise ProfileError("仅允许重试最后阶段为 failed 的 Delivery")
        artifact_digest = events[-1].digests.get("artifact", "")
        output_dir = PlatformPaths.OUTPUT_DIR / f"maker-{run_id}"
        files = sorted(str(path.relative_to(output_dir)) for path in output_dir.rglob("*") if path.is_file())
        hasher = hashlib.sha256()
        for relative in files:
            hasher.update((output_dir / relative).read_bytes())
        if not artifact_digest or hasher.hexdigest() != artifact_digest:
            raise ProfileError("冻结制品摘要不匹配，拒绝重试 Delivery")
        context = run_context(plan)
        task = Task(id=str(plan.task["id"]), title=str(plan.task.get("title", "")),
                    source=str(plan.task.get("source", "local")), case=plan.task.get("case"),
                    priority=plan.task.get("priority", 99), spec_text=plan.task.get("spec_text"),
                    extra=plan.task.get("extra", {}), profile_id=profile.id)
        adapter = create_source_adapter(profile)
        artifacts = ArtifactBundle(str(output_dir), files, artifact_digest)
        try:
            from pipeline.delivery import load_delivery
            result = load_delivery(profile.delivery, **profile.delivery_config).deliver(context, artifacts)
            status = "passed" if result.status == "passed" else "failed"
        except Exception as exc:
            result, status = None, "failed"
            reason = str(exc)[:300]
        payload = result.to_dict() if result is not None else {"error": reason}
        evidence = self.evidence_store.put_json(_redact_paths(payload), source="delivery", run_id=run_id,
                                                plan_digest=plan.digest, kind=f"delivery-retry-{len(events) + 1}")
        self.event_store.append(RunEvent(
            event_id=f"{run_id}-{len(events) + 1}", run_id=run_id, sequence=len(events) + 1,
            occurred_at=_now(), stage="delivery", status=status, profile_ref=context.profile, task_id=task.id,
            plan_digest=plan.digest, digests=dict(events[-1].digests),
            component_versions=events[-1].component_versions, attempt=context.attempt, evidence=(evidence,),
            details={"retry": True, "status": status},
        ))
        if result is None or result.status != "passed":
            failure = result.reason if result is not None else reason
            adapter.report(task.id, "failed", run_id=run_id, plan_digest=plan.digest, check_status="failed", reason=failure[:300])
            return ExecutionResult(run_id, plan.digest, task.id, "failed", len(events) + 1, failure[:300])
        adapter.report(task.id, "done", run_id=run_id, plan_digest=plan.digest, artifact_digest=artifact_digest,
                       check_status="passed", delivery=_redact_paths(result.to_dict()))
        return ExecutionResult(run_id, plan.digest, task.id, "passed", len(events) + 1,
                               delivery=_redact_paths(result.to_dict()))

    @staticmethod
    def validate_executable(profile: Profile) -> None:
        """Allow catalog-backed local and DeepSeek delivery profiles; execution still requires UI confirmation."""
        if profile.source != "local_queue":
            raise ProfileError("当前执行仅支持 local_queue Source")
        if profile.compiler not in {"simple", "mumuspec"}:
            raise ProfileError("当前执行仅支持 simple 或 mumuspec Compiler")
        if not profile.checkers or not set(profile.checkers).issubset({"security", "runtime", "e2e", "pages"}):
            raise ProfileError("当前执行仅支持 security、runtime、e2e、pages Checker")
        if profile.id == "fixture-local":
            expected = (profile.compiler == "simple" and profile.maker == "sample" and
                        profile.checkers == ("security",) and profile.delivery == "local_artifact")
            prohibited = ("allow_network", "allow_publish", "allow_deploy", "allow_model", "allow_git", "allow_ssh")
            if not expected or any(profile.policy.get(name, False) for name in prohibited):
                raise ProfileError("fixture-local 必须保持离线安全基线组合")
            return
        if profile.delivery == "local_artifact":
            if profile.maker == "sample":
                prohibited = ("allow_network", "allow_model", "allow_git", "allow_ssh", "allow_publish", "allow_deploy")
                if any(profile.policy.get(name, False) for name in prohibited):
                    raise ProfileError("Sample Maker 本地执行不允许外部权限")
                return
            if profile.maker == "deepseek":
                required, prohibited = ("allow_network", "allow_model"), ("allow_git", "allow_ssh", "allow_publish", "allow_deploy")
                if not all(profile.policy.get(name) is True for name in required) or any(profile.policy.get(name, False) for name in prohibited):
                    raise ProfileError("DeepSeek 本地执行必须仅允许网络和模型，禁止 Git、SSH、发布与部署")
                return
        if profile.delivery == "github_workflow":
            required = ("allow_network", "allow_model", "allow_git", "allow_publish", "allow_deploy")
            if profile.maker != "deepseek" or not {"security", "e2e"}.issubset(profile.checkers):
                raise ProfileError("GitHub Workflow 执行必须使用 DeepSeek、Security 与 E2E")
            if not all(profile.policy.get(name) is True for name in required) or profile.policy.get("allow_ssh", False):
                raise ProfileError("GitHub Workflow 必须显式允许模型/Git/发布/部署，且禁止 SSH")
            return
        raise ProfileError("当前 Profile 组合不能执行；请选择本地制品或 GitHub Workflow 交付")

    def _execute_task(self, profile: Profile, adapter: Any, task: Any, *, plan: RunPlan | None = None) -> ExecutionResult:
        if plan is None:
            plan = create_run_plan(profile, _task_dict(task))
            persist_run_plan(plan)
        elif plan.profile.get("ref") != profile.ref or plan.task != _task_dict(task):
            raise ProfileError("冻结 Run Plan 与当前 Profile 或任务快照不一致")
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
            report = check_with_context(context, artifacts, checker_names=list(profile.checkers),
                                        acceptance_path=spec.acceptance_path)
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
