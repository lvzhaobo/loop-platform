"""WBS 编译层：12-implementation-plan.md + acceptance.json → spec/wbs.json。

上游 MumuSpec 已产出「契约三件套」(spec.md + manifest.json + acceptance.json) 与
14 份规划文档，其中 12-implementation-plan.md 有里程碑表 + 按周的详细任务。
这一段把那些 Markdown 编译成机器可读的任务清单，并与 acceptance 的 TC 条目做
**确定性关联**：任务是做什么，AC 是怎么判，两者必须互相指认得上。

关联不用 LLM：路径/文件名/关键词的匹配是可解释的，用规则做，结论能复现。
匹配不上不硬凑，而是当场列出来——这正是本工具的输出：

  uncovered_ac   契约里要求验收，但没有任何任务负责它
  dangling_ac    任务挂上了 AC，但该 AC 自身不可自动判定(manual/unit_test)
  plan_routes    任务提到接口路径，契约里却没有对应 AC(做了没人验)
  contract_routes契约定了 AC，任务里完全没提(计划漏做)

前三类是发现，不是错误，不阻断落盘；只有解析不出任何任务才算失败。

用法：
    # 单个 case
    python engine/tools/wbs_compiler.py --name music_player

    # 只出门禁报告，不写文件
    python engine/tools/wbs_compiler.py --name music_player --check

    # 扫全部 case，汇总哪些有 12-plan 可编译
    python engine/tools/wbs_compiler.py --all
"""
import argparse
import json
import os
import re
import sys
from typing import Any

HARNESS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(HARNESS_DIR)
CASES_DIR = os.path.join(ROOT, "cases")

PLAN_REL = os.path.join("mumuspec", "12-implementation-plan.md")
WBS_REL = os.path.join("spec", "wbs.json")

# 路由里的结构段，做匹配时剔除：/api/health 与 /health 应当能对上
ROUTE_NOISE = {"api", "v1", "v2", "rest"}
# AC 里不能自动判定的类型
AC_NONAUTO = {"manual", "unit_test"}
# Markdown 内联标记：成对出现，要整体剥，不能只剥首尾字符
_MD_INLINE = ("`", "**")
# 表头关键词 → 逻辑列名。12-plan 由 LLM 生成，列名不统一（「阶段」/「里程碑」、
# 「主要交付物」/「工作内容」），按语义定位列，不按位置写死。
COLUMN_KEYS = {
    "milestone": ("里程碑", "阶段"),
    "deliverables": ("主要交付物", "交付物", "工作内容"),
    "criteria": ("完成标准", "验收标准"),
    "goal": ("目标",),
}
# 里程碑单元格：标题与分隔符都可选。“M2”、“M2：核心播放”、“M2 – 集成测试通过” 三种写法共存，
# 要分隔符会让只写编号的里程碑静默丢失（fs_002 写成 “M3 – …” 才没暴露这个问题）。
MILE_RE = re.compile(r"M(\d+)(?:\s*[：:–—\-]{1,2}\s*(.*?))?\s*$")
WEEK_RE = re.compile(r"第\s*(\d+)\s*周")
# 计划文本里对验收条目的引用：AC-001 / AC‑008 / AC_3 / AC01。
# HYPHENS 收齐各类连字符/破折号：LLM 产出的文档里同一个语义可能是 U+002D、U+2010、
# U+2011(不换行连字符，fs_002 实际用的就是这个)、U+2013、U+2014、U+2015、全角 U+FF0D。
# 按码点逐个补是打地鼠；这里的集合来自对现有 case 的实测，新文档出现未见码点时会漏，
# 漏了表现为「计划未引用 AC」而不是错报。
HYPHENS = "\u002d\u2010\u2011\u2012\u2013\u2014\u2015\uff0d"
AC_SEP = f"[{HYPHENS}_/:\uFF1A]?"
# 两头都不用 \b：“AC01 到 AC08” 里 '1'与'到'、'到'与'A' 在 Python 眼里都是 \w，
# \b 两边都不成立，一条引用能漏掉后半。首锚改成“前面不是 ASCII 字母数字”（排除 MAC1
# 这种误匹配），尾锚用 (?!\d) 表示“数字到此为止”。
AC_LEFT = r"(?<![0-9A-Za-z])A\s*C\s*"
AC_REF_RE = re.compile(AC_LEFT + AC_SEP + r"\s*0*(\d{1,3})(?!\d)")
AC_RANGE_RE = re.compile(
    AC_LEFT + AC_SEP + r"\s*0*\d+\s*(?:\u81f3|\u5230|~|[\u2013\u2014-])"
    + r"\s*(?:A\s*C)?" + AC_SEP + r"\s*0*\d+")


