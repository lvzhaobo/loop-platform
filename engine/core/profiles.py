"""Phase 3 Profile 与冻结 Run Plan。

Profile 是版本化的可复用组合；Run Plan 是某一任务冻结后的权威快照。
本模块只管理本地 JSON 元数据，不读取全局 config.env 伪造任务级配置。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.core.contracts import RunContext
from engine.core.paths import PlatformPaths


class ProfileError(ValueError):
    """Profile、组件解析或 Plan 持久化不符合合同。"""


_PROFILE_FIELDS = frozenset({
    "id", "version", "description", "source", "compiler", "maker",
    "checkers", "delivery", "delivery_config", "policy",
})
_SOURCE_FIELDS = frozenset({"name", "config"})
_POLICY_REQUIRED = frozenset({
    "max_attempts", "allow_network", "allow_publish", "allow_deploy", "on_unavailable",
})
_POLICY_FIELDS = _POLICY_REQUIRED | frozenset({
    "allow_model", "allow_git", "allow_ssh", "timeout_seconds",
    "cost_limit_yuan", "evidence_required",
})


def _reject_unknown(value: dict[str, Any], allowed: frozenset[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ProfileError(f"{label} 包含未知字段: {', '.join(unknown)}")


def _canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class Profile:
    id: str
    version: int
    source: str
    source_config: dict[str, Any]
    compiler: str
    maker: str
    checkers: tuple[str, ...]
    delivery: str
    delivery_config: dict[str, Any]
    policy: dict[str, Any]
    description: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Profile":
        if not isinstance(value, dict):
            raise ProfileError("Profile 必须是对象")
        _reject_unknown(value, _PROFILE_FIELDS, "Profile")

        source = value.get("source", {})
        if not isinstance(source, dict):
            raise ProfileError("source 必须是 {name, config} 对象")
        _reject_unknown(source, _SOURCE_FIELDS, "source")
        source_config = source.get("config") or {}
        if not isinstance(source_config, dict):
            raise ProfileError("source.config 必须是对象")

        policy = value.get("policy") or {}
        if not isinstance(policy, dict):
            raise ProfileError("policy 必须是对象")
        _reject_unknown(policy, _POLICY_FIELDS, "policy")
        delivery_config = value.get("delivery_config") or {}
        if not isinstance(delivery_config, dict):
            raise ProfileError("delivery_config 必须是对象")

        profile = cls(
            id=str(value.get("id", "")).strip(),
            version=value.get("version"),
            source=str(source.get("name", "")).strip(),
            source_config=dict(source_config),
            compiler=str(value.get("compiler", "")).strip(),
            maker=str(value.get("maker", "")).strip(),
            checkers=tuple(value.get("checkers") or ()),
            delivery=str(value.get("delivery", "")).strip(),
            delivery_config=dict(delivery_config),
            policy=dict(policy),
            description=str(value.get("description", "")).strip(),
        )
        required = (profile.id, profile.source, profile.compiler, profile.maker, profile.delivery)
        if not all(required) or not isinstance(profile.version, int) or not profile.checkers:
            raise ProfileError("Profile 必须包含 id、整数 version、source、compiler、maker、checkers、delivery")
        return profile

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "version": self.version, "description": self.description,
            "source": {"name": self.source, "config": self.source_config},
            "compiler": self.compiler, "maker": self.maker,
            "checkers": list(self.checkers), "delivery": self.delivery,
            "delivery_config": self.delivery_config, "policy": self.policy,
        }


@dataclass(frozen=True)
class RunPlan:
    id: str
    run_id: str
    created_at: str
    profile: dict[str, Any]
    task: dict[str, Any]
    components: dict[str, Any]
    policy: dict[str, Any]
    input_digest: str
    digest: str
    status: str = "planned"
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "id": self.id, "run_id": self.run_id,
            "created_at": self.created_at, "status": self.status, "profile": self.profile,
            "task": self.task, "components": self.components, "policy": self.policy,
            "input_digest": self.input_digest, "digest": self.digest,
        }


def _profile_path(profile_id: str) -> Path:
    if not profile_id or "/" in profile_id or "\\" in profile_id:
        raise ProfileError("Profile id 非法")
    return PlatformPaths.PROFILES_DIR / f"{profile_id}.json"


def load_profile(profile_id: str) -> Profile:
    path = _profile_path(profile_id)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProfileError(f"Profile 不存在: {profile_id}") from exc
    except json.JSONDecodeError as exc:
        raise ProfileError(f"Profile JSON 无效: {path}") from exc
    profile = Profile.from_dict(raw)
    if profile.id != profile_id:
        raise ProfileError(f"Profile 文件名与 id 不一致: {path.name} != {profile.id}")
    return profile


def list_profiles() -> list[dict[str, Any]]:
    if not PlatformPaths.PROFILES_DIR.is_dir():
        return []
    summaries = []
    for path in sorted(PlatformPaths.PROFILES_DIR.glob("*.json")):
        try:
            profile = load_profile(path.stem)
            validate_profile(profile)
            summaries.append({
                "id": profile.id, "version": profile.version, "ref": profile.ref,
                "description": profile.description, "source": profile.source,
                "compiler": profile.compiler, "maker": profile.maker,
                "checkers": list(profile.checkers), "delivery": profile.delivery,
                "policy": profile.policy, "valid": True,
            })
        except ProfileError as exc:
            summaries.append({"id": path.stem, "valid": False, "error": str(exc)})
    return summaries


def persist_profile(profile: Profile) -> Path:
    """Register a new executable Profile once; never overwrite an existing id."""
    validate_profile(profile)
    target = _profile_path(profile.id)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ProfileError(f"Profile 已存在，拒绝覆盖: {profile.id}；请使用新的 id")
    target.write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def validate_profile(profile: Profile) -> None:
    """在任何工作开始前验证所有组件与无副作用默认策略。"""
    from adapters.registry import load_adapter
    from engine.compilers import load_compiler
    from engine.makers import load_maker
    from engine.checkers import load_checker
    from pipeline.delivery import load_delivery

    config = dict(profile.source_config)
    for key in ("backlog_path", "state_path"):
        if config.get(key):
            config[key] = str(PlatformPaths.resolve(config[key]))
    try:
        load_adapter(profile.source, **config)
        load_compiler(profile.compiler)
        load_maker(profile.maker)
        for checker in profile.checkers:
            load_checker(checker)
        load_delivery(profile.delivery, **profile.delivery_config)
    except (TypeError, ValueError) as exc:
        raise ProfileError(str(exc)) from exc

    for key in ("allow_network", "allow_publish", "allow_deploy"):
        if key not in profile.policy or not isinstance(profile.policy[key], bool):
            raise ProfileError(f"policy.{key} 必须是布尔值")
    for key in ("allow_model", "allow_git", "allow_ssh"):
        if key in profile.policy and not isinstance(profile.policy[key], bool):
            raise ProfileError(f"policy.{key} 必须是布尔值")

    max_attempts = profile.policy.get("max_attempts")
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
        raise ProfileError("policy.max_attempts 必须是大于 0 的整数")
    if profile.policy.get("on_unavailable") not in {"block", "review_required", "continue"}:
        raise ProfileError("policy.on_unavailable 必须是 block、review_required 或 continue")
    if "timeout_seconds" in profile.policy:
        timeout = profile.policy["timeout_seconds"]
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
            raise ProfileError("policy.timeout_seconds 必须是大于 0 的整数")
    if "cost_limit_yuan" in profile.policy:
        cost = profile.policy["cost_limit_yuan"]
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
            raise ProfileError("policy.cost_limit_yuan 必须是非负数字")
    if "evidence_required" in profile.policy:
        evidence = profile.policy["evidence_required"]
        if not isinstance(evidence, list) or not all(isinstance(item, str) and item for item in evidence):
            raise ProfileError("policy.evidence_required 必须是非空字符串列表")

    if profile.delivery == "local_artifact":
        if profile.delivery_config:
            raise ProfileError("local_artifact 不接受 delivery_config")
        if profile.policy["allow_deploy"] or profile.policy["allow_publish"]:
            raise ProfileError("local_artifact 不允许发布或部署")
    elif profile.delivery == "github_workflow":
        required = ("allow_network", "allow_model", "allow_git", "allow_publish", "allow_deploy")
        if not all(profile.policy.get(key) is True for key in required):
            raise ProfileError("github_workflow 必须显式允许网络、模型、Git、发布和 Workflow 部署")
        if profile.policy.get("allow_ssh", False):
            raise ProfileError("github_workflow 不允许 SSH；ECS 必须由仓库 Workflow 接管")
    else:
        raise ProfileError("当前仅允许 local_artifact 或 github_workflow Delivery")


def create_source_adapter(profile: Profile):
    """将 Profile 的受控配置注入 Source Adapter。"""
    from adapters.registry import load_adapter

    config = dict(profile.source_config)
    for key in ("backlog_path", "state_path"):
        if config.get(key):
            config[key] = str(PlatformPaths.resolve(config[key]))
    return load_adapter(profile.source, **config)


def create_run_plan(profile: Profile, task: dict[str, Any]) -> RunPlan:
    validate_profile(profile)
    task_snapshot = {
        "id": str(task.get("id", "")).strip(),
        "title": str(task.get("title", "")).strip(),
        "source": str(task.get("source", "")).strip(),
        "case": task.get("case"),
        "priority": task.get("priority", 99),
        "spec_text": str(task.get("spec_text", "")),
        "extra": task.get("extra", {}),
    }
    if not task_snapshot["id"]:
        raise ProfileError("Run Plan 必须绑定 task.id")
    input_digest = _canonical_digest({
        **task_snapshot, "spec_text": task.get("spec_text", ""), "extra": task.get("extra", {}),
    })
    components = {
        "source": profile.source, "compiler": profile.compiler, "maker": profile.maker,
        "checkers": list(profile.checkers), "delivery": profile.delivery,
    }
    seed = _canonical_digest({"profile": profile.to_dict(), "task": task_snapshot, "input": input_digest})
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"run-{stamp}-{seed[:10]}"
    content = {
        "schema_version": 1, "id": run_id, "run_id": run_id, "created_at": _now(),
        "status": "planned", "profile": {**profile.to_dict(), "ref": profile.ref},
        "task": task_snapshot, "components": components, "policy": profile.policy,
        "input_digest": input_digest,
    }
    return RunPlan(**content, digest=_canonical_digest(content))


def persist_run_plan(plan: RunPlan) -> Path:
    """只创建、不覆盖：冻结后的 Plan 不可被后续配置修改。"""
    target = PlatformPaths.RUN_PLANS_DIR / f"{plan.id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ProfileError(f"Run Plan 已存在，拒绝覆盖: {plan.id}")
    target.write_text(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def get_run_plan(plan_id: str) -> dict[str, Any]:
    if not plan_id or "/" in plan_id or "\\" in plan_id:
        raise ProfileError("Run Plan id 非法")
    path = PlatformPaths.RUN_PLANS_DIR / f"{plan_id}.json"
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProfileError(f"Run Plan 不存在: {plan_id}") from exc
    except json.JSONDecodeError as exc:
        raise ProfileError(f"Run Plan JSON 无效: {plan_id}") from exc
    digest = plan.get("digest")
    content = {key: value for key, value in plan.items() if key != "digest"}
    if not isinstance(digest, str) or _canonical_digest(content) != digest:
        raise ProfileError(f"Run Plan digest 校验失败: {plan_id}")
    return plan


def _run_claim_path(plan_id: str) -> Path:
    if not plan_id or "/" in plan_id or "\\" in plan_id:
        raise ProfileError("Run Plan id 非法")
    return PlatformPaths.DATA_DIR / "run_execution_claims" / f"{plan_id}.json"


def claim_run_plan(plan_id: str) -> dict[str, str]:
    """Atomically reserve one reviewed Plan before any asynchronous execution starts."""
    plan = get_run_plan(plan_id)
    target = _run_claim_path(plan_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    claim = {
        "plan_id": plan_id,
        "run_id": str(plan["run_id"]),
        "plan_digest": str(plan["digest"]),
        "state": "queued",
        "claimed_at": _now(),
        "updated_at": _now(),
    }
    try:
        with target.open("x", encoding="utf-8") as handle:
            json.dump(claim, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
    except FileExistsError as exc:
        state = get_run_execution_claim(plan_id).get("state", "unknown")
        raise ProfileError(f"Run Plan 已被领取（状态：{state}）；请查看既有 Run 或重新冻结 Plan") from exc
    return claim


def get_run_execution_claim(plan_id: str) -> dict[str, str]:
    """Read a minimal execution state; this is queue metadata, not Run evidence."""
    try:
        value = json.loads(_run_claim_path(plan_id).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"state": "planned"}
    except (OSError, ValueError, TypeError) as exc:
        raise ProfileError("Run 执行领取记录损坏") from exc
    if not isinstance(value, dict) or str(value.get("plan_id", "")) != plan_id:
        raise ProfileError("Run 执行领取记录无效")
    return {key: str(value[key]) for key in ("plan_id", "run_id", "plan_digest", "state", "claimed_at", "updated_at", "reason") if key in value}


def update_run_execution_claim(plan_id: str, state: str, *, reason: str = "") -> dict[str, str]:
    if state not in {"running", "passed", "failed", "unavailable", "indeterminate", "skipped"}:
        raise ProfileError("Run 执行状态非法")
    target = _run_claim_path(plan_id)
    claim = get_run_execution_claim(plan_id)
    if claim.get("state") == "planned":
        raise ProfileError("Run Plan 尚未领取")
    claim.update({"state": state, "updated_at": _now()})
    if reason:
        claim["reason"] = reason[:200]
    target.write_text(json.dumps(claim, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return claim


def list_run_plans(limit: int = 50) -> list[dict[str, Any]]:
    if not PlatformPaths.RUN_PLANS_DIR.is_dir():
        return []
    plans = []
    for path in sorted(PlatformPaths.RUN_PLANS_DIR.glob("*.json"), reverse=True)[:limit]:
        try:
            plan = get_run_plan(path.stem)
            plans.append({
                "id": plan.get("id"), "run_id": plan.get("run_id"),
                "created_at": plan.get("created_at"), "status": plan.get("status"),
                "digest": plan.get("digest"), "task": plan.get("task", {}),
                "profile": {"ref": plan.get("profile", {}).get("ref", "")},
                "components": plan.get("components", {}), "policy": plan.get("policy", {}),
            })
        except (OSError, json.JSONDecodeError, ProfileError):
            continue
    return plans


def run_context(plan: RunPlan) -> RunContext:
    return RunContext(
        run_id=plan.run_id,
        profile=str(plan.profile["ref"]),
        workspace=str(PlatformPaths.ROOT),
        task=str(plan.task.get("case") or plan.task["id"]),
        hashes={"input": plan.input_digest, "plan": plan.digest},
        started_at=plan.created_at,
        component_versions={key: str(value) for key, value in plan.components.items() if key != "checkers"},
    )
