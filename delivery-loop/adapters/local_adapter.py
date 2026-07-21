"""local 适配器:以 backlog.jsonl 为需求池(每行一个任务对象)。

零依赖、零密钥,用于跑通「需求池 → 引擎 → 回写」整条闭环。
回写方式:原地重写 backlog.jsonl,更新对应任务的状态与结果字段。
"""
from __future__ import annotations

import json
import os
from typing import Any

from .base import Adapter, Task, apply_report

# Task 数据类已声明的字段(其余字段收进 extra 透传,回写时再展开)
_KNOWN = {"id", "title", "source", "status", "priority", "case", "spec_text"}


class LocalAdapter(Adapter):
    name = "local"

    def __init__(self, path: str):
        self.path = path

    # ---- 读 ----
    def _read_all(self) -> list[dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        rows: list[dict[str, Any]] = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def _write_all(self, rows: list[dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def list_pending(self) -> list[Task]:
        tasks: list[Task] = []
        for r in self._read_all():
            if r.get("status", "pending") != "pending":
                continue
            tasks.append(Task(
                id=str(r["id"]),
                title=r.get("title", r["id"]),
                source="local",
                status="pending",
                priority=int(r.get("priority", 99)),
                case=r.get("case"),
                spec_text=r.get("spec_text"),
                extra={k: v for k, v in r.items() if k not in _KNOWN},
            ))
        tasks.sort(key=lambda t: t.priority)
        return tasks

    # ---- 写回 ----
    def report(self, task_id: str, status: str, **fields: Any) -> None:
        rows = self._read_all()
        for r in rows:
            if str(r["id"]) == str(task_id):
                apply_report(r, status, fields)
                break
        self._write_all(rows)
