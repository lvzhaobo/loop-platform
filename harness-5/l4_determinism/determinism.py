"""L4 · 确定性:同样的输入,跑两遍,产物必须字节一致。

可复现是最硬的验收。做法:固定 temperature=0 + seed,把"跑到通过"的完整流程
独立跑两遍(各自输出目录),对最终产物做 sha256,比对两次哈希是否相同。
每次运行追加到 runs.jsonl,形成可审计的确定性基线。

用法: python harness-5/l4_determinism/determinism.py
观察: 两次哈希相同 → 确定性通过 ✓(sample 是纯确定的;real 模式靠 temp0+seed 逼近)。
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lib import common, gates, model  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]

OUT = os.path.join(ROOT, "output", "l4")


def run_once(out_dir, spec_text, facts, constraints, max_iter):
    """跑一条"生成→验收→回喂"的收敛流程,返回 (passed, 产物哈希, 轮数)。"""
    feedback = None
    for attempt in range(1, max_iter + 1):
        model.generate(out_dir, spec_text, facts, constraints, attempt=attempt, feedback=feedback)
        results = gates.verify(out_dir, facts, constraints)
        if gates.all_ok(results):
            h = common.sha256_file(os.path.join(out_dir, facts["module"]))
            return True, h, attempt
        feedback = gates.format_report(results)
    return False, None, max_iter


def main():
    spec_text, facts, constraints = common.load_spec()
    max_iter = constraints.get("loop", {}).get("max_iterations", 5)
    print(f"[L4] temperature={model.TEMPERATURE} seed={model.SEED} 模式={model.MODE}")
    print("[L4] 将独立跑两遍,比对最终产物哈希...\n")

    runs = []
    for i in (1, 2):
        out_dir = os.path.join(OUT, f"run{i}")
        passed, h, n = run_once(out_dir, spec_text, facts, constraints, max_iter)
        print(f"[L4] run{i}: passed={passed} attempts={n} sha256={h[:16] if h else None}...")
        runs.append({
            "run": i, "passed": passed, "attempts": n, "sha256": h,
            "temperature": model.TEMPERATURE, "seed": model.SEED, "mode": model.MODE,
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        })

    both_pass = all(r["passed"] for r in runs)
    same_hash = runs[0]["sha256"] is not None and runs[0]["sha256"] == runs[1]["sha256"]
    deterministic = both_pass and same_hash

    log_path = os.path.join(OUT, "runs.jsonl")
    with open(log_path, "a", encoding="utf-8") as f:
        for r in runs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n[L4] 两次均通过: {both_pass}")
    print(f"[L4] 两次哈希一致: {same_hash}")
    print(f"[L4] 确定性验收: {'通过 ✓' if deterministic else '未通过 ✗'}")
    print(f"[L4] 已追加基线到 {log_path}")
    sys.exit(0 if deterministic else 1)


if __name__ == "__main__":
    main()
