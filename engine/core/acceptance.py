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
