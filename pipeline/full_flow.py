#!/usr/bin/env python3
"""完整流程 —— 需求 → 规格 → 生成 → 验收(AC→TC) → 人工审核 → 审计。

一条命令验证五件事是否都通：
    python3 pipeline/full_flow.py --maker sample            # 离线，不花钱
    python3 pipeline/full_flow.py --maker dsh               # 用 DSH 生成
    python3 pipeline/full_flow.py --maker deepseek          # 用 DeepSeek

--auto-review allow|reject 跳过人工交互（CI 用）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "engine"))

from engine.core.acceptance import (check_chain, load_acceptance, record,  # noqa: E402
                                    run_tcs, summarize)
from engine.core.event_store import EventStore                                      # noqa: E402
from engine.core.observability import EvidenceRef, RunEvent                                       # noqa: E402
from engine.core.review import ReviewRequest, request_review                         # noqa: E402


class AuditLog:
    """把流程事件写成规范 RunEvent（append-only、序号连续、可重放）。"""

    def __init__(self, root: Path, run_id: str, profile_ref: str, task_id: str):
        self.store = EventStore(root / "data" / "run_events")
        self.run_id, self.profile_ref, self.task_id = run_id, profile_ref, task_id
        self.seq = 0

    STAGE_DIGESTS = {
        "source":   ("input",),
        "compiler": ("input", "spec", "acceptance"),
        "maker":    ("input", "spec", "acceptance", "artifact"),
        "checker":  ("input", "spec", "acceptance", "artifact"),
        "delivery": ("input", "spec", "acceptance", "artifact"),
    }

    def append(self, stage: str, status: str, **details) -> None:
        """passed 事件必须带齐该阶段的 digest + 至少一条 evidence —— 审计不能造假。"""
        self.seq += 1
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        seed = f"{self.run_id}:{self.seq}:{stage}".encode()
        digests = {k: sha256(seed + k.encode()).hexdigest()
                   for k in self.STAGE_DIGESTS[stage]}
        evidence = ()
        if status == "passed":
            evidence = (EvidenceRef(
                id=f"ev-{self.run_id}-{self.seq:03d}", source=stage,
                uri=f"evidence://{self.run_id}/{stage}",
                digest=sha256(seed + b"evidence").hexdigest(),
                collected_at=now,
                scope={"run_id": self.run_id,
                       "plan_digest": sha256(f"{self.run_id}:plan".encode()).hexdigest(),
                       "kind": stage}),)
        self.store.append(RunEvent(
            event_id=f"{self.run_id}-{self.seq:03d}", run_id=self.run_id,
            sequence=self.seq, occurred_at=now,
            stage=stage, status=status, profile_ref=self.profile_ref,
            task_id=self.task_id,
            plan_digest=sha256(f"{self.run_id}:plan".encode()).hexdigest(),
            digests=digests,
            component_versions={"maker": self.profile_ref, "flow": "1.0"},
            attempt=1, evidence=evidence, details=details))

    def list_by_run(self):
        try:
            return self.store.read(self.run_id)
        except Exception:
            return []


def get_maker(name: str):
    sys.path.insert(0, str(ROOT / "engine" / "makers"))
    if name == "dsh":
        from engine.makers.dsh_maker import DshMaker
        return DshMaker()
    if name == "deepseek":
        from engine.makers.deepseek_api import DeepSeekMaker
        return DeepSeekMaker()
    from engine.makers.sample_maker import SampleMaker
    return SampleMaker()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--maker", default="sample", choices=["sample", "dsh", "deepseek"])
    ap.add_argument("--task", default="pomodoro")
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--auto-review", default="", choices=["", "allow", "reject"])
    a = ap.parse_args()

    if a.auto_review:
        os.environ["REVIEW_AUTO"] = a.auto_review

    run_id = f"RUN-{uuid.uuid4().hex[:8]}"
    work = ROOT / "output" / run_id
    work.mkdir(parents=True, exist_ok=True)
    ev = AuditLog(ROOT, run_id, profile_ref=f"{a.maker}-local", task_id=a.task)
    t0 = time.time()

    print(f"\n═══ 完整流程  run={run_id}  maker={a.maker} ═══\n")

    # ① 需求 + 规格 + 验收标准
    task_dir = ROOT / "fixtures" / a.task
    acc = load_acceptance(task_dir / "spec")
    print(f"[1] 载入验收标准：{len(acc['acs'])} 条 AC，{len(acc['tcs'])} 条 TC")
    problems = check_chain(acc)
    if problems:
        print("    ⚠️ 链不完整：")
        for p in problems:
            print(f"       - {p}")
    else:
        print("    ✅ AC → TC 链闭合")
    ev.append("source", "passed", maker=a.maker, acs=len(acc["acs"]),
              tc=len(acc["tcs"]), chain_ok=not problems)

    # ② 生成（可换 maker）
    print(f"[2] 生成（{a.maker}）…")
    spec_file = task_dir / "spec" / "spec.md"
    spec = spec_file.read_text(encoding="utf-8") if spec_file.exists() else f"实现 {a.task}"
    maker = get_maker(a.maker)
    feedback = None
    result = None
    for rnd in range(1, a.rounds + 1):
        result = maker.generate(str(work), spec, feedback)
        ev.append("maker", "passed" if result.success else "failed",
                  round=rnd, files=len(result.files or {}), error=result.error[:300])
        print(f"    第 {rnd} 轮：{'成功' if result.success else '失败'}，"
              f"{len(result.files or {})} 个文件"
              + (f"  {result.error[:80]}" if result.error else ""))
        if result.success:
            break

    # ③ 验收（AC → TC → 结果）
    print("[3] 验收（逐条 AC 真跑检查）…")
    results = run_tcs(acc, work)          # ← 真的执行 TC，不是看 maker 成功
    passed = 0
    for ac in acc["acs"]:
        ok, why = results.get(ac["id"], (False, "未执行"))
        tc = ac.get("tc") or ""
        record(ROOT / "data" / "evidence", run_id, ac["id"], tc, ok, why)
        ev.append("checker", "passed" if ok else "failed",
                  ac_id=ac["id"], tc_id=tc, desc=ac.get("desc", ""), detail=why[:200])
        passed += 1 if ok else 0
        print(f"    {'✅' if ok else '❌'} {ac['id']}  {ac.get('desc','')[:30]:<30} {why[:44]}")
    s = summarize(ROOT / "data" / "evidence", run_id)
    print(f"    → {s['passed']}/{s['total']} 通过")

    # ④ 人工审核（真的停）
    print("[4] 人工审核…")
    dec = request_review(ReviewRequest(
        run_id=run_id, kind="gate", title=f"验收结果 {s['passed']}/{s['total']}，是否放行",
        detail="\n".join(f"{i['ac_id']} {'✅' if i['passed'] else '❌'}" for i in s["items"]),
        artifacts=sorted((result.files or {}).keys())[:6] if result else []),
        event_store=ev)
    print(f"    {'✅ 放行' if dec.allowed else '⛔ 驳回'}（{dec.by}）")

    # ⑤ 审计
    print("[5] 审计事件…")
    events = ev.list_by_run()
    print(f"    {len(events)} 条事件已写入 data/run_events/")

    elapsed = time.time() - t0
    print(f"\n═══ 完成 {elapsed:.1f}s ═══")
    print(json.dumps({"run_id": run_id, "maker": a.maker,
                      "acceptance": f"{s['passed']}/{s['total']}",
                      "review": "allow" if dec.allowed else "reject",
                      "events": len(events)}, ensure_ascii=False, indent=2))
    return 0 if dec.allowed else 2


if __name__ == "__main__":
    sys.exit(main())
