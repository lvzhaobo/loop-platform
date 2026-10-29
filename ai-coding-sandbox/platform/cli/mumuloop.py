#!/usr/bin/env python3
"""
MumuLoop CLI — 形态 1「个人轻量」驱动器：check → 工单 → trace 一条线

定位（与形态 2 的关系）：
  形态 1（本文件）：CLI，个人环境用；一条线 = 跑检查 → 生成本地工单 → 落 trace
  形态 2（server/app.py）：服务化控制台，读同一份日志 schema 展示
  两者共用：JSONL trace schema（round/ts/target/violations/byRule/score/action/result）

与课程素材 loop.py 的差异（演进点）：
  1. 通用化：checker / 工作区任意指定（loop.py 路径固定）
  2. 工单化：产出 tickets/ticket-rN.md（本地票面，供后续工单桥推送到 Jira / 禅道）
  3. 平台化：trace 直接落 platform/data/logs/，形态 2 控制台立即可见

用法：
  python3 platform/cli/mumuloop.py run <目标路径> [--task 名称] [--checker 路径] [--max-rounds 3]
  python3 platform/cli/mumuloop.py stats
  python3 platform/cli/mumuloop.py list

退出码（与 loop.py 对齐）：0 = 闭环完成；1 = 本轮未收敛（已开票）；2 = 达上限需人工介入
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CLI_DIR = Path(__file__).resolve().parent
PLATFORM = CLI_DIR.parent
CONFIG_FILE = PLATFORM / "config.json"
DEFAULT_CONFIG = {
    "checker": "../../../../20261021/课程素材/demo-project/scripts/check.py",
    "logs_dir": "data/logs",
    "tickets_dir": "data/tickets",
}
TODAY = datetime.now().strftime("%Y%m%d")


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            print(f"[警告] 配置解析失败，使用默认：{CONFIG_FILE}")
    return cfg


def resolve_checker(args, cfg):
    raw = args.checker or cfg["checker"]
    p = Path(raw)
    return p if p.is_absolute() else (PLATFORM / p).resolve()


def tag_target(target: Path, checker: Path) -> str:
    """展示与落日志用的目标标识：优先相对 checker 项目的短路径"""
    for base in (checker.parent.parent, checker.parent, Path.cwd(), PLATFORM):
        try:
            return str(target.relative_to(base))
        except ValueError:
            continue
    return str(target)


def run_check(checker: Path, target: Path):
    """调用规则检查器 -> (违规列表, 原始输出)"""
    proc = subprocess.run(
        [sys.executable, str(checker), str(target)],
        capture_output=True, text=True,
    )
    violations, current = [], None
    for line in proc.stdout.splitlines():
        m = re.match(r"\s*\[FAIL\]\s+(\w+)\s", line)
        if m:
            current = m.group(1)
            continue
        m = re.match(r"\s{8}(\S+):(\d+)\s+(.*)$", line)
        if m and current:
            violations.append({
                "rule": current,
                "file": m.group(1),
                "line": int(m.group(2)),
                "evidence": m.group(3).strip(),
            })
    return violations, proc.stdout


def by_rule(violations):
    counts = {}
    for v in violations:
        counts[v["rule"]] = counts.get(v["rule"], 0) + 1
    return counts


def trace_file(logs_dir: Path, task: str) -> Path:
    return logs_dir / f"{task}-{TODAY}.jsonl"


def infer_round(logs_dir: Path, task: str) -> int:
    """读当天该任务的 trace 推断下一轮"""
    lf = trace_file(logs_dir, task)
    if not lf.exists():
        return 1
    rounds = []
    for line in lf.read_text(encoding="utf-8").splitlines():
        try:
            rounds.append(json.loads(line)["round"])
        except (json.JSONDecodeError, KeyError):
            continue
    return max(rounds) + 1 if rounds else 1


def write_ticket(tickets_dir: Path, task: str, round_no: int, target: Path,
                 checker: Path, violations):
    """生成本地工单（票面 = 修正指令 + 元信息；工单桥接 Jira/禅道时直接推此票面）"""
    tickets_dir.mkdir(parents=True, exist_ok=True)
    out = tickets_dir / f"ticket-r{round_no}.md"
    counts = by_rule(violations)
    detail = "，".join(f"{k}×{n}" for k, n in sorted(counts.items()))
    lines = [
        f"# 工单（第 {round_no} 轮）— {task}",
        "",
        f"- 任务：{task}",
        f"- 目标：{target}",
        f"- 时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 来源：形态 1 CLI（check → 工单 → trace）",
        f"- 检查器：{checker}",
        f"- 违规：{len(violations)} 处（{detail}）",
        "",
        "## 明细",
        "",
    ]
    for i, v in enumerate(violations, 1):
        lines += [
            f"{i}. [{v['rule']}] {v['file']}:{v['line']}",
            f"   违规：{v['evidence']}",
        ]
    lines += [
        "",
        "## 关闭条件",
        "",
        f"修复后运行 `python3 platform/cli/mumuloop.py run {target} --task {task}` 复检；",
        "违规归零则 trace 记为 closed，本工单关闭。",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def append_trace(logs_dir: Path, task: str, entry):
    logs_dir.mkdir(parents=True, exist_ok=True)
    lf = trace_file(logs_dir, task)
    with open(lf, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return lf


def cmd_run(args):
    cfg = load_config()
    checker = resolve_checker(args, cfg)
    if not checker.exists():
        print(f"检查器不存在：{checker}\n可在 platform/config.json 或 --checker 指定")
        return 3

    target = Path(args.target).expanduser().resolve()
    if not target.exists():
        print(f"目标不存在：{target}")
        return 3
    task = args.task or target.name
    tag = tag_target(target, checker)

    logs_dir = PLATFORM / cfg["logs_dir"]
    tickets_dir = PLATFORM / cfg["tickets_dir"]
    round_no = infer_round(logs_dir, task)

    print(f"==== MumuLoop 形态 1 · 第 {round_no} 轮 · 任务 {task} ====")
    print(f"[check] 目标 {tag}")
    violations, _ = run_check(checker, target)
    counts = by_rule(violations)
    if counts:
        detail = "，".join(f"{k}x{n}" for k, n in sorted(counts.items()))
        print(f"[评分] 违规 {len(violations)} 处（{detail}）")
    else:
        print("[评分] 0 违规——通过")

    entry = {
        "round": round_no,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "target": tag,
        "violations": len(violations),
        "byRule": counts,
    }

    if not violations:
        entry.update({"score": 100, "action": "none", "result": "closed"})
        lf = append_trace(logs_dir, task, entry)
        print("[终止] 闭环完成：违规归零、检查全绿")
        print(f"[trace] 已落盘 {lf}")
        return 0

    if round_no >= args.max_rounds:
        entry.update({"score": 0, "action": "none", "result": "escalate"})
        lf = append_trace(logs_dir, task, entry)
        print(f"[终止] 达上限 {args.max_rounds} 轮仍未收敛 → 需人工介入（工单桥推送点）")
        print(f"[trace] 已落盘 {lf}")
        return 2

    ticket = write_ticket(tickets_dir, task, round_no, target, checker, violations)
    entry.update({"score": 0, "action": f"ticket_written:{ticket.name}", "result": "pending_fix"})
    lf = append_trace(logs_dir, task, entry)
    print(f"[ticket] 已开票 {ticket} → 交 AI / 人工修复")
    print("[终止] 本轮未收敛（修复后进入下一轮复检）")
    print(f"[trace] 已落盘 {lf}")
    return 1


def iter_entries(logs_dir: Path):
    """读全部 trace（含 sample-multi/ 子目录）"""
    for lf in sorted(logs_dir.rglob("*.jsonl")):
        for line in lf.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
                e["_file"] = lf.name
                yield e
            except json.JSONDecodeError:
                continue


def cmd_stats():
    cfg = load_config()
    logs_dir = PLATFORM / cfg["logs_dir"]
    entries = list(iter_entries(logs_dir))
    if not entries:
        print("暂无 trace（先跑一轮：python3 platform/cli/mumuloop.py run <目标>）")
        return 0

    tasks = {}
    for e in entries:
        stem = Path(e["_file"]).stem
        parts = stem.split("-")
        key = "-".join(parts[:-1]) if parts[-1].isdigit() and len(parts[-1]) == 8 else stem
        tasks.setdefault(key, []).append(e)

    print("======== MumuLoop 平台 trace 概览（口径同课程素材 aggregate.py）========")
    total_rounds = len(entries)
    converged = 0
    total_hits = pending = 0
    rows = []
    for name, es in sorted(tasks.items()):
        es = sorted(es, key=lambda x: (x["ts"], x["round"]))
        hits = sum(e["violations"] for e in es)
        last_v = es[-1]["violations"]
        total_hits += hits
        pending += last_v
        closed = es[-1]["result"] == "closed"
        converged += 1 if closed else 0
        rows.append((name, len(es), hits, es[-1]["result"], es[-1]["ts"][:16]))

    print(f" 任务数：{len(tasks)}    总轮数：{total_rounds}    收敛：{converged}/{len(tasks)}")
    print(f" 拦截累计：{total_hits}    末轮残留：{pending}")
    if total_hits:
        eff = (total_hits - pending) * 100 // total_hits
        print(f" 有效拦截率：{eff}%")
    print()
    print(" 按任务：")
    for name, n, hits, res, ts in sorted(rows, key=lambda r: r[4], reverse=True):
        print(f"   {name:<18} {n} 轮  {hits} 拦截  末轮 {res:<12} {ts}")
    rule_counts = {}
    for e in entries:
        for k, n in e.get("byRule", {}).items():
            rule_counts[k] = rule_counts.get(k, 0) + n
    if rule_counts:
        print()
        print(" 按规则：")
        for k, n in sorted(rule_counts.items(), key=lambda x: -x[1]):
            print(f"   {k}  {n} 次")
    return 0


def cmd_list():
    cfg = load_config()
    logs_dir = PLATFORM / cfg["logs_dir"]
    tickets_dir = PLATFORM / cfg["tickets_dir"]
    entries = list(iter_entries(logs_dir))
    if not entries:
        print("暂无任务（先跑一轮：python3 platform/cli/mumuloop.py run <目标>）")
        return 0

    tasks = {}
    for e in entries:
        stem = Path(e["_file"]).stem
        parts = stem.split("-")
        key = "-".join(parts[:-1]) if parts[-1].isdigit() and len(parts[-1]) == 8 else stem
        tasks.setdefault(key, []).append(e)

    print("任务                 轮数  末状态        最近时间")
    print("-" * 58)
    for name, es in sorted(tasks.items(), key=lambda kv: max(e["ts"] for e in kv[1]), reverse=True):
        es = sorted(es, key=lambda x: (x["ts"], x["round"]))
        last = es[-1]
        open_mark = "  ← 有未关闭工单" if last["result"] != "closed" else ""
        print(f"{name:<18} {len(es):>4}  {last['result']:<12} {last['ts'][:16]}{open_mark}")
    tickets = sorted(tickets_dir.glob("*.md")) if tickets_dir.exists() else []
    print()
    print(f"本地工单目录：{tickets_dir}（{len(tickets)} 份）")
    return 0


def main():
    ap = argparse.ArgumentParser(description="MumuLoop 形态 1 CLI（check → 工单 → trace）")
    sub = ap.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="跑一轮：检查 → 开票 → 落 trace")
    p_run.add_argument("target", help="要检查的目录或文件")
    p_run.add_argument("--task", help="任务名（默认取目标目录名）")
    p_run.add_argument("--checker", help="规则检查器路径（默认读 config.json）")
    p_run.add_argument("--max-rounds", type=int, default=3, help="终止上限（默认 3）")

    sub.add_parser("stats", help="读 platform trace 输出度量")
    sub.add_parser("list", help="列任务与末状态")

    args = ap.parse_args()
    if args.cmd == "run":
        sys.exit(cmd_run(args))
    if args.cmd == "stats":
        sys.exit(cmd_stats())
    if args.cmd == "list":
        sys.exit(cmd_list())
    ap.print_help()
    sys.exit(0)


if __name__ == "__main__":
    main()
