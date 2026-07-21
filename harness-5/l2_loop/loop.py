"""L2 · Loop:把 L1 的门禁接成闭环。失败 → 回喂报告 → 重新生成 → 再验收,直到通过。

这是 Loop 的最朴素形态(Ralph 式):Maker(生成) 与 Checker(验收) 分离,
Checker 的失败报告成为 Maker 下一轮的输入。状态写入 state.json,过程可追溯。

用法: python harness-5/l2_loop/loop.py
观察: sample 模式下 attempt1(BUGGY) 验收失败 → 回喂 → attempt2(CORRECT) 通过。
      你会亲眼看到"自我纠错"发生。

⚠️ 注意:L2 故意【不设任何上限】。真实模型可能修不好而无限循环、把额度烧光。
   —— 这正是 L3 护栏要解决的问题。教学时先感受"裸循环"的危险。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lib import common, gates, model  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]

OUT = os.path.join(ROOT, "output", "l2")


def main():
    spec_text, facts, constraints = common.load_spec()

    cfails = gates.check_consistency(spec_text, facts)
    if cfails:
        sys.exit("[L2] 自洽性门禁未过: " + "; ".join(cfails))
    print("[L2] 自洽性门禁通过 ✓\n")

    state = {"attempts": []}
    feedback = None
    attempt = 0
    while True:
        attempt += 1
        print(f"===== 第 {attempt} 轮 =====")
        model.generate(OUT, spec_text, facts, constraints, attempt=attempt, feedback=feedback)
        results = gates.verify(OUT, facts, constraints)
        report = gates.format_report(results)
        print(report)
        ok = gates.all_ok(results)
        state["attempts"].append({
            "attempt": attempt,
            "passed": ok,
            "passed_checks": sum(1 for r in results if r["ok"]),
            "total_checks": len(results),
        })
        if ok:
            print(f"\n[L2] 第 {attempt} 轮通过 ✓ 循环结束")
            break
        print(f"[L2] 第 {attempt} 轮未过,把失败报告回喂给模型,继续...\n")
        feedback = report

    state["final"] = {"passed": True, "attempts": attempt}
    common.write(os.path.join(OUT, "state.json"), json.dumps(state, ensure_ascii=False, indent=2))
    print(f"[L2] 状态已写入 {os.path.join(OUT, 'state.json')}(共 {attempt} 轮)")


if __name__ == "__main__":
    main()
