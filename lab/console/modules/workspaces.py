"""工作区模块 —— 需求绑定到「哪个仓库 + 哪个门禁」。

这是「输入需求 → 生成代码」的最后一环：
前面三步产出的 Spec / WBS 再漂亮，如果跑的还是别的仓库，那都是文档。

设计：直接复用 demo/shared/tasks.json 的条目作为工作区注册表。
一条 = 一个工作区（fixture）+ 一个门禁（check）+ 一份默认任务书。
"""
import json
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent.parent / "demo"


def registry():
    p = DEMO / "shared" / "tasks.json"
    return {t["id"]: t for t in json.loads(p.read_text(encoding="utf-8"))["tasks"]}


def list_workspaces(ctx, params, body):
    out = []
    for wid, w in registry().items():
        fixture = (DEMO / w["fixture"]).resolve()
        files = sorted(f.name for f in fixture.iterdir() if f.is_file()) if fixture.exists() else []
        out.append({
            "id": wid,
            "name": w["name"],
            "fixture": w["fixture"],
            "check": w["check"],
            "files": files,
            "note": w.get("note", ""),
            "runs": len([r for r in ctx.store.all("runs") if r.get("task") == wid]),
        })
    return 200, {"items": out}


def files(ctx, params, body):
    """看一个工作区里现在有哪些文件、多大"""
    wid = params.get("id")
    reg = registry()
    if wid not in reg:
        return 404, {"error": f"没有工作区 {wid}"}
    fixture = (DEMO / reg[wid]["fixture"]).resolve()
    out = {}
    for f in sorted(fixture.iterdir()):
        if f.is_file():
            txt = f.read_text(encoding="utf-8", errors="replace")
            out[f.name] = {"bytes": len(txt.encode()), "lines": len(txt.splitlines())}
    return 200, {"id": wid, "fixture": reg[wid]["fixture"], "files": out}
