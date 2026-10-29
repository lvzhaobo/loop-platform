#!/usr/bin/env python3
"""Sample A：自研最小 harness。

用法：
  python3 main.py                # 真实模型（需在 demo/config.env 填 key）
  python3 main.py --mock         # 离线演示（不调 API）
  python3 main.py --mock --yes   # 离线 + 自动批准（无人值守演示）
  python3 main.py --check-safety # 只检查「harness 是否在工作区内」
"""
import argparse, sys
from pathlib import Path

import approve, config, llm, loop, policy, session, tools


def safety_check(cfg):
    """最容易被忽略的一条：harness 代码如果在工作区内，agent 能改掉自己的闸门。"""
    harness = Path(__file__).resolve().parent
    ws = cfg["WORKSPACE_PATH"]
    inside = harness == ws or ws in harness.parents
    print("\n【安全检查】")
    print(f"  harness 目录 : {harness}")
    print(f"  工作区       : {ws}")
    if inside:
        print("  ⚠️  危险：harness 在 agent 可写的范围内")
        print("      agent 可以改写 tools.py，把 rm 加进白名单，然后你就没有白名单了。")
        print("      正确做法：把 harness 放在工作区之外，或只读挂载。")
    else:
        print("  ✅ harness 在工作区之外 —— agent 改不到自己的闸门")
    return not inside


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="不调 API，用脚本模型演示")
    ap.add_argument("--yes", action="store_true", help="自动批准所有需要审批的动作")
    ap.add_argument("--check-safety", action="store_true", help="只做安全检查")
    ap.add_argument("--task", default=None, help="任务文件路径，默认 shared/tasks.md")
    args = ap.parse_args()

    cfg = config.load()
    if args.mock:
        cfg["MOCK"] = "true"
    cfg["AUTO_YES"] = args.yes

    ok = safety_check(cfg)
    if args.check_safety:
        return 0 if ok else 1

    task_path = Path(args.task) if args.task else cfg["SHARED"] / "tasks.md"
    task = Path(task_path).read_text(encoding="utf-8")

    sess = session.Session(cfg["SHARED"].parent / "runs" / "A.jsonl")
    t = tools.Tools(cfg, sess, approve.ask)
    bud = policy.Budget(cfg)

    print(f"\n模型：{'MOCK（离线）' if cfg['bool']('MOCK') else cfg['DEEPSEEK_MODEL']}")
    print(f"任务：{task_path.name}   门禁：{cfg['SHARED'] / 'check.py'}")
    print("─" * 58)

    try:
        result = loop.run(cfg, llm.LLM(cfg), t, sess, bud, task)
    except RuntimeError as e:
        print(f"\n✖ {e}")
        print("  两个办法：① 在 demo/config.env 填 DEEPSEEK_API_KEY  ② 加 --mock 离线演示")
        return 3

    print("\n" + "─" * 58)
    print(f"终止：{result['status']}    门禁退出码：{result['gate']}    "
          f"被拒次数：{result['denied']}    步数：{result['steps']}/{result['max_steps']}")
    print(f"会话：{sess.path}（{sess.seq} 条事件，可回放）")

    if result["status"] == "done" and result["gate"] == 0:
        print("✅ 任务完成且门禁绿")
        return 0
    if result["status"] == "escalated":
        print("⚠ 已升级人工介入（R3）——这正是「终止判定」该有的样子")
        return 2
    print("❌ 未完成")
    return 1


if __name__ == "__main__":
    sys.exit(main())
