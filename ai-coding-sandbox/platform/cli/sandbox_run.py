#!/usr/bin/env python3
"""MumuLoop 多模型沙箱跑分器（DeepSeek 实跑 + Bedrock 预留）。

聚焦关键闭环，不做平台服务化。一条命令完成：
  1. 读取任务集（批量 spec + 可选 constraints）
  2. 每任务多轮：Maker 生成 -> checker 确定性检查 -> 判定账本（pass/regression/flat/max_rounds）
  3. 修复轮注入 checker 修正指令，驱动下一轮生成
  4. 每轮落盘 trace JSONL（schema 与平台口径一致），含 diff 账本
  5. 汇总并输出 WAF 六支柱证据

用法：
  python3 platform/cli/sandbox_run.py --suite platform/suites/injection-suite.json \
      --maker deepseek --max-rounds 3 --outdir /tmp/mumuloop-sandbox

切换 AWS：
  python3 platform/cli/sandbox_run.py --suite ... --maker bedrock \
      --region us-west-2 --model us.anthropic.claude-3-5-sonnet-20241022-v2:0
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CLI_DIR = Path(__file__).resolve().parent
PLATFORM = CLI_DIR.parent
sys.path.insert(0, str(PLATFORM))

from maker.bedrock_maker import BedrockMaker  # noqa: E402
from maker.deepseek_maker import DeepSeekMaker  # noqa: E402

FAIL_RE = re.compile(r"\s*\[FAIL\]\s+(\w+)\s")
DET_RE = re.compile(r"\s{8}(\S+):(\d+)\s+(.*)$")

RULE_FIX = {
    "ERR001": "禁止直接 raise HTTPException，改用 BusinessException(ErrorCode.XXX, message)",
    "ERR002": "code 字段从 ErrorCode 枚举取值，禁止裸数字（0/200 豁免）",
    "SEC001": "密钥/密码移入 config.py 的 Settings，从 settings 读取，禁止硬编码",
    "SEC002": "密码哈希用 hashPassword()（bcrypt），禁止 md5/sha1",
    "SEC003": "SQL 改参数绑定 execute(sql, {...}) 或走 ORM，禁止 f-string 拼 SQL",
    "CFG001": "配置统一进 config.py 的 Settings，通过 settings.XXX 读取，禁止直接 os.getenv/os.environ",
}

DEFAULT_CONSTRAINTS = (
    "你是后端工程师。只输出纯 Python 代码，不要 Markdown 代码块，不要任何解释文字。"
)


def load_checker(cfg_file: Path, cli_checker: str | None) -> Path:
    raw = cli_checker
    if not raw:
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            raw = cfg.get("checker")
        except (OSError, json.JSONDecodeError):
            raw = None
    if not raw:
        raise SystemExit("未指定检查器：--checker 或 platform/config.json")
    p = Path(raw)
    return p if p.is_absolute() else (PLATFORM / p).resolve()


def run_check(checker: Path, target: Path) -> list[dict]:
    proc = subprocess.run(
        [sys.executable, str(checker), str(target)],
        capture_output=True, text=True,
    )
    violations, current = [], None
    for line in proc.stdout.splitlines():
        m = FAIL_RE.match(line)
        if m:
            current = m.group(1)
            continue
        m = DET_RE.match(line)
        if m and current:
            violations.append({
                "rule": current,
                "file": m.group(1),
                "line": int(m.group(2)),
                "evidence": m.group(3).strip(),
            })
    return violations


def make_repair(violations: list[dict]) -> str:
    grouped: dict[str, list[dict]] = {}
    for v in violations:
        grouped.setdefault(v["rule"], []).append(v)
    lines = ["上一轮检查发现违规，请逐条修复，只改违规处、不动无关代码："]
    for i, (rule, vs) in enumerate(grouped.items(), 1):
        locs = "、".join(f"{v['file']}:{v['line']}" for v in vs)
        lines.append(f"{i}. [{rule}] {locs} —— {RULE_FIX.get(rule, '按规则文件修复')}")
    return "\n".join(lines)


def append_trace(logs_dir: Path, task: str, entry: dict) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    out = logs_dir / f"{task}-{datetime.now().strftime('%Y%m%d')}.jsonl"
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return out


def diff_counts(prev: dict, cur: dict) -> dict:
    rules = set(prev) | set(cur)
    fixed = sum(1 for r in rules if prev.get(r, 0) > 0 and cur.get(r, 0) == 0)
    regressed = sum(1 for r in rules if cur.get(r, 0) > 0 and prev.get(r, 0) == 0)
    still_red = sum(1 for r in rules if prev.get(r, 0) > 0 and cur.get(r, 0) > 0)
    return {"fixed": fixed, "regressed": regressed, "still_red": still_red}


def run_task(maker, maker_name: str, model_name: str, task: dict, outdir: Path,
             checker: Path, logs_dir: Path, max_rounds: int) -> tuple[str, list[dict]]:
    name = task["task"]
    spec = task["spec"]
    constraints = task.get("constraints") or DEFAULT_CONSTRAINTS
    tdir = outdir / name
    tdir.mkdir(parents=True, exist_ok=True)
    target = tdir / "generated.py"
    prev: dict[str, int] = {}
    entries: list[dict] = []

    for rnd in range(1, max_rounds + 1):
        code, usage = maker.generate(spec, constraints)
        target.write_text(code, encoding="utf-8")
        violations = run_check(checker, target)
        counts: dict[str, int] = {}
        for v in violations:
            counts[v["rule"]] = counts.get(v["rule"], 0) + 1
        diff = diff_counts(prev, counts) if rnd > 1 else {"fixed": 0, "regressed": 0, "still_red": 0}

        if not violations:
            result, action, score, rc = "closed", "none", 100, 0
        elif rnd > 1 and diff["regressed"] > 0:
            result, action, score, rc = "escalate", "ticket_written:regression.md", 0, 2
        elif rnd > 1 and diff["fixed"] == 0 and diff["still_red"] > 0:
            result, action, score, rc = "escalate", "ticket_written:flat.md", 0, 2
        elif rnd == max_rounds:
            result, action, score, rc = "escalate", "ticket_written:max-rounds.md", 0, 2
        else:
            result, action, score, rc = "pending_fix", f"ticket_written:ticket-{name}-r{rnd}.md", 0, 1

        entry = {
            "round": rnd,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "target": str(target),
            "violations": len(violations),
            "byRule": counts,
            "score": score,
            "action": action,
            "result": result,
            "maker": maker_name,
            "model": model_name,
            "usage": usage,
            "diff": diff,
        }
        append_trace(logs_dir, name, entry)
        entries.append(entry)

        detail = "，".join(f"{k}×{n}" for k, n in sorted(counts.items())) or "0 违规"
        print(f"  [{name}] round {rnd}: {result:11s} 违规 {len(violations):2d}（{detail}） diff={diff}")

        if result in ("closed", "escalate"):
            break
        constraints = constraints + "\n\n" + make_repair(violations)
        prev = counts

    return name, entries


def main() -> int:
    ap = argparse.ArgumentParser(description="MumuLoop 多模型沙箱跑分器")
    ap.add_argument("--suite", required=True, help="任务集 JSON 文件路径")
    ap.add_argument("--checker", default=None, help="规则检查器路径（默认读 config.json）")
    ap.add_argument("--outdir", default="/tmp/mumuloop-sandbox", help="生成物输出根目录")
    ap.add_argument("--max-rounds", type=int, default=3)
    ap.add_argument("--maker", choices=["deepseek", "bedrock", "dsh"], default="deepseek")
    ap.add_argument("--model", default="us.anthropic.claude-3-5-sonnet-20241022-v2:0")
    ap.add_argument("--deepseek-model", default="deepseek-chat")
    ap.add_argument("--deepseek-base-url", default="https://api.deepseek.com")
    ap.add_argument("--region", default="us-west-2")
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--temperature", type=float, default=0.2)
    args = ap.parse_args()

    checker = load_checker(PLATFORM / "config.json", args.checker)
    if not checker.exists():
        raise SystemExit(f"检查器不存在：{checker}")

    suite_path = Path(args.suite).expanduser().resolve()
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    tasks = suite if isinstance(suite, list) else suite.get("tasks", [])
    if not tasks:
        raise SystemExit("任务集为空")

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    logs_dir = PLATFORM / "data" / "logs"

    if args.maker == "deepseek":
        maker = DeepSeekMaker(
            model=args.deepseek_model,
            base_url=args.deepseek_base_url,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        model_name = args.deepseek_model
    else:
        try:
            maker = BedrockMaker(
                region_name=args.region,
                model_id=args.model,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
            )
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(
                "Bedrock 初始化失败（接口已预留）：请配置 AWS 凭据后重试。\n"
                f"  建议：export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_REGION={args.region}\n"
                f"  或配置 ~/.aws/credentials。原始错误：{exc}"
            )
        model_name = args.model

    print(f"[suite] {suite_path.name} · {len(tasks)} 任务 · maker={args.maker} · max-rounds={args.max_rounds}")
    print(f"[maker] model={model_name}")
    print("=" * 78)

    results: dict[str, dict] = {}
    for t in tasks:
        name, entries = run_task(maker, args.maker, model_name, t, outdir, checker, logs_dir, args.max_rounds)
        last = entries[-1]
        results[name] = {
            "rounds": len(entries),
            "result": last["result"],
            "total_hits": sum(e["violations"] for e in entries),
            "first_hits": entries[0]["violations"],
            "last_diff": last.get("diff", {}),
        }

    print("=" * 78)
    print(" 汇总：")
    total_hits = sum(r["total_hits"] for r in results.values())
    converged = sum(1 for r in results.values() if r["result"] == "closed")
    for name, r in results.items():
        print(f"   {name:20s} rounds={r['rounds']} final={r['result']:10s} "
              f"首轮违规={r['first_hits']} 累计拦截={r['total_hits']}")
    print(f"   收敛 {converged}/{len(results)} · 累计拦截 {total_hits}")

    print("\n WAF 六支柱证据（Lite 档，仅方向）：")
    print("   P1 人机协作   ：唯一强制人工点为人工 Gate；其余轮次机器给结论")
    print("   P2 知识规范   ：Harness 规则红绿测（本次为注入型任务，证明可被机检拦截）")
    print(f"   P3 质量安全   ：累计拦截 {total_hits} 次；收敛 {converged}/{len(results)}")
    print("   P4 效率 ROI   ：收敛轮数与 token 成本见各任务 trace 的 usage 字段")
    print("   P5 可观测审计 ：逐轮 JSONL 落盘 + diff 判定账本（fixed/regressed/still_red）")
    print("   P6 组织演进   ：逃逸项可回流 Harness 校准（本次 n 小，不下有效性结论）")

    print(f"\n trace 目录：{logs_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
