"""MumuSpec 四维评分器：完整性 + 可追溯性 + 可验证性 + 一致性。

对齐 spec-console-bl-v4.html 的 SCORE_FRAMEWORK。
输入: docs 字典（{文件名: 内容}），由 mumuspec_compiler.run_pipeline() 产出。
输出: {"total": 0-100, "dimensions": {...}}

用法:
  python loop/engine/tools/mumuspec_grade.py <case_name>
"""

import json
import os
import re
import sys

DOC_NAMES = {  # 与 mumuspec_compiler.py 保持一致
    "02": "02-elicitation.md",   "03": "03-proposal.md",
    "04": "04-prd.md",           "05": "05-user-stories.md",
    "06": "06-fsd.md",           "07": "07-nfr.md",
    "08": "08-architecture.md",  "09": "09-api-spec.md",
    "10": "10-data-model.md",    "11": "11-security.md",
    "12": "12-implementation-plan.md",
    "13": "13-test-strategy.md", "14": "14-traceability-matrix.md",
}

TARGET_DOCS = ["03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14"]
FUZZY_WORDS = ["尽量", "大概", "可能", "建议", "友好", "应该",
               "适当", "酌情", "差不多", "基本上", "一般来说"]


def _read_case_docs(case_name: str) -> dict:
    """从 cases/<name>/mumuspec/ 读取 14 文档。"""
    engine_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mumu_dir = os.path.join(engine_dir, "cases", case_name, "mumuspec")
    docs = {}
    if os.path.isdir(mumu_dir):
        for fname in os.listdir(mumu_dir):
            if fname.endswith(".md"):
                with open(os.path.join(mumu_dir, fname), encoding="utf-8") as f:
                    docs[fname] = f.read()
    # 也读取 spec/ 下的契约
    spec_dir = os.path.join(engine_dir, "cases", case_name, "spec")
    if os.path.isdir(spec_dir):
        for fname in os.listdir(spec_dir):
            path = os.path.join(spec_dir, fname)
            with open(path, encoding="utf-8") as f:
                docs[f"spec/{fname}"] = f.read()
    return docs


# ═══════════════════════════════════════════════════════════════════
# 维度 1: 完整性（满分 30）
# ═══════════════════════════════════════════════════════════════════

def check_completeness(docs: dict) -> dict:
    checks = []
    filled = 0
    for doc_id in TARGET_DOCS:
        fname = DOC_NAMES[doc_id]
        content = docs.get(fname, "")
        stripped = re.sub(r'^---\n[\s\S]*?\n---\n*', '', content)
        placeholders = re.findall(r'【[^】]*填写[^】]*】', stripped)
        fuzzy = []
        for w in FUZZY_WORDS:
            hits = re.findall(w, stripped)
            if hits:
                fuzzy.append(f"{w}({len(hits)})")
        if not placeholders:
            filled += 1
            result = "warn" if fuzzy else "pass"
        else:
            result = "fail"
        checks.append({"item": f"{doc_id} {fname}", "result": result,
                       "note": f"{len(placeholders)}占位符, 模糊词:{fuzzy}" if fuzzy else ""})
    score = round((filled / len(TARGET_DOCS)) * 30)
    return {"score": score, "max": 30, "checks": checks}


# ═══════════════════════════════════════════════════════════════════
# 维度 2: 可追溯性（满分 25）
# ═══════════════════════════════════════════════════════════════════

def check_traceability(docs: dict) -> dict:
    checks = []
    all_text = "\n".join(docs.values())
    reqs = set(re.findall(r'REQ-\w*[\d]+', all_text))
    uss = set(re.findall(r'US-\d+', all_text))
    tcs = set(re.findall(r'TC-\d+', all_text))

    # 通用格式兼容
    if not reqs:
        reqs = set(re.findall(r'REQ[\d]+', all_text))
    if not tcs:
        tcs = set(re.findall(r'TC[\d]+', all_text))

    checks.append({"item": "编号统计", "result": "pass" if reqs else "warn",
                   "note": f"REQ:{len(reqs)}, US:{len(uss)}, TC:{len(tcs)}"})

    # 05→09 交叉引用
    doc05 = docs.get(DOC_NAMES["05"], "")
    doc09 = docs.get(DOC_NAMES["09"], "")
    refs_api = "09" in doc05 or "API" in doc05
    checks.append({"item": "05→09 交叉引用", "result": "pass" if refs_api else "warn",
                   "note": "05引用了API" if refs_api else "05未引用API"})

    tc_per_req = len(tcs) >= len(reqs) if reqs else True
    checks.append({"item": "P0 REQ→TC 覆盖", "result": "pass" if tc_per_req else "fail",
                   "note": f"{len(reqs)} REQ, {len(tcs)} TC" + (" ✓" if tc_per_req else " ✗")})

    score = min(25, 15 + len(reqs) * 2 + (3 if tc_per_req else 0))
    return {"score": score, "max": 25, "checks": checks}


