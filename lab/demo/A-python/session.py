"""仅追加事件日志 —— 模型可见即已记录。

为什么不做成内存列表：因为回放、审计、成本核算、断点续跑都要读它。
"""
import json, time
from pathlib import Path

class Session:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.seq = 0
        if self.path.exists():
            self.seq = sum(1 for _ in self.path.open(encoding="utf-8"))

    def append(self, kind: str, **data):
        self.seq += 1
        ev = {"seq": self.seq, "ts": time.time(), "type": kind, **data}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        return ev

    def replay(self):
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.open(encoding="utf-8") if l.strip()]
