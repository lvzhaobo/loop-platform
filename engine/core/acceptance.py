"""验收链：AC（验收标准）→ TC（测试用例）→ 门禁结果。

设计要点：
  - 每条 AC 有稳定编号（AC-001），来自需求/规格，不由代码生成
  - 每条 TC 必须挂到某条 AC 上（tc.ac_id）；挂不上的 TC 视为孤儿，报告出来
  - 每次运行把"哪条 AC、被哪条 TC 验、结果如何"写进 evidence，可追溯

为什么要有链：
  没有链，门禁是黑盒——客户问"你凭什么叫通过"，答不上来。
  有链，每条验收标准能追到测试，每个测试能追到一次运行结果。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def load_acceptance(root: Path) -> dict[str, Any]:
    """读 acceptance.json。兼容老格式（只有 checks 列表）。"""
    f = root / "acceptance.json"
    if not f.exists():
        return {"acs": [], "tcs": []}
    raw = json.loads(f.read_text(encoding="utf-8"))

    # 老格式：{"checks": [{"name","desc"}]} → 自动升级成 AC
    if "checks" in raw and "acs" not in raw:
        acs = []
        for i, c in enumerate(raw["checks"], 1):
            acs.append({"id": f"AC-{i:03d}", "desc": c.get("desc") or c.get("name"),
                        "tc": c.get("name", f"tc-{i:03d}")})
        return {"acs": acs, "tcs": [{"id": a["tc"], "ac_id": a["id"]} for a in acs]}

    return {"acs": raw.get("acs", []), "tcs": raw.get("tcs", [])}


def check_chain(acc: dict) -> list[str]:
    """校验链的完整性，返回问题列表（空 = 链是闭合的）。"""
    problems = []
    ac_ids = {a["id"] for a in acc.get("acs", [])}
    tc_ids = {t["id"] for t in acc.get("tcs", [])}
    if not ac_ids:
        problems.append("没有任何 AC（验收标准）—— 门禁无据可依")

    for a in acc.get("acs", []):
        if not a.get("tc"):
            problems.append(f"{a['id']} 没有关联 TC —— 这条标准无法验证")
        elif a["tc"] not in tc_ids:
            problems.append(f"{a['id']} 关联的 TC {a['tc']} 不存在")
    for t in acc.get("tcs", []):
        if t.get("ac_id") not in ac_ids:
            problems.append(f"TC {t['id']} 挂在未知 AC {t.get('ac_id')} 上（孤儿用例）")
    return problems


# ── TC 执行器：把"验收标准"变成真跑一遍的检查 ──
CHECK_TYPES = {
    "file_exists":  "文件存在",
    "text_contains": "文件包含文本",
    "text_absent":  "文件不包含文本",
    "regex":        "文件匹配正则",
    "command":      "命令退出码等于期望值",
    "unit_test":    "测试命令退出码为 0",
    "glob_exists":  "匹配 glob 的文件至少 N 个",
    "node_test_glob": "找到 tests/*.test.js 并用 node 跑通",
}


def _run_one(check: dict, workdir: Path) -> tuple[bool, str]:
    """执行一条 TC 检查，返回 (通过, 说明)。"""
    if not isinstance(check, dict):
        return False, "TC 没有 check 定义（无法验证）"

    kind = check.get("type", "")
    if kind not in CHECK_TYPES:
        return False, f"未知检查类型 {kind!r}（支持：{', '.join(CHECK_TYPES)}）"

    f = workdir / check["file"] if check.get("file") else None

    if kind in ("file_exists", "text_contains", "text_absent", "regex"):
        if not check.get("file"):
            return False, f"{kind} 缺少 file 字段"
        if not f.exists():
            return False, f"文件不存在：{check['file']}"
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            return False, f"读不了 {check['file']}：{e}"

        if kind == "file_exists":
            return True, f"{check['file']} 存在（{len(text)} 字符）"
        if kind == "text_contains":
            v = check.get("value", "")
            return (v in text), (f"包含 {v!r}" if v in text else f"没找到 {v!r}")
        if kind == "text_absent":
            v = check.get("value", "")
            return (v not in text), (f"未出现 {v!r}" if v not in text else f"不该出现 {v!r}")
        import re
        pat = check.get("pattern", "")
        m = re.search(pat, text)
        return bool(m), (f"匹配 {pat!r} → {m.group(0)[:40]!r}" if m else f"不匹配 {pat!r}")

    if kind == "glob_exists":
        pat = check.get("pattern", "*")
        need = int(check.get("min", 1))
        hits = sorted(x for x in workdir.glob(pat)
                      if x.is_file() and not any(p.startswith(".") for p in x.parts))
        return len(hits) >= need, (f"找到 {len(hits)} 个 {pat}（需要 ≥{need}）"
                                   + (f"：{[h.name for h in hits][:3]}" if hits else ""))

    if kind == "node_test_glob":
        pat = check.get("pattern", "tests/*.test.js")
        hits = sorted(x for x in workdir.glob(pat) if x.is_file())
        if not hits:
            return False, f"没有匹配 {pat} 的测试文件"
        target = hits[0]
        import subprocess
        try:
            r = subprocess.run(f"node {target.relative_to(workdir)}", shell=True,
                               cwd=str(workdir), capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return False, f"测试超时：{target.name}"
        ok = r.returncode == 0
        passed_n = ""
        for line in (r.stdout or "").splitlines():
            if line.strip().startswith("ℹ pass"):
                passed_n = line.strip()
                break
        return ok, f"{target.name} 退出码 {r.returncode} {passed_n}"

    if kind in ("command", "unit_test"):
        import subprocess
        cmd = check.get("command") or check.get("cmd")
        if not cmd:
            return False, f"{kind} 缺少 command 字段"
        expect = 0 if kind == "unit_test" else int(check.get("expect_exit", 0))
        try:
            r = subprocess.run(cmd, shell=True, cwd=str(workdir),
                               capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return False, f"命令超时：{cmd}"
        ok = r.returncode == expect
        tail = (r.stdout or r.stderr or "").strip().splitlines()
        return ok, (f"退出码 {r.returncode}"
                    + (f"；{tail[-1][:80]}" if tail else ""))

    return False, f"未实现的检查类型 {kind}"


def run_tcs(acc: dict, workdir: Path) -> dict[str, tuple[bool, str]]:
    """跑所有 TC，返回 {ac_id: (通过, 说明)}。一个 AC 挂多条 TC 时取全部通过。"""
    tc_by_id = {t["id"]: t for t in acc.get("tcs", [])}
    out: dict[str, list[tuple[bool, str]]] = {}
    for ac in acc.get("acs", []):
        tc_id = ac.get("tc")
        tc = tc_by_id.get(tc_id) if tc_id else None
        if not tc or not tc.get("check"):
            out.setdefault(ac["id"], []).append((False, "没有可执行的 TC"))
            continue
        out.setdefault(ac["id"], []).append(_run_one(tc["check"], workdir))
    return {k: (all(r[0] for r in v), "；".join(r[1] for r in v)) for k, v in out.items()}


def record(evidence_dir: Path, run_id: str, ac_id: str, tc_id: str,
           passed: bool, detail: str = "") -> dict:
    """把一条 AC 的验证结果落进 evidence。"""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    rec = {"run_id": run_id, "ac_id": ac_id, "tc_id": tc_id,
           "passed": bool(passed), "detail": detail[:500], "ts": time.time()}
    with (evidence_dir / "acceptance.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def summarize(evidence_dir: Path, run_id: str) -> dict:
    """某个 run 的验收汇总：每条 AC 最后一次的结果。"""
    f = evidence_dir / "acceptance.jsonl"
    if not f.exists():
        return {"run_id": run_id, "total": 0, "passed": 0, "items": []}
    latest: dict[str, dict] = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["run_id"] == run_id:
            latest[r["ac_id"]] = r
    items = sorted(latest.values(), key=lambda x: x["ac_id"])
    return {"run_id": run_id, "total": len(items),
            "passed": sum(1 for x in items if x["passed"]), "items": items}
