"""L1 · Harness:给生成套上"环境 + 门禁"。单次尝试,不重试。

流程(三步门禁):
  1) 生成【前】check_consistency:facts 与 spec 是否漂移(最便宜,先跑)
  2) 生成:model.generate()
  3) 生成【后】verify:结构 / 安全 / 行数 / 跑测试

用法: python harness-5/l1_harness/gate.py
观察: sample 模式下这一版 factorial 有 bug → verify 的"测试全绿"会 FAIL,
      L1 如实报错并退出码 1。它能【发现】问题,但不会【修复】—— 那是 L2 的事。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lib import common, gates, model  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]

OUT = os.path.join(ROOT, "output", "l1")


def main():
    spec_text, facts, constraints = common.load_spec()

    # 关卡一:自洽性(生成前,不花钱)
    cfails = gates.check_consistency(spec_text, facts)
    if cfails:
        print("[L1] 自洽性门禁未过:")
        for f in cfails:
            print("   - " + f)
        sys.exit(2)
    print("[L1] 自洽性门禁通过 ✓")

    # 生成
    print(f"[L1] 模式={model.MODE} 生成到 {OUT}")
    model.generate(OUT, spec_text, facts, constraints, attempt=1)

    # 关卡二:验收
    results = gates.verify(OUT, facts, constraints)
    print(gates.format_report(results))

    ok = gates.all_ok(results)
    print(f"\n[L1] 验收{'通过 ✓' if ok else '未通过 ✗ —— L1 只发现不修复,去 L2 看闭环'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
