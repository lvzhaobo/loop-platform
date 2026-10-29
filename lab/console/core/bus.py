"""事件总线 —— 一份事件，三个去处：SSE / 历史回放 / 持久化。

所有实时页面（执行、长程、上下文、审计）都挂在这一个东西上。
设计约束：
  · 慢订阅者不能拖垮发布者（每个订阅者一个独立队列，满了就丢）
  · 必须有历史，否则前端刷新就断片
"""
import json
import queue
import threading
import time
from collections import deque
from pathlib import Path


class Bus:
    def __init__(self, history=2000, log_path: Path = None):
        self.seq = 0
        self.history = deque(maxlen=history)
        self.subs = []
        self.lock = threading.Lock()
        self.log_path = Path(log_path) if log_path else None
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def publish(self, ev: dict) -> dict:
        with self.lock:
            self.seq += 1
            ev = {**ev, "seq": self.seq, "ts": time.time()}
            self.history.append(ev)
            subs = list(self.subs)
        for q in subs:
            try:
                q.put_nowait(ev)
            except queue.Full:
                pass                      # 慢订阅者丢事件，不拖累别人
        if self.log_path:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        return ev

    def subscribe(self) -> queue.Queue:
        q = queue.Queue(maxsize=4000)
        with self.lock:
            self.subs.append(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            if q in self.subs:
                self.subs.remove(q)

    def replay(self, since: int = 0):
        with self.lock:
            return [e for e in self.history if e["seq"] > since]
