"""L0 · 最朴素的生成:一句话调模型,把产物写到磁盘。没有任何检查。

用法: python harness-5/l0_single/run.py
观察: 生成出来的 mathkit.py 到底对不对?—— L0 不知道,也不关心。
      (sample 模式下,这一版 factorial 是错的,但 L0 不会告诉你。)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lib import common, model  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]

OUT = os.path.join(ROOT, "output", "l0")


def main():
    spec_text, facts, constraints = common.load_spec()
    print(f"[L0] 模式={model.MODE} 生成到 {OUT}")
    written = model.generate(OUT, spec_text, facts, constraints, attempt=1)
    print(f"[L0] 完成,写出文件: {written}")
    print("[L0] 注意:L0 没有任何验收 —— 产物可能是错的,你无从得知。下一层 L1 加门禁。")


if __name__ == "__main__":
    main()