def route_segments(route: str) -> set[str]:
    """/api/playback/state → {"playback", "state"}；用于跨写法比对路径。"""
    parts = [p for p in re.split(r"[\/\-_]", route or "") if p]
    return {p.lower() for p in parts if p.lower() not in ROUTE_NOISE}


def extract_routes(text: str) -> set[str]:
    """只认反引号里的路径，如 `/playback/play`。

    不用裸 `/` 匹配：12-plan 里 "Selenium/Cypress"、"React/Electron"、"macOS/Linux"
    这类斜杠分隔词会被误抓成接口，误报会把这个工具的结论整体拖成不可信。
    代价是计划里不加反引号的接口会被漏掉——宁可漏，不错报。
    """
    found = set()
    for m in re.finditer(r"`([^`\n]+)`", text):
        seg = m.group(1).strip().rstrip("/")
        if seg.startswith("/") and " " not in seg and "//" not in seg:
            found.add(seg.lower())
    return found


def clean(cell: str) -> str:
    """剥掉 Markdown 内联标记：粗体星号、行内代码反引号。

    用 replace 不用 strip：`/pause` API 这种单元格，反引号只有一侧在首尾，
    按首尾字符剥会剩下半个标记写进 wbs.json。标记换成空格，不连字（/pause`API），
    换完再归一空白，否则一个标记就剩两个空格。
    路径识别读的是未清洗的 raw 行，这里剥掉反引号不影响 extract_routes。
    """
    text = cell.strip()
    for mark in _MD_INLINE:
        text = text.replace(mark, " ")
    return re.sub(r"\s+", " ", text).strip().strip("*").strip()


def _header_map(cells: list[str]) -> dict[str, int]:
    """按表头文本定位语义列。认不出「里程碑/阶段」列就不当任务表处理。"""
    idx: dict[str, int] = {}
    for i, c in enumerate(cells):
        for key, words in COLUMN_KEYS.items():
            if key not in idx and any(w in c for w in words):
                idx[key] = i
                break
    return idx if "milestone" in idx else {}


def _cell(cells: list[str], idx: dict[str, int], key: str) -> str:
    i = idx.get(key, -1)
    return cells[i] if 0 <= i < len(cells) else ""


def _table_tasks(lines: list[str]) -> list[dict[str, Any]]:
    """吃里程碑表与时间线表。表头换列名不影响，空表不产生任务。

    同一张表内 id 只取首次出现，后面的当作跨页重复行。
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    idx: dict[str, int] = {}
    for line in lines:
        s = line.strip()
        if not s.startswith("|"):
            idx = {}
            continue
        cells = [clean(c) for c in s.strip("|").split("|")]
        if set("".join(cells)) <= set("-: "):      # 对齐分隔行 |---|---|
            continue
        if not idx:
            idx = _header_map(cells)
            continue
        mcell = _cell(cells, idx, "milestone")
        mm, wm = MILE_RE.search(mcell), WEEK_RE.search(mcell)
        if mm:
            mid, title, kind, week = f"M{mm.group(1)}", mm.group(2) or mcell, "milestone", None
        elif wm:
            mid, title, kind, week = f"W{wm.group(1)}", mcell, "week", int(wm.group(1))
        else:
            continue
        if mid in seen:
            continue
        seen.add(mid)
        crit = _cell(cells, idx, "criteria")
        goal = _cell(cells, idx, "goal")
        deliv = _cell(cells, idx, "deliverables")
        out.append({
            "id": mid, "milestone": mid, "title": title, "level": kind,
            "week": week, "goal": goal, "role": "",
            "deliverables": [clean(d) for d in re.split(r"[；;、,]", deliv) if clean(d)],
            "done_criteria": crit,
            "ac_refs": sorted({int(n) for n in AC_REF_RE.findall(crit + " " + goal)}),
            "ac_range": bool(AC_RANGE_RE.search(crit + " " + goal)),
            # 未清洗原文：接口路径靠反引号识别，clean 后就丢了（不落盘）
            "raw": line,
        })
    return out


def _section_lines(lines: list[str], title_pat: str) -> list[str]:
    """取指定章节标题下到下一个标题前的行，避免把全文 bullet 当成任务。"""
    body: list[str] = []
    hit = False
    for line in lines:
        s = line.strip()
        if s.startswith("#"):
            if hit:
                break
            hit = bool(re.search(title_pat, s))
            continue
        if hit:
            body.append(line)
    return body


def _ordered_tasks(lines: list[str]) -> list[dict[str, Any]]:
    """「## 里程碑」下的有序列表（test_pomo 那种没表格的极简计划）。"""
    out: list[dict[str, Any]] = []
    for line in _section_lines(lines, r"里程碑"):
        om = re.match(r"^\s*(\d+)[\.、]\s*(.+)$", line)
        if not om:
            continue
        n, body = int(om.group(1)), clean(om.group(2))
        out.append({
            "id": f"M{n}", "milestone": f"M{n}", "title": body, "level": "milestone",
            "week": None, "goal": "", "role": "",
            "deliverables": [clean(d) for d in re.split(r"[，,+、]", body) if clean(d)],
            "done_criteria": "", "ac_refs": [], "ac_range": False, "raw": line,
        })
    return out


