"""LocalQueue Adapter — 从本地 data/backlog.json 读取任务 (Phase 2)。

替代硬编码的 orchestrator.py 直接构造。Profile 注入后，orchestrator 仅调 load_adapter(profile.adapter)。
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from adapters.base import Adapter, Task
from adapters.registry import register


@register("local_queue")
class LocalQueueAdapter(Adapter):
    """从本地数据读取任务队列。"""

    source = "local"

    def __init__(self, backlog_path: str = ""):
        self.backlog_path = backlog_path or os.path.join("data", "backlog.json")

    def list_pending(self) -> list[Task]:
        """从 backlog.json 读取 pending 任务。"""
        if not os.path.isfile(self.backlog_path):
            return []

        try:
            with open(self.backlog_path, encoding="utf-8") as f:
                backlog = json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

        tasks = []
        items = backlog if isinstance(backlog, list) else backlog.get("items", [])
        for item in items:
            if isinstance(item, str):
                # 纯文本需求
                from hashlib import sha256
                req_hash = sha256(item.encode()).hexdigest()[:8]
                tasks.append(Task(
                    id=f"local-{req_hash}",
                    title=item[:80],
                    source="local",
                    status="pending",
                    spec_text=item,
                ))
            elif isinstance(item, dict):
                tasks.append(Task(
                    id=item.get("id", f"local-{item.get('case', 'unknown')}"),
                    title=item.get("title", item.get("case", "")),
                    source="local",
                    status=item.get("status", "pending"),
                    case=item.get("case"),
                    spec_text=item.get("text"),
                    priority=item.get("priority", 99),
                ))
        return tasks

    def report(self, task_id: str, status: str, **kwargs):
        """回写任务状态（本地队列仅标记，不持久化回写）。"""
        # Phase 2: 本地队列暂不回写，仅由 orchestrator 记录到 runs.jsonl
        pass
