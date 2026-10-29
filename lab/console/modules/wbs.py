"""WBS 模块 —— Spec → 任务卡 → 回写 Jira。

两条硬规矩：
  ① 每个任务必须挂「来源 Spec 章节」——半年后能找回它为什么存在
  ② 回写 Jira 只放引用，不复制 Spec 全文——避免两处不一致
"""
import time

# 从哪几份 Spec 拆任务，以及怎么拆
SPLIT_RULES = [
    (4,  "用户故事与验收标准", ["主流程实现", "异常分支处理"]),
    (10, "页面与交互规格",     ["页面结构改造", "交互状态处理"]),
    (9,  "API 接口规格",       ["接口契约实现", "字段校验"]),
    (11, "错误与边界",         ["边界条件补全"]),
    (12, "测试策略与质量门禁", ["补测试用例"]),
]


def _gen(ctx, req_id):
    specs = {s["n"]: s for s in ctx.store.all("specs", req_id=req_id)}
    rows, n = [], 0
    for spec_n, spec_name, titles in SPLIT_RULES:
        if spec_n not in specs:
            continue
        for t in titles:
            n += 1
            rows.append({
                "id": f"{req_id}-W{n:02d}",
                "req_id": req_id,
                "title": t,
                "spec_n": spec_n,
                "spec": f"S{spec_n:02d} {spec_name}",
                "est": "0.5d" if n % 2 else "1d",
                "dep": [] if n == 1 else [f"{req_id}-W{n-1:02d}"],
                "jira": None,
                "status": "待开始",
                "owner": None,
            })
    # 依赖：同一个 Spec 拆出来的任务串起来
    by_spec = {}
    for r in rows:
        by_spec.setdefault(r["spec_n"], []).append(r["id"])
    for r in rows:
        grp = by_spec[r["spec_n"]]
        i = grp.index(r["id"])
        r["dep"] = ([grp[i-1]] if i > 0 else [])
    return rows


def generate(ctx, params, body):
    body = body or {}
    req_id = body.get("req_id")
    if not req_id or not ctx.store.get("reqs", req_id):
        return 400, {"error": "req_id 不存在"}
    specs = ctx.store.all("specs", req_id=req_id)
    if len(specs) < 5:
        return 409, {"error": "Spec 还没生成齐，先跑 /api/specs/generate"}
    rows = _gen(ctx, req_id)
    for r in rows:
        ctx.store.put("wbs", r)
    ctx.bus.publish({"type": "wbs_generated", "req": req_id, "count": len(rows)})
    return 201, {"req": req_id, "count": len(rows), "items": rows}


def list_wbs(ctx, params, body):
    req_id = params.get("req_id")
    rows = ctx.store.all("wbs", req_id=req_id) if req_id else ctx.store.all("wbs")
    return 200, {"items": rows, "total": len(rows)}


def push_jira(ctx, params, body):
    """回写 Jira：只放引用，不复制 Spec 全文。这里是桩，真实要调 Jira API。"""
    wid = params["id"]
    row = ctx.store.get("wbs", wid)
    if not row:
        return 404, {"error": "任务不存在"}
    if row.get("jira"):
        return 409, {"error": f"已经回写过：{row['jira']}"}
    key = "PROJ-" + str(2100 + len(ctx.store.all("wbs")) + hash(wid) % 90)
    ctx.store.patch("wbs", wid, jira=key, status="已回写", pushed_at=time.time())
    ctx.bus.publish({"type": "jira_pushed", "wbs": wid, "jira": key})
    return 200, {"id": wid, "jira": key,
                 "payload": {"summary": row["title"],
                             "labels": ["ai-coding", wid],
                             "description_ref": row["spec"]}}


def push_all(ctx, params, body):
    body = body or {}
    req_id = body.get("req_id")
    rows = [r for r in ctx.store.all("wbs", req_id=req_id) if not r.get("jira")]
    pushed = []
    for r in rows:
        _, res = push_jira(ctx, {"id": r["id"]}, {})
        if "jira" in res:
            pushed.append({"id": r["id"], "jira": res["jira"]})
    return 200, {"pushed": pushed, "count": len(pushed)}


def stale_check(ctx, params, body):
    """Spec 变了，哪些任务要重拆（GET，所以从 query 取）"""
    body = body or {}
    req_id = params.get("req_id") or body.get("req_id")
    rows = ctx.store.all("wbs", req_id=req_id)
    specs = {s["n"]: s for s in ctx.store.all("specs", req_id=req_id)}
    out = []
    for r in rows:
        s = specs.get(r["spec_n"])
        if not s:
            continue
        # ① 上游被标了"需修改"（依赖传播）
        if s["status"] == "需修改":
            out.append({"wbs": r["id"], "title": r["title"],
                        "because": f"S{s['n']:02d} {s['name']} 被标需修改"})
        # ② 上游重新生成过，比这张卡还新 —— 卡就旧了
        elif s.get("generated_at", 0) > r.get("created_at", 0):
            out.append({"wbs": r["id"], "title": r["title"],
                        "because": f"S{s['n']:02d} 已重新生成 v{s.get('version')}"})
    return 200, {"stale": out, "count": len(out)}