def _role_tasks(lines: list[str]) -> list[dict[str, Any]]:
    """「## 关键任务分解」下 `- **后端**` 分组及其缩进子项。"""
    out: list[dict[str, Any]] = []
    cur_role = ""
    for line in _section_lines(lines, r"任务分解|任务与时间线"):
        rm = re.match(r"^-\s*\*\*([^*]+)\*\*\s*$", line.strip())
        if rm:
            cur_role = clean(rm.group(1))
            continue
        if re.match(r"^\s*(\d+)[\.、]\s*\*\*", line) or re.match(r"^-\s*\*\*第", line.strip()):
            wm = re.search(r"第\s*(\d+)\s*周", line)
            cur_role = f"第{wm.group(1)}周" if wm else cur_role
            continue
        sm = re.match(r"^\s+-\s+(.+)$", line)
        if not sm or not cur_role:
            continue
        body = clean(sm.group(1))
        out.append({
            "id": f"T{len(out) + 1}-{cur_role}", "milestone": "", "title": body[:60],
            "level": "task", "week": None, "goal": "", "role": cur_role,
            "deliverables": [clean(d) for d in re.split(r"[，,+、]", body) if clean(d)],
            "done_criteria": "", "ac_refs": [], "ac_range": False, "raw": line,
        })
    return out


def parse_plan(md: str) -> list[dict[str, Any]]:
    """从 12-plan 抽任务。四种来源：里程碑表 / 时间线表 / 有序列表 / 任务分解分组。

    一个都抽不到就返回空，由调用方判失败——不从 spec.md 猜任务，猜出来的不算数。
    """
    lines = md.splitlines()
    tasks = _table_tasks(lines) + _ordered_tasks(lines) + _role_tasks(lines)
    dedup: dict[str, dict[str, Any]] = {}
    for t in tasks:
        key = f"{t['level']}:{t['id']}"
        dedup.setdefault(key, t)
    return list(dedup.values())


def load_acceptance(case_dir: str) -> list[dict[str, Any]]:
    p = os.path.join(case_dir, "spec", "acceptance.json")
    if not os.path.isfile(p):
        return []
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("acceptance", [])


def relate(tasks: list[dict[str, Any]],
           acs: list[dict[str, Any]]) -> dict[str, Any]:
    """任务 ↔ AC 的双向指认。命中判据只有两条，都能说出理由。"""
    for t in tasks:
        text = " ".join([t["title"], t.get("goal", "")] + t["deliverables"])
        low = text.lower()
        t_routes = extract_routes(t.get("raw", "") or text)
        covers, why = [], []
        for a in acs:
            aid, atype = a.get("id", ""), a.get("type", "")
            hit = ""
            if a.get("file") and a["file"].lower() in low:
                hit = f"file:{a['file']}"
            elif a.get("needle") and a["needle"].lower() in low:
                hit = f"needle:{a['needle']}"
            elif a.get("route"):
                segs = route_segments(a["route"])
                if segs and all(s in low for s in segs):
                    hit = f"route:{a['route']}"
                else:
                    for r in t_routes:
                        if route_segments(r) and route_segments(r) == segs:
                            hit = f"route-seg:{a['route']}"
                            break
            if hit:
                covers.append(aid)
                why.append(f"{aid}<-{hit}")
        t["covers_ac"] = covers
        t["match_reasons"] = why
        t["auto_verifiable"] = bool(covers) and all(
            a.get("type") not in AC_NONAUTO for a in acs if a.get("id") in covers)

    covered = {aid for t in tasks for aid in t["covers_ac"]}
    ac_ids = {a.get("id", "") for a in acs}
    uncovered = [a for a in acs if a.get("id", "") not in covered]
    dangling = [a for a in acs
                if a.get("id", "") in covered and a.get("type") in AC_NONAUTO]

    plan_routes = {r for t in tasks
                   for r in extract_routes(t.get("raw", "") or " ".join(
                       [t["title"], t.get("goal", "")] + t["deliverables"]))}
    contract_routes = {a["route"].lower() for a in acs if a.get("route")}
    contract_segs = {frozenset(route_segments(r)) for r in contract_routes}
    orphan_routes = sorted(
        r for r in plan_routes
        if r not in contract_routes and route_segments(r)
        and not any(route_segments(r) == cs for cs in contract_segs))

    return {"uncovered_ac": uncovered, "dangling_ac": dangling,
            "plan_only_routes": orphan_routes}


