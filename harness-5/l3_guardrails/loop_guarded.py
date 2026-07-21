"""L3 · 护栏:给 L2 的裸循环装上刹车。三条护栏,任一触发即停。

  1) 迭代上限 max_iterations:最多试几轮,防止无限循环。
  2) 花费上限 max_cost:累计成本(这里用 mock 单位代表 token/$)超预算即停。
  3) 卡死检测 diff-guard:若本轮产物与上轮字节完全相同,说明"修不动了",提前停。

护栏参数来自 constraints.json 的 "loop" 段,可一行行改。

用法:
  python harness-5/l3_guardrails/loop_guarded.py                 # 正常:第 2 轮通过
  HARNESS_SAMPLE_STUCK=1 python harness-5/l3_guardrails/loop_guarded.py  # 演示护栏触发
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lib import common, gates, model  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]

OUT = os.path.join(ROOT, "output", "l3")


def main():
    spec_text, facts, constraints = common.load_spec()
    g = constraints.get("loop", {})
    max_iter = g.get("max_iterations", 5)
    max_cost = g.get("max_cost", 100)
    cost_per = g.get("cost_per_attempt", 20)
    module_path = os.path.join(OUT, facts["module"])

    cfails = gates.check_consistency(spec_text, facts)
    if cfails:
        sys.exit("[L3] 自洽性门禁未过: " + "; ".join(cfails))
    print(f"[L3] 护栏: 最多 {max_iter} 轮 / 预算 {max_cost} / 每轮耗 {cost_per}\n")

    feedback = None
    prev_hash = None
    cost = 0
    attempt = 0
    stop = None
    while True:
        attempt += 1
        # 护栏①:迭代上限
        if attempt > max_iter:
            stop = f"触发【迭代上限】{max_iter} 轮仍未通过,停止"
            break
        # 护栏②:花费上限(生成前预估)
        if cost + cost_per > max_cost:
            stop = f"触发【花费上限】再跑一轮将超预算 {max_cost}(已花 {cost}),停止"
            break

        print(f"===== 第 {attempt} 轮 (已花 {cost}/{max_cost}) =====")
        model.generate(OUT, spec_text, facts, constraints, attempt=attempt, feedback=feedback)
        cost += cost_per

        # 护栏③:卡死检测(产物与上轮完全相同)
        cur_hash = common.sha256_file(module_path)
        if prev_hash is not None and cur_hash == prev_hash:
            stop = "触发【卡死检测】本轮产物与上轮完全相同,判定修不动了,停止"
            break
        prev_hash = cur_hash

        results = gates.verify(OUT, facts, constraints)
        print(gates.format_report(results))
        if gates.all_ok(results):
            stop = f"验收通过 ✓(共 {attempt} 轮,花费 {cost})"
            break
        print(f"[L3] 第 {attempt} 轮未过,回喂继续...\n")
        feedback = gates.format_report(results)

    passed = stop.startswith("验收通过")
    print(f"\n[L3] {stop}")
    state = {"passed": passed, "attempts": attempt, "cost": cost, "stop_reason": stop}
    common.write(os.path.join(OUT, "state.json"), json.dumps(state, ensure_ascii=False, indent=2))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
