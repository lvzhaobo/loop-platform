"""delivery-loop 适配器包。"""
import os

from .base import Adapter, Task
from .feishu_adapter import FeishuAdapter
from .local_adapter import LocalAdapter

__all__ = ["Adapter", "Task", "LocalAdapter", "FeishuAdapter"]


def load_adapter(source: str, *, backlog_file: str) -> Adapter:
    """按 HARNESS_BACKLOG_SOURCE 选择适配器。新增来源在此登记即可。"""
    if source == "local":
        return LocalAdapter(backlog_file)
    if source == "feishu":
        docs = os.environ.get("HARNESS_FEISHU_DOCS", "delivery-loop/backlog/feishu_docs.json")
        state = os.environ.get("HARNESS_FEISHU_STATE", "delivery-loop/backlog/feishu_state.json")
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return FeishuAdapter(os.path.join(root, docs), os.path.join(root, state))
    raise SystemExit(
        f"[delivery-loop] 暂不支持来源 '{source}'。"
        "当前已实现:local、feishu。后续可扩展 github/jira/teambition/bitable。"
    )
