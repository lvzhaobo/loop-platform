#!/usr/bin/env python3
"""mumuloop-mini —— loop 工程最小实现：跑 → 判定 → 差分 → 停止。

120 行，零依赖。三条停止条件（顺序敏感，先严后宽）：
  A. error <= pass_when_error      → 通过，停
  B. regressed > 0                 → 回归，停（这一轮变坏了）
  C. 连续 N 轮 error 不降           → 不收敛，停（继续烧没意义）

为什么 B 要立即停：总数 5→4 但新冒一条回归，只看总数会以为变好了。

用法:
  python3 mumuloop-mini.py run --checker "python3 checker_demo.py" \
      --fixer "python3 fixer.py" --max-rounds 5
  python3 mumuloop-mini.py stats
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

OUT = Path(__file__).parent / "out"
LEDGER = OUT / "ledger.jsonl"


def run_checker(cmd):
    """跑门禁，返回 (退出码, 失败的规则 id 集合, 原始输出)"""
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
    fails = set()
    for line in p.stdout.splitlines():
        # 约定：失败行形如  "RED  ERR001  说明"
        if line.startswith("RED"):
            parts = line.split()
            if len(parts) >= 2:
                fails.add(parts[1])
    return p.returncode, fails, p.stdout


def sign(fails):
    return hashlib.md5(",".join(sorted(fails)).encode()).hexdigest()[:8]


def cmd_run(a):
    OUT.mkdir(exist_ok=True)
    prev, same_sig, rows = set(), 0, []
    print(f"═══ mumuloop-mini ═══  门禁: {a.checker}")
    print(f"{'轮':<3}{'退出码':<7}{'error':<7}{'fixed':<7}{'regressed':<11}{'still_red':<10}判定")
    print("─" * 68)

    for rnd in range(1, a.max_rounds + 1):
        code, fails, raw = run_checker(a.checker)
        fixed = prev - fails
        # 第一轮没有基线：不能把"本来就红的"算成回归
        regressed = (fails - prev) if prev else set()
        still = fails & prev
        verdict = ""

        # ── 停止条件 A：通过
        if len(fails) <= a.pass_when_error:
            verdict = "✅ A 通过"
        # ── 停止条件 B：出现回归（第一轮没有 prev，不算）
        elif prev and len(regressed) > 0:
            verdict = f"⛔ B 回归 {sorted(regressed)}"
        # ── 停止条件 C：连续 N 轮不降
        else:
            s = sign(fails)
            same_sig = same_sig + 1 if s == getattr(a, "_last_sig", None) else 0
            a._last_sig = s
            if same_sig >= a.stall_rounds - 1:
                verdict = f"⛔ C 连续 {a.stall_rounds} 轮无变化"

        print(f"{rnd:<3}{code:<7}{len(fails):<7}{len(fixed):<7}"
              f"{len(regressed):<11}{len(still):<10}{verdict or '→ 继续修'}")

        rows.append({"round": rnd, "exit": code, "error": len(fails),
                     "fixed": sorted(fixed), "regressed": sorted(regressed),
                     "still_red": sorted(still), "verdict": verdict or "continue",
                     "ts": time.time()})
        with LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rows[-1], ensure_ascii=False) + "\n")

        if verdict:
            print("\n" + verdict)
            print(f"账本: {LEDGER}")
            return 0 if verdict.startswith("✅") else 2 if "B" in verdict else 3

        prev = fails
        if a.fixer:
            subprocess.run(a.fixer, shell=True, capture_output=True, text=True, timeout=120)

    print(f"\n⛔ 达到轮次上限 {a.max_rounds}")
    return 4


def cmd_stats(a):
    if not LEDGER.exists():
        print("账本为空，先跑一次 run")
        return 1
    rows = [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()]
    by_run, cur = [], []
    last_round = 0
    for r in rows:
        if r["round"] <= last_round:
            by_run.append(cur)
            cur = []
        last_round = r["round"]
        cur.append(r)
    if cur:
        by_run.append(cur)
    print(f"共 {len(by_run)} 次运行，{len(rows)} 轮")
    for i, run in enumerate(by_run, 1):
        last = run[-1]
        print(f"  #{i}  {len(run)} 轮  终态 error={last['error']}  {last['verdict']}")
        for r in run:
            if r["fixed"] or r["regressed"]:
                print(f"      第{r['round']}轮  修好 {r['fixed']}  回归 {r['regressed']}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--checker", required=True)
    r.add_argument("--fixer", default="")
    r.add_argument("--max-rounds", type=int, default=5)
    r.add_argument("--pass-when-error", type=int, default=0)
    r.add_argument("--stall-rounds", type=int, default=3)
    s = sub.add_parser("stats")
    a = ap.parse_args()
    sys.exit(cmd_run(a) if a.cmd == "run" else cmd_stats(a))
