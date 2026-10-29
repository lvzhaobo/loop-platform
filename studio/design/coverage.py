"""覆盖度 —— 原型 29 页里，哪些真有后端。

状态不写在文档里，从 Flask 的 url_map 反推：
  page   → done（页面在 + 接口在）
  api    → 有接口没页面
  design → 只有设计
"""
DECLARED = {
    # page：有真实页面
    "mine":    ("我的待办",   "page", ["/api/requirement", "/api/run"]),
    "spec":    ("Spec 生成",  "page", ["/api/spec"]),
    "wbs":     ("WBS 拆解",   "page", ["/api/wbs"]),
    "harness": ("Harness 约束","page", ["/api/constraint"]),
    "run":     ("执行",       "page", ["/api/run", "/api/maker"]),
    "gate":    ("验收",       "page", ["/api/gate"]),
    "design":  ("设计稿",     "page", ["/design"]),
    # api：有接口，没页面
    "gatehistory": ("门禁历史", "api", ["/api/gate"]),
    "workspace":   ("工作区",   "api", ["/api/profile"]),
    "audit":       ("审计日志", "api", ["/api/event"]),
    # design：仅原型
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


def build_coverage(app):
    """从真实路由反推：declared 里的 api 只要有一个在 url_map 上，就算有接口。"""
    rules = {r.rule for r in app.url_map.iter_rules()}
    pages = {}
    for pid, (name, kind, apis) in DECLARED.items():
        if kind == "page":
            status = "done" if (not apis or any(a in rules for a in apis)) else "api"
        elif kind == "api":
            status = "api" if any(a in rules for a in apis) else "design"
        else:
            status = "design"
        pages[pid] = {"name": name, "status": status, "apis": apis}
    return {"pages": pages, "summary": {
        "done": sum(1 for v in pages.values() if v["status"] == "done"),
        "api": sum(1 for v in pages.values() if v["status"] == "api"),
        "design": sum(1 for v in pages.values() if v["status"] == "design"),
        "total": len(pages),
    }}
