#!/usr/bin/env python3
"""Spec 链路自检 —— 生成 → 依赖序 → 审核 → 失效传播 → 重生成

固定用 engine=template：快、确定、不烧钱。
LLM 引擎（DeepSeek）手工验，见 platform/真实模型实测.md。
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8899"
OK, FAIL = [], []


def call(method, path, body=None, timeout=20):
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
    print("\n═══ Spec 链路自检 ═══\n")

    print("[1] 建需求")
    _, r = call("POST", "/api/reqs", {
        "title": "会话超时自动转人工",
        "acceptance": "超时 90s 触发；转人工后不丢上下文"})
    req = r["item"]["id"]
    check("需求创建", bool(req), r)
    print(f"       → {req}")

    print("\n[2] 生成 14 份（batch 模式）")
    code, r = call("POST", "/api/specs/generate", {"req_id": req, "mode": "batch", "engine": "template"})
    check("生成已受理", code == 202 and r.get("total") == 14, r)

    for _ in range(100):
        _, p = call("GET", f"/api/specs/progress?req_id={req}")
        if p.get("generated") == 14:
            break
        time.sleep(0.1)
    check("14 份全部生成", p.get("generated") == 14, p)

    print("\n[3] 依赖顺序真的被遵守了吗")
    _, g = call("GET", f"/api/specs/graph?req_id={req}")
    _, lst = call("GET", f"/api/specs?req_id={req}")
    order = {}
    seq = 0
    for grp in lst["groups"]:
        for it in grp["items"]:
            order[it["n"]] = seq; seq += 1
    bad = []
    for e in g["edges"]:
        a = int(e["from"].split("-S")[-1]); b = int(e["to"].split("-S")[-1])
        if order[a] > order[b]:
            bad.append(f"S{a} 应该在 S{b} 之前")
    check("上游都排在下游之前", not bad, bad[:3])
    check("依赖边数量正确", len(g["edges"]) == sum(len(x["dep"]) for x in
        [i for grp in lst["groups"] for i in grp["items"]]), len(g["edges"]))
    print(f"       → {len(g['nodes'])} 节点 / {len(g['edges'])} 条依赖边")

    print("\n[4] 审核 3 份")
    sid3 = f"{req}-S03"
    code, r = call("POST", f"/api/specs/{sid3}/review", {"decision": "approve", "by": "张伟"})
    check("通过一份", code == 200 and r["item"]["status"] == "已审", r)
    sid5 = f"{req}-S05"
    code, r = call("POST", f"/api/specs/{sid5}/review",
                   {"decision": "request_change", "comment": "功能范围写得太大"})
    check("打回一份", code == 200 and r["item"]["status"] == "需修改", r)
    code, r = call("POST", f"/api/specs/{sid3}/review", {"decision": "approve"})
    check("已审的不能再审（状态机）", code == 409, r)

    print("\n[5] 改上游 → 下游自动标 stale")
    code, r = call("POST", f"/api/specs/{sid3}/regenerate")
    affected = r.get("stale_affected", [])
    check("重生成成功", code == 200 and r["item"]["version"] == 2, r)
    check("下游被标 stale", len(affected) > 0, affected)
    print(f"       → S03 变了，影响 {affected}")

    _, lst2 = call("GET", f"/api/specs?req_id={req}")
    stale = [i for grp in lst2["groups"] for i in grp["items"] if i["status"] == "需修改"]
    check("需修改的数量 = 传播范围 + 被打回的那份",
          len(stale) >= len(affected), f"{len(stale)} vs {len(affected)}")

    print("\n[6] 汇总")
    _, p2 = call("GET", f"/api/specs/progress?req_id={req}")
    print(f"       → 已生成 {p2['generated']}/14，已审 {p2['reviewed']}，"
          f"状态分布 {lst2['by_status']}")

    print("\n[7] 逐份审模式：生成一份就停下等人")
    _, r = call("POST", "/api/reqs", {"title": "登录失败 5 次锁定", "acceptance": "按用户维度计数"})
    req2 = r["item"]["id"]
    call("POST", "/api/specs/generate", {"req_id": req2, "mode": "stepwise", "engine": "template"})
    time.sleep(1.2)
    _, p3 = call("GET", f"/api/specs/progress?req_id={req2}")
    check("只生成了 1 份就停下（真的阻塞了）", p3.get("generated") == 1, p3)
    print(f"       → 生成 {p3.get('generated')}/14，卡在第一份等人审")

    code, _ = call("POST", f"/api/specs/{req2}-S01/review", {"decision": "approve", "by": "李娜"})
    check("审第一份", code == 200)
    time.sleep(1.2)
    _, p4 = call("GET", f"/api/specs/progress?req_id={req2}")
    check("审完之后才继续生成第二份", p4.get("generated") == 2, p4)
    print(f"       → 现在 {p4.get('generated')}/14")

    print("\n" + "═" * 46)
    print(f"  {len(OK)} 通过 / {len(FAIL)} 失败")
    if FAIL:
        print("  失败项：" + "、".join(FAIL))
    print("═" * 46 + "\n")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
