#!/usr/bin/env python3
"""门禁 / 约束 / WBS 三个模块的自检。"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8899"
DEMO = Path(__file__).resolve().parent.parent / "demo"
OK, FAIL = [], []


def call(method, path, body=None, timeout=25):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def check(name, cond, detail=""):
    (OK if cond else FAIL).append(name)
    print(("  ✅ " if cond else "  ❌ ") + name + ("" if cond else f"  ← {detail}"))


def main():
    print("\n═══ 门禁 / 约束 / WBS 自检 ═══\n")
    subprocess.run([sys.executable, str(DEMO / "reset.py")], capture_output=True)

    print("[1] 门禁逐条断言（番茄钟）")
    code, r = call("POST", "/api/gates/run", {"task": "pomodoro"})
    g = r.get("gate", {})
    check("返回逐条断言", len(g.get("assertions", [])) == 7, len(g.get("assertions", [])))
    check("import 模式（不是退化成 exit code）", g.get("mode") == "import", g.get("mode"))
    check("红：4/7", g.get("passed") == 4 and g.get("exit_code") == 1,
          f"{g.get('passed')}/{g.get('total')}")
    a = g["assertions"][0]
    check("断言带 name/ok/hint", all(k in a for k in ("name", "ok", "hint")), a)
    print(f"       → {g['passed']}/{g['total']} · 第 1 条：{a['name'][:24]}")

    print("\n[2] 门禁逐条断言（智能客服）")
    code, r = call("POST", "/api/gates/run", {"task": "cs"})
    g2 = r.get("gate", {})
    check("客服门禁 5/9", g2.get("passed") == 5 and g2.get("total") == 9,
          f"{g2.get('passed')}/{g2.get('total')}")
    print(f"       → {g2['passed']}/{g2['total']}")

    print("\n[3] 约束四象限（读真实文件）")
    code, r = call("GET", "/api/constraints")
    check("扫到了文件", len(r.get("files", [])) > 0, r.get("total"))
    quads = r.get("by_quadrant", {})
    check("至少分到 2 个象限", len(quads) >= 2, list(quads))
    check("确定性文件不算 token", any(f["tok"] == 0 for f in r["files"]), "")
    print(f"       → {len(r['files'])} 个文件 / {len(quads)} 象限 / "
          f"{r['total_tokens']} tok（确定性的不计）")
    for k, v in quads.items():
        print(f"         {k}：{len(v)} 个")

    print("\n[4] 冲突检测")
    code, r2 = call("POST", "/api/constraints/check")
    check("检测接口返回 ok 字段", "ok" in r2, r2)
    print(f"       → {r2['total']} 个文件，{len(r2['conflicts'])} 条冲突")

    print("\n[5] WBS：Spec → 任务卡")
    _, r = call("POST", "/api/reqs", {"title": "订单列表首屏优化", "acceptance": "P95 < 1.2s"})
    req = r["item"]["id"]
    call("POST", "/api/specs/generate", {"req_id": req, "mode": "batch"})
    for _ in range(60):
        _, p = call("GET", f"/api/specs/progress?req_id={req}")
        if p.get("generated") == 14:
            break
        time.sleep(0.1)
    code, r = call("POST", "/api/wbs/generate", {"req_id": req})
    items = r.get("items", [])
    check("拆出任务卡", len(items) >= 5, r)
    check("每张卡都挂来源 Spec", all(i.get("spec") for i in items), "")
    print(f"       → {len(items)} 张卡，来源示例：{items[0]['spec']}")

    print("\n[6] 回写 Jira（只放引用）")
    wid = items[0]["id"]
    code, r = call("POST", f"/api/wbs/{wid}/jira")
    key = r.get("jira")
    check("拿到 jira key", code == 200 and key, r)
    check("payload 里是引用不是全文", "description_ref" in r.get("payload", {}), r.get("payload"))
    code2, r2 = call("POST", f"/api/wbs/{wid}/jira")
    check("重复回写被拒（幂等）", code2 == 409, r2)
    print(f"       → {wid} → {key}")

    print("\n[7] Spec 变了 → WBS 里的卡要重拆")
    call("POST", f"/api/specs/{req}-S04/regenerate")
    code, r = call("GET", f"/api/wbs/stale?req_id={req}")
    check("能查出生效的卡", r.get("count", 0) > 0, r)
    print(f"       → {r['count']} 张卡受影响：{[x['because'] for x in r['stale'][:2]]}")

    subprocess.run([sys.executable, str(DEMO / "reset.py")], capture_output=True)
    print("\n" + "═" * 46)
    print(f"  {len(OK)} 通过 / {len(FAIL)} 失败")
    if FAIL:
        print("  失败项：" + "、".join(FAIL))
    print("═" * 46 + "\n")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
