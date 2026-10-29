"""需求模块 —— 最普通的 CRUD，用来验证 store + REST 约定。"""
import time


def list_reqs(ctx, params, body):
    rows = ctx.store.all("reqs")
    q = (params.get("q") or "").lower()
    if q:
        rows = [r for r in rows if q in r.get("title", "").lower() or q in r["id"].lower()]
    return 200, {"items": rows, "total": len(rows)}


def create_req(ctx, params, body):
    title = (body or {}).get("title", "").strip()
    if not title:
        return 400, {"error": "title 必填"}
    if len(title) > 120:
        return 400, {"error": "title 太长"}
    from modules.workspaces import registry
    ws = (body or {}).get("workspace_id", "pomodoro")
    if ws not in registry():
        return 400, {"error": f"没有工作区 {ws}"}

    rid = ctx.store.new_id("reqs", "REQ")
    row = ctx.store.put("reqs", {
        "id": rid, "title": title,
        "workspace_id": ws,
        "source": (body or {}).get("source", "手工"),
        "priority": (body or {}).get("priority", "P2"),
        "acceptance": (body or {}).get("acceptance", ""),
        "status": "待分析",
        "spec_id": None,
    })
    ctx.bus.publish({"type": "req_created", "req": rid, "title": title})
    return 201, {"item": row}


def get_req(ctx, params, body):
    row = ctx.store.get("reqs", params["id"])
    if not row:
        return 404, {"error": "需求不存在"}
    return 200, {"item": row}


def patch_req(ctx, params, body):
    allowed = {"title", "priority", "acceptance", "status", "spec_id", "workspace_id"}
    kv = {k: v for k, v in (body or {}).items() if k in allowed}
    if not kv:
        return 400, {"error": "没有可改的字段"}
    row = ctx.store.patch("reqs", params["id"], **kv)
    if not row:
        return 404, {"error": "需求不存在"}
    ctx.bus.publish({"type": "req_updated", "req": row["id"], "changed": list(kv)})
    return 200, {"item": row}


def stats(ctx, params, body):
    rows = ctx.store.all("reqs")
    by = {}
    for r in rows:
        by[r.get("status", "?")] = by.get(r.get("status", "?"), 0) + 1
    return 200, {"total": len(rows), "by_status": by}
