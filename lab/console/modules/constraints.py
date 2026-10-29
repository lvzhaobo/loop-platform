"""约束模块 —— 扫描仓库里真实的约束文件，按四象限归类，跑冲突检测。

读的是 demo/ 下的真文件，不是假数据。所以这一页能当场证明"我在看你的仓库"。
"""
import json
import re
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent.parent / "demo"

# 文件名模式 → (象限标签, 作用域, 强制性)
RULES = [
    (r"^AGENTS\.md$",                 "指令·全局",     "全局", "概率"),
    (r"^CLAUDE\.md$",                 "指令·全局",     "全局", "概率"),
    (r"^persona\.md$",                "人格·全局",     "全局", "概率"),
    (r"^permissions?\.ya?ml$",        "权限·全局",     "全局", "确定"),
    (r"^sandbox\.ya?ml$",             "沙箱·全局",     "全局", "确定"),
    (r"^approvals?\.ya?ml$",          "审批策略",      "任务", "确定"),
    (r"^tasks?(-.*)?\.md$",           "任务书",        "任务", "概率"),
    (r"^check(-.*)?\.py$",            "门禁",          "任务", "确定"),
    (r"^SKILL\.md$",                  "能力",          "任务", "概率"),
    (r"^cordis\.patch\.ya?ml$",       "装配覆盖",      "全局", "确定"),
]

SKIP_DIRS = {"__pycache__", "node_modules", ".git", "runs", "data", "web"}


def _classify(name):
    for pat, quad, scope, force in RULES:
        if re.match(pat, name):
            return quad, scope, force
    return None


def _scan(max_files=200):
    found = []
    for p in sorted(DEMO.rglob("*")):
        if not p.is_file() or p.suffix not in (".md", ".yml", ".yaml", ".py", ".json"):
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        c = _classify(p.name)
        if not c:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        lines = len(text.splitlines())
        found.append({
            "path": str(p.relative_to(DEMO)),
            "name": p.name,
            "quad": c[0], "scope": c[1], "force": c[2],
            "lines": lines,
            "tok": 0 if c[2] == "确定" else max(1, int(len(text) / 2.4)),
        })
        if len(found) >= max_files:
            break
    return found


def conflicts(files):
    out = []
    for f in files:
        if f["force"] == "概率" and f["scope"] == "全局" and f["lines"] > 30:
            out.append({"lv": "warn", "path": f["path"],
                        "msg": f"{f['name']} 有 {f['lines']} 行，全局·概率超过 30 行会稀释上下文"})
        if f["force"] == "确定" and f["lines"] == 0:
            out.append({"lv": "bad", "path": f["path"], "msg": "确定性约束文件是空的"})
    # AGENTS.md 说"任意命令"但权限层受限 → 经典冲突
    agents = next((f for f in files if f["name"] == "AGENTS.md"), None)
    perms = next((f for f in files if f["force"] == "确定" and f["scope"] == "全局"), None)
    if agents and perms:
        try:
            txt = (DEMO / agents["path"]).read_text(encoding="utf-8")
        except Exception:
            txt = ""
        if re.search(r"任意命令|any command", txt):
            out.append({"lv": "bad", "path": agents["path"],
                        "msg": f"{agents['name']} 写了「可以执行任意命令」，但 {perms['name']} 会拦——"
                               f"实际以权限层为准，这句是误导"})
    return out


# ---------- HTTP ----------
def list_constraints(ctx, params, body):
    files = _scan()
    quads = {}
    for f in files:
        key = f"{f['scope']} · {f['force']}"
        quads.setdefault(key, []).append(f)
    total_tok = sum(f["tok"] for f in files)
    return 200, {"files": files, "by_quadrant": quads,
                 "total_tokens": total_tok,
                 "conflicts": conflicts(files)}


def check(ctx, params, body):
    files = _scan()
    c = conflicts(files)
    ctx.bus.publish({"type": "constraints_checked", "conflicts": len(c)})
    return 200, {"ok": not any(x["lv"] == "bad" for x in c),
                 "total": len(files), "conflicts": c}


def patch_file(ctx, params, body):
    body = body or {}
    path = body.get("path")
    if not path:
        return 400, {"error": "path 必填"}
    p = (DEMO / path).resolve()
    if not str(p).startswith(str(DEMO)) or not p.is_file():
        return 400, {"error": "只能改 demo/ 里的文件"}
    if body.get("content") is None:
        return 400, {"error": "content 必填"}
    p.write_text(body["content"], encoding="utf-8")
    ctx.bus.publish({"type": "constraint_updated", "path": path})
    return 200, {"ok": True, "path": path, "lines": len(body["content"].splitlines())}
