"""LocalQueue Adapter — 从本地 data/backlog.json 读取任务 (Phase 2)。

替代硬编码的 orchestrator.py 直接构造。Profile 注入后，orchestrator 仅调 load_adapter(profile.adapter)。
"""

from __future__ import annotations

import json
import os
from typing import Any

from adapters.base import Adapter, Task
from adapters.registry import register


@register("local_queue")
class LocalQueueAdapter(Adapter):
    """读取统一的 ``data/backlog.json`` 或离线 fixture，并将回报写入可选 state 文件。"""

    source = "local"

    def __init__(self, backlog_path: str = "", state_path: str = ""):
        self.backlog_path = backlog_path or os.path.join("data", "backlog.json")
        self.state_path = state_path
        self.reports: list[dict[str, Any]] = []

    def list_pending(self) -> list[Task]:
        if not os.path.isfile(self.backlog_path):
            return []
        try:
            with open(self.backlog_path, encoding="utf-8") as handle:
                backlog = json.load(handle)
        except (json.JSONDecodeError, OSError):
            return []
        states = self._read_state()
        if isinstance(backlog, list):
            items = backlog
        elif isinstance(backlog, dict):
            items = backlog.get("items", backlog.get("docs", []))
        else:
            items = []
        tasks = []
        for item in items:
            task = self._task(item, states)
            if task is not None:
                tasks.append(task)
        return sorted(tasks, key=lambda task: (task.priority, task.id))

    @staticmethod
    def _task(item: Any, states: dict[str, Any]) -> Task | None:
        if isinstance(item, str):
            from hashlib import sha256
            task_id = f"local-{sha256(item.encode()).hexdigest()[:8]}"
            return Task(id=task_id, title=item[:80], source="local", status="pending", spec_text=item)
        if not isinstance(item, dict):
            return None
        task_id = str(item.get("id", f"local-{item.get('case', 'unknown')}")).strip()
        if not task_id:
            return None
        state = states.get(task_id, {}) if isinstance(states.get(task_id, {}), dict) else {}
        return Task(
            id=task_id,
            title=str(item.get("title", item.get("case", ""))),
            source="local",
            status=str(state.get("status", item.get("status", "pending"))),
            case=item.get("case"),
            spec_text=item.get("text", item.get("spec_text")),
            priority=item.get("priority", 99),
            profile_id=str(item.get("profile_id", "")).strip() or None,
            extra={key: value for key, value in item.items()
                   if key not in {"id", "title", "status", "case", "text", "spec_text", "priority", "profile_id"}},
        )

    def report(self, task_id: str, status: str, **kwargs: Any) -> None:
        if not task_id:
            raise ValueError("task_id 不能为空")
        if status not in {"running", "done", "failed"}:
            raise ValueError(f"本地 Adapter 不支持的回报状态: {status}")
        report = {"task_id": task_id, "status": status, "fields": dict(kwargs)}
        self.reports.append(report)
        if self.state_path:
            state = self._read_state()
            record = dict(state.get(task_id, {}))
            record.update(report["fields"])
            record["status"] = status
            state[task_id] = record
            directory = os.path.dirname(self.state_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            temporary = f"{self.state_path}.tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temporary, self.state_path)

    def _read_state(self) -> dict[str, Any]:
        if not self.state_path or not os.path.isfile(self.state_path):
            return {}
        try:
            with open(self.state_path, encoding="utf-8") as handle:
                value = json.load(handle)
            return value if isinstance(value, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
