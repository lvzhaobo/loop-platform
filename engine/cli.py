"""Loop 平台 Profile CLI：安全预览、受控离线执行与只读重放。"""
from __future__ import annotations

import argparse
import json
from typing import Any

from engine.core.profiles import (ProfileError, create_run_plan,
                                  create_source_adapter, list_profiles,
                                  load_profile, validate_profile)
from engine.core.observability import EventError
from engine.core.evidence_store import EvidenceStore
from engine.core.event_store import EventStore
from engine.core.run_executor import ProfileRunExecutor


def _task_dict(task: Any) -> dict[str, Any]:
    return {
        "id": task.id, "title": task.title, "source": task.source,
        "case": task.case, "priority": task.priority,
        "spec_text": task.spec_text or "", "extra": task.extra,
    }


def _select_task(profile_id: str, task_id: str = "") -> dict[str, Any]:
    profile = load_profile(profile_id)
    validate_profile(profile)
    tasks = create_source_adapter(profile).list_pending()
    if task_id:
        tasks = [task for task in tasks if task.id == task_id]
    if not tasks:
        selector = f" task_id={task_id}" if task_id else ""
        raise ProfileError(f"Profile {profile_id} 没有待执行任务{selector}")
    return _task_dict(tasks[0])


def _json(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def cmd_profile_list(_: argparse.Namespace) -> int:
    _json({"ok": True, "profiles": list_profiles()})
    return 0


def cmd_profile_validate(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile_id)
    validate_profile(profile)
    _json({"ok": True, "profile": profile.to_dict(), "ref": profile.ref})
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    task = _select_task(args.profile_id, args.task_id)
    plan = create_run_plan(load_profile(args.profile_id), task)
    _json({"ok": True, "dry_run": True, "plan": plan.to_dict()})
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    results = ProfileRunExecutor().execute(args.profile_id, task_id=args.task_id, max_tasks=args.max_tasks)
    payload = {"ok": all(item.status == "passed" for item in results),
               "profile_id": args.profile_id, "runs": [item.to_dict() for item in results]}
    _json(payload)
    return 0 if payload["ok"] else 1


def cmd_replay(args: argparse.Namespace) -> int:
    replay = EventStore(evidence_store=EvidenceStore()).replay(args.run_id)
    _json({"ok": True, "replay": replay})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m engine.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    profile = commands.add_parser("profile", help="查看或验证 Profile")
    profile_commands = profile.add_subparsers(dest="profile_command", required=True)
    profile_list = profile_commands.add_parser("list", help="列出 Profile")
    profile_list.set_defaults(handler=cmd_profile_list)
    profile_validate = profile_commands.add_parser("validate", help="验证 Profile")
    profile_validate.add_argument("profile_id")
    profile_validate.set_defaults(handler=cmd_profile_validate)

    plan = commands.add_parser("plan", help="创建不落盘的 Run Plan 预览")
    plan.add_argument("--profile", dest="profile_id", required=True)
    plan.add_argument("--task-id", default="")
    plan.add_argument("--dry-run", action="store_true", required=True)
    plan.set_defaults(handler=cmd_plan)

    run = commands.add_parser("run", help="执行受控的离线 fixture-local Profile")
    run.add_argument("--profile", dest="profile_id", required=True)
    run.add_argument("--task-id", default="")
    run.add_argument("--max-tasks", type=int, default=1)
    run.set_defaults(handler=cmd_run)

    replay = commands.add_parser("replay", help="只读校验并重放一个 Run 的事件与证据")
    replay.add_argument("--run", dest="run_id", required=True)
    replay.set_defaults(handler=cmd_replay)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (ProfileError, EventError) as exc:
        _json({"ok": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
