"""loop/pipeline 适配器契约。

编排层只认这里定义的归一化 Task 与 Adapter 接口,与具体来源(local/jira/teambition/
zentao/github)彻底解耦。新增来源=实现一个 Adapter 子类,主循环一行不改。
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Task:
    """归一化任务:所有来源翻译到此结构后进入 Loop。"""
    id: str                       # 外部唯一 id(用于回写与去重)
    title: str                    # 人读标题
    source: str = "local"         # 来源标记
    status: str = "pending"       # 内部状态机:pending/running/done/failed
    priority: int = 99            # 数字越小越先做
    case: str | None = None       # 映射到 loop/engine 的用例名(结构化任务直接给)
    spec_text: str | None = None  # 自由文本需求(需 spec 编译,当前最小版暂不启用)
    profile_id: str | None = None  # 允许执行此任务的 Profile id；未绑定任务不能进入受控 run
    extra: dict[str, Any] = field(default_factory=dict)  # 来源特有字段透传


# 互斥的「结局说明」字段:每次 report 都完整描述本次结局,故若本次未再提供,
# 应清掉上一状态残留(否则 done 会残留 failed 的 reason、fetched 的 note,UI 自相矛盾)。
_OUTCOME_FIELDS = ("reason", "note")


def apply_report(rec: dict[str, Any], status: str, fields: dict[str, Any]) -> None:
    """把一次 report 归并进状态记录:写新状态 → 清掉本次未提供的互斥结局说明字段 → 合并本次字段。"""
    rec["status"] = status
    for k in _OUTCOME_FIELDS:
        if k not in fields:
            rec.pop(k, None)
    rec.update(fields)


class Adapter(abc.ABC):
    """来源适配器:负责「读取待办」与「回写结果」两个方向。"""

    name = "abstract"

    @abc.abstractmethod
    def list_pending(self) -> list[Task]:
        """拉取 status=pending 的任务,按 priority 升序返回。"""

    @abc.abstractmethod
    def report(self, task_id: str, status: str, **fields: Any) -> None:
        """把运行结果回写到来源(状态 + 产物目录/PR 链接/失败原因等)。"""
