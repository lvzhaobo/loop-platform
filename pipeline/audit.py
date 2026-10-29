#!/usr/bin/env python3
"""审计查询 —— 看一个 run 的完整事实链。

    python3 pipeline/audit.py --list                 列出所有 run
    python3 pipeline/audit.py --run RUN-xxxx         看某次运行的完整事件
    python3 pipeline/audit.py --run RUN-xxxx --json  机器可读
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.core.event_store import EventStore   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--run", default="")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    root = ROOT / "data" / "run_events"
    store = EventStore(root)

    if a.list or not a.run:
        files = sorted(root.glob("*.jsonl"), key=lambda x: -x.stat().st_mtime)
        if not files:
            print("还没有任何审计记录")
            return 0
        print(f"{'RUN':<16}{'事件':<6}{'末态':<12}{'时间'}")
        print("─" * 56)
        for f in files[:20]:
            rid = f.stem
            try:
                evs = store.read(rid)
            except Exception:
                continue
            last = evs[-1] if evs else None
            import datetime
            ts = datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%m-%d %H:%M")
            print(f"{rid:<16}{len(evs):<6}{last.status if last else '—':<12}{ts}")
        return 0

    try:
        evs = store.read(a.run)
    except Exception as e:
        print(f"读不到 {a.run}：{e}", file=sys.stderr)
        return 1

    if a.json:
        print(json.dumps([e.to_dict() for e in evs], ensure_ascii=False, indent=2))
        return 0

    print(f"run {a.run} · {len(evs)} 条事件\n")
    for e in evs:
        d = e.details or {}
        extra = " ".join(f"{k}={v}" for k, v in d.items()
                         if k in ("ac_id", "tc_id", "files", "round", "maker", "detail"))[:90]
        print(f"  {e.sequence:<3} {e.occurred_at:<21} {e.stage:<9} {e.status:<10} "
              f"ev={len(e.evidence)}  {extra}")
    bad = [e for e in evs if e.status == "failed"]
    print(f"\n{'⚠️ ' + str(len(bad)) + ' 条失败' if bad else '✅ 全部通过'}")
    return 0 if not bad else 2


if __name__ == "__main__":
    sys.exit(main())
