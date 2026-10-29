"""门禁模块 —— 从「一个 exit code」变成「N 条具体断言」。

为什么重要：exit code 只告诉你"没过"，断言列表告诉你"哪一条没过、为什么"。
验收页要的就是后者。

实现上直接 import 门禁脚本里的 CHECKS 列表逐条跑，
比解析 stdout 可靠——不用跟输出格式耦合。
"""
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent.parent / "demo"


def _registry():
    p = DEMO / "shared" / "tasks.json"
    return {t["id"]: t for t in json.loads(p.read_text(encoding="utf-8"))["tasks"]}


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(f"gate_{path.stem}_{int(time.time()*1000)}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_task(task_id: str):
    reg = _registry()
    if task_id not in reg:
        return None, {"error": f"没有任务 {task_id}"}
    check = (DEMO / reg[task_id]["check"]).resolve()
    if not check.exists():
        return None, {"error": f"门禁脚本不存在：{check}"}

    out = {"task": task_id, "script": str(check.relative_to(DEMO)), "at": time.time()}
    try:
        mod = _load_module(check)
        # 兼容两种写法：CHECKS 或 checks；(name, fn) 或 (name, fn, hint)
        checks = getattr(mod, "CHECKS", None) or getattr(mod, "checks", None)
        if not checks:
            raise RuntimeError("门禁里没有 CHECKS / checks 列表")
        rows, bad = [], 0
        for i, item in enumerate(checks, 1):
            name, fn = item[0], item[1]
            hint = item[2] if len(item) > 2 else ""
            try:
                res = fn()
                ok, detail = (res if isinstance(res, tuple) else (res, ""))
            except Exception as e:
                ok, detail = False, f"{type(e).__name__}: {e}"
            if not ok:
                bad += 1
            rows.append({"n": i, "name": name, "ok": bool(ok),
                         "detail": detail or "", "hint": hint or ""})
        out.update(exit_code=0 if bad == 0 else 1, passed=len(rows) - bad,
                   total=len(rows), assertions=rows, mode="import")
    except Exception as e:
        # 兜底：脚本不是 import 友好的，就跑子进程，只拿得到 exit code
        p = subprocess.run([sys.executable, str(check)], capture_output=True, text=True)
        out.update(exit_code=p.returncode, passed=None, total=None,
                   assertions=[], mode="subprocess",
                   note=f"逐条解析失败（{type(e).__name__}: {e}），退回 exit code")
    return out, None


# ---------- HTTP ----------
def run(ctx, params, body):
    body = body or {}
    task_id = body.get("task") or params.get("task") or "pomodoro"
    res, err = run_task(task_id)
    if err:
        return 400, err
    rec = ctx.store.put("gates", {"id": f"GATE-{int(time.time()*1000)}", **res})
    ctx.bus.publish({"type": "gate_result", "task": task_id,
                     "exit_code": res["exit_code"], "passed": res.get("passed"),
                     "total": res.get("total")})
    return 200, {"gate": rec}


def latest(ctx, params, body):
    task_id = params.get("task") or "pomodoro"
    rows = [r for r in ctx.store.all("gates") if r.get("task") == task_id]
    if not rows:
        return 404, {"error": "还没有跑过门禁"}
    rows.sort(key=lambda r: r["at"])
    return 200, {"gate": rows[-1]}


def history(ctx, params, body):
    task_id = params.get("task")
    rows = [r for r in ctx.store.all("gates")
            if not task_id or r.get("task") == task_id]
    rows.sort(key=lambda r: r["at"], reverse=True)
    return 200, {"items": rows[:50], "total": len(rows)}


def tasks(ctx, params, body):
    return 200, {"items": [{"id": k, "name": v["name"], "check": v["check"]}
                           for k, v in _registry().items()]}