# ═══════════════════════════════════════════════════════════════════
# 维度 3: 可验证性（满分 25）
# ═══════════════════════════════════════════════════════════════════

def check_verifiability(docs: dict) -> dict:
    checks = []
    fuzzy_total = 0
    for fname, content in docs.items():
        if fname.startswith("spec/"):
            continue
        for w in FUZZY_WORDS:
            fuzzy_total += len(re.findall(w, content))

    doc05 = docs.get(DOC_NAMES["05"], "")
    ac_count = len(re.findall(r'AC-\d+', doc05))
    doc09 = docs.get(DOC_NAMES["09"], "")
    has_json = "```json" in doc09

    checks.append({"item": "模糊词总数", "result": "warn" if fuzzy_total > 0 else "pass",
                   "note": f"共{fuzzy_total}处"})
    checks.append({"item": "AC 可测试性", "result": "pass" if ac_count >= 3 else "fail",
                   "note": f"{ac_count}条 AC 定义"})
    checks.append({"item": "09 JSON 示例", "result": "pass" if has_json else "warn",
                   "note": "有 JSON 示例" if has_json else "无 JSON 示例"})

    score = max(0, 25 - min(10, fuzzy_total))
    return {"score": score, "max": 25, "checks": checks}


# ═══════════════════════════════════════════════════════════════════
# 维度 4: 一致性（满分 20）
# ═══════════════════════════════════════════════════════════════════

def check_consistency(docs: dict) -> dict:
    checks = []
    doc09 = docs.get(DOC_NAMES["09"], "")
    doc10 = docs.get(DOC_NAMES["10"], "")
    doc08 = docs.get(DOC_NAMES["08"], "")

    fields09 = set(re.findall(r'`(\w+)`', doc09))
    fields10 = set(re.findall(r'`(\w+)`', doc10))
    common = fields09 & fields10
    checks.append({"item": "09↔10 字段一致", "result": "pass" if common else "warn",
                   "note": f"共同字段: {', '.join(sorted(common))}" if common else "无共同字段"})

    storage_ok = "无持久化" in doc08 or "不持久化" in doc10 or "JSON" in doc10
    checks.append({"item": "08↔10 存储策略", "result": "pass" if storage_ok else "warn",
                   "note": "一致" if storage_ok else "存疑"})

    score = min(20, 10 + len(common) * 2 + (2 if storage_ok else 0))
    return {"score": score, "max": 20, "checks": checks}


# ═══════════════════════════════════════════════════════════════════
# 汇总
# ═══════════════════════════════════════════════════════════════════

def grade_mumuspec(docs: dict) -> dict:
    dimensions = {
        "completeness":  check_completeness(docs),
        "traceability":  check_traceability(docs),
        "verifiability": check_verifiability(docs),
        "consistency":   check_consistency(docs),
    }
    total = sum(d["score"] for d in dimensions.values())
    max_score = sum(d["max"] for d in dimensions.values())
    return {
        "total": total, "max": max_score,
        "pct": round(total / max_score * 100, 1) if max_score else 0,
        "dimensions": dimensions,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python mumuspec_grade.py <case_name>")
        sys.exit(1)
    case_name = sys.argv[1]
    docs = _read_case_docs(case_name)
    if not docs:
        print(f"未找到 {case_name} 的 MumuSpec 文档")
        sys.exit(1)
    result = grade_mumuspec(docs)
    print(f"MumuSpec 四维评分: {case_name}")
    print(f"总分: {result['total']}/{result['max']} ({result['pct']}%)")
    for dim, data in result["dimensions"].items():
        print(f"  {dim}: {data['score']}/{data['max']}")
        for c in data["checks"]:
            icon = "✅" if c["result"] == "pass" else "⚠️" if c["result"] == "warn" else "❌"
            print(f"    {icon} {c['item']}: {c.get('note', '')}")
