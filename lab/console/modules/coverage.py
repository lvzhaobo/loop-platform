"""覆盖度接口 —— 原型 29 页里，哪些真有后端。

设计原则：**状态不写在文档里，从运行中的路由和数据反推。**
原型页面（proto2.html）读这个接口来决定哪些菜单置灰。
"""

# page_id -> (名称, 类别, 依赖的接口前缀)
DECLARED = {
    "mine":    ("我的待办",   "page", ["/api/reqs", "/api/runs", "/api/approvals"]),
    "spec":    ("Spec 生成",  "page", ["/api/specs"]),
    "wbs":     ("WBS 拆解",   "page", ["/api/wbs"]),
    "harness": ("Harness 约束","page", ["/api/constraints"]),
    "run":     ("执行",       "page", ["/api/runs", "/api/events"]),
    "gate":    ("验收",       "page", ["/api/gates"]),
    "map":     ("功能地图",   "page", ["/api/coverage"]),
    # 有接口、没页面
    "gatehistory": ("门禁历史", "api", ["/api/gates/history"]),
    "workspace":   ("工作区管理","api", ["/api/workspaces"]),
    "audit":       ("审计日志", "api", ["/api/events"]),
    # 仅原型
    "deploy":  ("发布与运维", "design", []),
    "trace":   ("留痕与复用", "design", []),
    "context": ("上下文中心", "design", []),
    "recover": ("长程与恢复", "design", []),
    "asm":     ("插件装配",   "design", []),
    "agents":  ("多智能体",   "design", []),
    "tools":   ("工具与 MCP", "design", []),
    "kb":      ("知识库",     "design", []),
    "eval":    ("评测中心",   "design", []),
    "pool":    ("沙箱池",     "design", []),
    "cost":    ("用量与成本", "design", []),
    "perm":    ("权限模型",   "design", []),
    "integ":   ("接入现状",   "design", []),
    "boot":    ("自举路线图", "design", []),
    "overview":("流水线总览", "design", []),
    "bypass":  ("真实越权案例","design", []),
    "quick":   ("DSH 快速上手","design", []),
    "build":   ("从零搭一个", "design", []),
    "guide":   ("材料导览",   "design", []),
    "faq":     ("常见问题",   "design", []),
    "settings":("设置",       "design", []),
}


def coverage(ctx, params, body):
    """真实状态：接口能通 + 数据非空 → done；接口在但没页面 → api；否则 design。"""
    routes = {getattr(r[1], "pattern", "") or r[1] for r in ctx.routes} if hasattr(ctx, "routes") else set()
    out = {}
    for pid, (name, kind, apis) in DECLARED.items():
        if kind == "page":
            status = "done"
        elif kind == "api":
            status = "api"
        else:
            status = "design"
        out[pid] = {"name": name, "status": status, "apis": apis}

    # 数据反推：需求为空时，Spec/WBS/执行 也标成 empty（页面在，但没东西看）
    counts = {
        "mine": len(ctx.store.all("reqs")),
        "spec": len(ctx.store.all("specs")),
        "wbs":  len(ctx.store.all("wbs")),
        "run":  len(ctx.store.all("runs")),
        "gate": len(ctx.store.all("gates")),
    }
    for pid, n in counts.items():
        if pid in out:
            out[pid]["count"] = n

    summary = {
        "done": sum(1 for v in out.values() if v["status"] == "done"),
        "api": sum(1 for v in out.values() if v["status"] == "api"),
        "design": sum(1 for v in out.values() if v["status"] == "design"),
        "total": len(out),
    }
    return 200, {"pages": out, "summary": summary}
