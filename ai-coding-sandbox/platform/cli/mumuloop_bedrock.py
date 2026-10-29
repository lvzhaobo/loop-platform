#!/usr/bin/env python3
"""MumuLoop × Bedrock 最小闭环：生成 → 检查 → trace。

聚焦关键路径，不接入形态 2 服务。一条命令完成：
  1. BedrockMaker 按 spec + constraints 生成代码，写到 outdir/generated.py
  2. 用平台 checker 对生成物做确定性检查
  3. 结果追加为 platform trace JSONL（schema 同形态 1）

用法：
  python3 platform/cli/mumuloop_bedrock.py \
    --spec "写一个 Python 函数 get_user_by_id(db, uid)" \
    --constraints "不要硬编码密钥；不要 eval/exec；不要 shell=True；不要裸 except" \
    --outdir /tmp/bedrock-demo --task bedrock-demo \
    --model us.anthropic.claude-3-5-sonnet-20241022-v2:0 --region us-west-2
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


def append_trace(logs_dir: Path, task: str, entry: dict) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    out = logs_dir / f"{task}-{datetime.now().strftime('%Y%m%d')}.jsonl"
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="MumuLoop × Bedrock 最小闭环")
    ap.add_argument("--spec", required=True, help="单元规格（要生成什么）")
    ap.add_argument("--constraints", default="", help="注入给模型的约束文本")
    ap.add_argument("--outdir", required=True, help="生成物输出目录")
    ap.add_argument("--task", default="bedrock-demo", help="任务名（trace 文件名用）")
    ap.add_argument("--checker", default=None, help="规则检查器路径（默认读 config.json）")
    ap.add_argument("--maker", choices=["bedrock", "deepseek"], default="bedrock")
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

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    target = outdir / "generated.py"

    if args.maker == "deepseek":
        maker = DeepSeekMaker(
            model=args.deepseek_model,
            base_url=args.deepseek_base_url,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        model_name = args.deepseek_model
    else:
        maker = BedrockMaker(
            region_name=args.region,
            model_id=args.model,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        model_name = args.model
    constraints = args.constraints.strip() or (
        "你是资深后端工程师。输出纯 Python 代码，不要 Markdown 代码块，不要解释。"
        "禁止：硬编码密钥/token/密码；eval/exec；subprocess shell=True；裸 except；"
        "SQL 字符串拼接；可变对象作默认参数。"
    )

    print(f"[maker] 调用 {args.maker} model={model_name}")
    code, usage = maker.generate(args.spec, constraints)
    if not code.strip():
        raise SystemExit("Bedrock 返回空文本")
    target.write_text(code, encoding="utf-8")
    print(f"[maker] 已写入 {target}（{len(code)} 字符）")

    violations = run_check(checker, target)
    counts: dict[str, int] = {}
    for v in violations:
        counts[v["rule"]] = counts.get(v["rule"], 0) + 1

    if violations:
        detail = "，".join(f"{k}×{n}" for k, n in sorted(counts.items()))
        print(f"[check] 违规 {len(violations)} 处（{detail}）")
        result = "pending_fix"
        action = "ticket_written:ticket-r1.md"
        score = 0
        rc = 1
    else:
        print("[check] 0 违规——通过")
        result = "closed"
        action = "none"
        score = 100
        rc = 0

    entry = {
        "round": 1,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "target": str(target),
        "violations": len(violations),
        "byRule": counts,
        "score": score,
        "action": action,
        "result": result,
        "maker": args.maker,
        "model": model_name,
        "usage": usage,
    }
    trace = append_trace(PLATFORM / "data" / "logs", args.task, entry)
    print(f"[trace] 已落盘 {trace}")
    print(json.dumps(entry, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
