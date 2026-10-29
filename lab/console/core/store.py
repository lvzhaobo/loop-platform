"""极简 JSON 存储 —— 每个集合一个文件。

为什么不上数据库：这套东西要让客户能读懂、能改、能 git 管。
一个 data/reqs.json 胜过一张没人敢动的表。
"""
import json
import threading
import time
from pathlib import Path


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self._cache = {}

    def _path(self, coll): return self.root / f"{coll}.json"

    def _load(self, coll):
        with self.lock:
            if coll in self._cache:
                return self._cache[coll]
            p = self._path(coll)
            data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
            self._cache[coll] = data
            return data

    def _save(self, coll, data):
        with self.lock:
            self._cache[coll] = data
            self._path(coll).write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def all(self, coll, **filters):
        rows = list(self._load(coll))
        for k, v in filters.items():
            rows = [r for r in rows if r.get(k) == v]
        return rows

    def get(self, coll, rid):
        for r in self._load(coll):
            if r.get("id") == rid:
                return r
        return None

    def put(self, coll, obj):
        with self.lock:
            data = self._load(coll)
            obj = {**obj, "updated_at": time.time()}
            for i, r in enumerate(data):
                if r.get("id") == obj.get("id"):
                    data[i] = obj
                    break
            else:
                obj.setdefault("created_at", time.time())
                data.append(obj)
            self._save(coll, data)
        return obj

    def patch(self, coll, rid, **kv):
        with self.lock:
            obj = self.get(coll, rid)
            if not obj:
                return None
            return self.put(coll, {**obj, **kv})

    def new_id(self, coll, prefix):
        n = len(self._load(coll)) + 1
        with self.lock:
            while self.get(coll, f"{prefix}-{n:03d}"):
                n += 1
        return f"{prefix}-{n:03d}"
