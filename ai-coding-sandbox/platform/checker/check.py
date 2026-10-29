#!/usr/bin/env python3
"""
天翼智屏后端 MVP — 规则检查器（Harness 检查层最小实现）

一条 Rule 一条检查，对应关系：
  rules/error-codes.md  -> ERR001 / ERR002
  rules/security.md     -> SEC001 / SEC002 / SEC003
  rules/config.md       -> CFG001

用法：
  python3 scripts/check.py                # 检查 backend/app（默认）
  python3 scripts/check.py samples/       # 检查指定目录或文件
  python3 scripts/check.py --feedback     # 失败时输出 AI 修正指令（闭环入口）

退出码：0 = 全部通过；1 = 存在违规
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 跳过目录（含 scripts 自身与 tests——检查器不检查自己）
SKIP_DIR_NAMES = {"__pycache__", ".venv", "venv", ".git", "node_modules", "keys", "scripts", "tests"}
# 对 SEC001 / CFG001 整体豁免的文件（配置集中点）
CONFIG_EXEMPT = {"config.py"}


@dataclass
class Check:
    id: str
    desc: str
    pattern: str
    rule_file: str
    fix: str
    exempt_files: set = field(default_factory=set)
    exempt_values: set = field(default_factory=set)


CHECKS = [
    Check("ERR001", "错误码体系：禁止直接 raise HTTPException（应走 BusinessException + ErrorCode）",
          r"raise\s+HTTPException\s*\(",
          "rules/error-codes.md",
          "改用 BusinessException(ErrorCode.XXX, message)"),
    Check("ERR002", "魔法错误码：code 字段禁止裸数字（0 / 200 豁免）",
          r"""['"]code['"]\s*:\s*(\d+)|(?<![\w.'"])code\s*=\s*(\d+)""",
          "rules/error-codes.md",
          "从 ErrorCode 枚举取值",
          exempt_values={"0", "200"}),
    Check("SEC001", "安全红线：禁止硬编码密钥 / 密码",
          r"""(?i)(secret|token|api_key|apikey|password|passwd|private_key)\w*\s*[:=]\s*['"]([^'"]{6,})['"]""",
          "rules/security.md",
          "移入 config.py 的 Settings，从 settings 读取",
          exempt_files=CONFIG_EXEMPT),
    Check("SEC002", "安全红线：禁止弱哈希 md5 / sha1（密码用 bcrypt）",
          r"\b(?:hashlib\.)?(?:md5|sha1)\s*\(",
          "rules/security.md",
          "密码用 hashPassword()（bcrypt）"),
    Check("SEC003", "安全红线：禁止 f-string 拼接 SQL",
          r"""execute\s*\(\s*f['"]""",
          "rules/security.md",
          "改参数绑定：execute(sql, {...}) 或走 ORM"),
    Check("CFG001", "配置规范：禁止直接 os.getenv / os.environ（应进 Settings）",
          r"\bos\.(?:getenv|environ)\b",
          "rules/config.md",
          "加进 config.py 的 Settings，通过 settings.XXX 读取",
          exempt_files=CONFIG_EXEMPT),
]


@dataclass
class Violation:
    check: Check
    path: Path
    line_no: int
    line: str


def iter_py_files(target: Path):
    """遍历目标下的 .py 文件（跳过豁免目录）"""
    if target.is_file():
        yield target
        return
    for p in sorted(target.rglob("*.py")):
        if any(part in SKIP_DIR_NAMES for part in p.parts):
            continue
        yield p


def scan(target: Path):
    """对目标执行全部检查，返回违规列表"""
    violations = []
    for f in iter_py_files(target):
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for c in CHECKS:
                if f.name in c.exempt_files:
                    continue
                m = re.search(c.pattern, line)
                if not m:
                    continue
                if c.exempt_values:
                    val = next((g for g in m.groups() if g), None)
                    if val in c.exempt_values:
                        continue
                if c.id == "SEC001" and m.lastindex and m.group(m.lastindex).startswith("http"):
                    continue
                violations.append(Violation(c, f, i, stripped))
    return violations


def report(target: Path, violations):
    """打印检查报告"""
    def rel(p: Path) -> str:
        for base in (PROJECT_ROOT, Path.cwd()):
            if base in p.parents:
                return str(p.relative_to(base))
        return str(p)

    by_check = {}
    for v in violations:
        by_check.setdefault(v.check.id, []).append(v)

    width = 66
    print("=" * width)
    print(f" Harness 检查报告 — 靶点: {rel(target)}")
    print("=" * width)
    for c in CHECKS:
        hits = by_check.get(c.id, [])
        if hits:
            print(f" [FAIL] {c.id} {c.desc} — {len(hits)} 处")
            for v in hits:
                print(f"        {rel(v.path)}:{v.line_no}  {v.line[:72]}")
        else:
            print(f" [PASS] {c.id} {c.desc}")
    print("-" * width)
    if violations:
        print(f" 结论：不通过（{len(violations)} 处违规，涉及 {len(by_check)} 条规则）")
    else:
        print(" 结论：通过（0 违规）")
    print("=" * width)


def feedback(target: Path, violations):
    """生成 AI 修正指令（Loop 闭环的输入）"""
    def rel(p: Path) -> str:
        for base in (PROJECT_ROOT, Path.cwd()):
            if base in p.parents:
                return str(p.relative_to(base))
        return str(p)

    print()
    print("======== 修正指令（自动生成，供 AI 闭环修复）========")
    print(f"检查发现 {len(violations)} 处违规。要求：逐条修复，不改动无关代码。")
    print()
    for i, v in enumerate(violations, 1):
        print(f"{i}. [{v.check.id}] {rel(v.path)}:{v.line_no}")
        print(f"   违规：{v.line[:90]}")
        print(f"   修法：{v.check.fix}（见 {v.check.rule_file}）")
    print()
    print(f"修复后重新运行：python3 scripts/check.py {rel(target)}")


def main():
    ap = argparse.ArgumentParser(description="规则检查器（一条 Rule 一条检查）")
    ap.add_argument("target", nargs="?", default="backend/app",
                    help="检查目标目录或文件（默认 backend/app）")
    ap.add_argument("--feedback", action="store_true",
                    help="失败时输出 AI 修正指令（闭环入口）")
    args = ap.parse_args()

    target = PROJECT_ROOT / args.target if not Path(args.target).is_absolute() else Path(args.target)
    if not target.exists():
        print(f"目标不存在：{target}")
        sys.exit(2)

    violations = scan(target)
    report(target, violations)
    if violations and args.feedback:
        feedback(target, violations)
    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