def check_ac_declaration(tasks: list[dict[str, Any]],
                         acs: list[dict[str, Any]],
                         md: str = "") -> dict[str, Any] | None:
    """计划文本引用的 AC 编号，与契约实际条目比对。无引用就返回 None。

    这是 MumuSpec 六轮之间最容易漂移的位置：12-plan 写「AC‑001 至 AC‑008 全部通过」，
    而 acceptance.json 里的 id 可能是 TC1..TC6。对不上就列出来，不替它对齐。

    声明不只从表格抽：fs_002 的硬声明在「六、验收」说明正文里，不在任何任务行上，
    只看任务会漏掉最关键的证据，所以全文再扫一遍取并集。
    比对只按 id 尾部的数字（TC1 、AC-INFRA-01 都归为 1），因此只能发现「数量/编号
    对不上」，不能证明某条 AC 具体对应哪个任务。
    """
    declared = sorted({n for t in tasks for n in t.get("ac_refs", [])}
                      | {int(m.group(1)) for m in AC_REF_RE.finditer(md)})
    if not declared or not acs:
        return None
    ids = [a.get("id", "") for a in acs]
    numeric = {int(m.group(1)) for i in ids if (m := re.search(r"(\d+)$", i))}
    ranged = bool(AC_RANGE_RE.search(md)) or any(t.get("ac_range") for t in tasks)
    assumed = max(declared) if ranged else len(declared)
    return {
        "plan_ac_refs": declared,
        "plan_states_range": ranged,
        "plan_assumes_count": assumed,
        "contract_ac_count": len(acs),
        "contract_id_style": sorted({re.sub(r"\d+", "N", i) for i in ids}),
        "refs_absent_from_contract": [n for n in declared if n not in numeric],
    }


def build_payload(name: str, tasks: list[dict[str, Any]],
                  acs: list[dict[str, Any]], findings: dict[str, Any],
                  plan_path: str) -> dict[str, Any]:
    auto = sum(1 for t in tasks if t["auto_verifiable"])
    return {
        "name": name,
        "schema_version": 1,
        "source": plan_path,
        "ac_source": "spec/acceptance.json",
        "tasks": [{k: v for k, v in t.items() if k != "raw"} for t in tasks],
        "summary": {
            "task_count": len(tasks),
            "ac_count": len(acs),
            "tasks_with_ac": sum(1 for t in tasks if t["covers_ac"]),
            "auto_verifiable_tasks": auto,
            "uncovered_ac": len(findings["uncovered_ac"]),
            "plan_only_routes": len(findings["plan_only_routes"]),
        },
        "findings": {
            "uncovered_ac": [a.get("id", "") for a in findings["uncovered_ac"]],
            "dangling_ac": [a.get("id", "") for a in findings["dangling_ac"]],
            "plan_only_routes": findings["plan_only_routes"],
            "ac_declaration": findings.get("ac_declaration"),
        },
    }


