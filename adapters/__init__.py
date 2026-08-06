"""adapters — Source Adapter Port + Registry (Phase 2)。"""

from .registry import register, load_adapter, list_adapters
from .local_queue import LocalQueueAdapter

__all__ = [
    "register", "load_adapter", "list_adapters",
    "LocalQueueAdapter",
]