def report(name: str, payload: dict[str, Any]) -> bool:
    s, f = payload["summary"], payload["findings"]
    print(f"[wbs] {name}: {s['task_count']} 任务 / {s['ac_count']} 条 AC"
          f"，{s['tasks_with_ac']} 个任务挂上了 AC，{s['auto_verifiable_tasks']} 个可自动判定")
    if f["uncovered_ac"]:
        print(f"[wbs] ⚠ 契约要求验收但无任务负责 ({len(f['uncovered_ac'])}): "
              + ", ".join(f["uncovered_ac"]))
    if f["dangling_ac"]:
        print(f"[wbs] ⚠ 任务挂上的 AC 自身不能自动判定: " + ", ".join(f["dangling_ac"]))
    if f["plan_only_routes"]:
        print(f"[wbs] ⚠ 计划提到接口但契约里没有对应 AC: "
              + ", ".join(f["plan_only_routes"][:8])
              + ("…" if len(f["plan_only_routes"]) > 8 else ""))
    decl = f.get("ac_declaration")
    if decl:
        if decl["plan_assumes_count"] != decl["contract_ac_count"] \
                or decl["refs_absent_from_contract"]:
            print(f"[wbs] ⚠ 计划引用的 AC 与契约不一致：计划假定 "
                  f"{decl['plan_assumes_count']} 条"
                  f"({'按区间最大值' if decl['plan_states_range'] else '按引用个数'})，"
                  f"契约实际 {decl['contract_ac_count']} 条"
                  f"（id 形式 {', '.join(decl['contract_id_style']) or '—'}）"
                  + (f"；引用了契约里不存在的编号 "
                     f"{', '.join(str(n) for n in decl['refs_absent_from_contract'])}" if
                     decl["refs_absent_from_contract"] else ""))
        else:
            print(f"[wbs] 计划引用的 AC 编号与契约数量一致"
                  f"（{decl['contract_ac_count']} 条）")
    if not (f["uncovered_ac"] or f["dangling_ac"] or f["plan_only_routes"] or decl):
        print("[wbs] 任务与 AC 双向指认闭合，无缺口")
    return s["task_count"] > 0


def compile_case(name: str, check_only: bool = False) -> int:
    case_dir = os.path.join(CASES_DIR, name)
    plan_rel = os.path.join("cases", name, PLAN_REL)
    plan = os.path.join(case_dir, PLAN_REL)
    if not os.path.isdir(case_dir):
        print(f"[wbs] ❌ case 不存在: {name}")
        return 2
    if not os.path.isfile(plan):
        print(f"[wbs] {name}: 无 {plan_rel}，不可编译（不拿 spec.md 凑任务）")
        return 3

    with open(plan, encoding="utf-8") as fh:
        md = fh.read()
    tasks = parse_plan(md)
    if not tasks:
        print(f"[wbs] ❌ {name}: 12-plan 里解析不出任务（里程碑表格式可能不合约定）")
        return 4

    acs = load_acceptance(case_dir)
    if not acs:
        print(f"[wbs] ⚠ {name}: {len(tasks)} 个任务，但没有 acceptance.json，"
              f"无法建立判据关联")

    findings = relate(tasks, acs)
    findings["ac_declaration"] = check_ac_declaration(tasks, acs, md)
    payload = build_payload(name, tasks, acs, findings, plan_rel)
    ok = report(name, payload)

    if check_only:
        return 0 if ok else 1
    out = os.path.join(case_dir, WBS_REL)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"[wbs] 已写出 cases/{os.path.join(name, WBS_REL)}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="12-plan + acceptance → spec/wbs.json")
    ap.add_argument("--name", help="case 名，如 music_player")
    ap.add_argument("--all", action="store_true", help="扫全部 case")
    ap.add_argument("--check", action="store_true", help="只出门禁报告，不写文件")
    args = ap.parse_args()

    if args.all:
        names = sorted(d for d in os.listdir(CASES_DIR)
                       if os.path.isdir(os.path.join(CASES_DIR, d)))
        compiled, skipped = [], []
        for n in names:
            rc = compile_case(n, check_only=args.check)
            (compiled if rc == 0 else skipped).append((n, rc))
        print("=" * 64)
        print(f"[wbs] 共 {len(names)} 个 case：可编译 {len(compiled)}，"
              f"无 12-plan 或其他 {len(skipped)}")
        by_rc: dict[int, list[str]] = {}
        for n, rc in skipped:
            by_rc.setdefault(rc, []).append(n)
        for rc, ns in sorted(by_rc.items()):
            label = {3: "无 12-plan", 4: "12-plan 解析不出任务",
                     2: "case 不存在"}.get(rc, f"rc={rc}")
            print(f"  [{label}] {len(ns)}: " + ", ".join(ns[:10])
                  + ("…" if len(ns) > 10 else ""))
        return 0

    if not args.name:
        ap.error("需要 --name <case> 或 --all")
    return compile_case(args.name, check_only=args.check)


if __name__ == "__main__":
    sys.exit(main())
