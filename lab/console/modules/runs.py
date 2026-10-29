"""执行模块 —— 起线程跑 loop，事件全部走总线。

关键点：**不重写 loop**。直接复用 demo/A-python 的实现，
证明"平台层"和"harness 层"能干净地分开。
"""
import sys
import threading
import time
import uuid
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent.parent / "demo"
HARNESS = DEMO / "A-python"
sys.path.insert(0, str(HARNESS))

import approve      # noqa: E402  demo 的 CLI 版审批（不用）
import compact      # noqa: E402
import config       # noqa: E402
import llm          # noqa: E402
import loop as agent_loop   # noqa: E402
import policy       # noqa: E402
import session as agent_session  # noqa: E402
import tools as agent_tools      # noqa: E402

from modules import approvals     # noqa: E402

RUNS = {}          # run_id -> {"thread","cancel","status"}
_lock = threading.Lock()


def _registry():
    import json
    p = DEMO / "shared" / "tasks.json"
    return {t["id"]: t for t in json.loads(p.read_text(encoding="utf-8"))["tasks"]}


def _worker(ctx, run_id, task, prompt):
    cfg = config.load()
    cfg["MOCK"] = "true" if ctx.mock else cfg.get("MOCK", "false")
    cfg["WORKSPACE_PATH"] = (DEMO / task["fixture"]).resolve()
    cfg["CHECK_PATH"] = (DEMO / task["check"]).resolve()
    cfg["MOCK_SCRIPT"] = str((DEMO / task.get("mock")).resolve())

    sess = agent_session.Session(ctx.data_dir / "sessions" / f"{run_id}.jsonl")
    prov = approvals.HttpApprover(ctx.bus, run_id)
    tl = agent_tools.Tools(cfg, sess, prov, emit=ctx.bus.publish,
                           check_path=cfg["CHECK_PATH"])

    def emit(ev):
        ev["run"] = run_id
        ctx.bus.publish(ev)

    try:
        res = agent_loop.run(cfg, llm.LLM(cfg), tl, sess,
                             policy.Budget(cfg), prompt,
                             emit=emit, cancel=RUNS[run_id]["cancel"])
        ctx.store.patch("runs", run_id,
                        status="done" if res["status"] == "done" else res["status"],
                        gate=res.get("gate"), steps=res.get("steps"),
                        denied=res.get("denied"), finished_at=time.time())
    except Exception as e:
        emit({"type": "error", "message": f"{type(e).__name__}: {e}"})
        ctx.store.patch("runs", run_id, status="error", error=str(e))
    finally:
        with _lock:
            RUNS.pop(run_id, None)
        emit({"type": "run_closed"})


def compose_prompt(ctx, req, task):
    """把「需求 + 已审 Spec + WBS 任务 + 工作区约定」拼成一次任务的 prompt。

    这是链路里最容易断的一环：前面三步产出的东西，必须真的喂给 agent，
    否则 Spec 和 WBS 就只是文档，不参与执行。
    """
    parts = [f"# 任务：{req['title']}", ""]
    if req.get("acceptance"):
        parts += ["## 验收要点", req["acceptance"], ""]

    specs = [s for s in ctx.store.all("specs", req_id=req["id"]) if s["status"] == "已审"]
    if specs:
        parts += ["## 已审 Spec（按这些做，不要自行发挥）"]
        for s in sorted(specs, key=lambda x: x["n"])[:8]:
            head = [l for l in (s.get("content") or "").splitlines()
                    if l.startswith("##")][:4]
            parts.append(f"- S{s['n']:02d} {s['name']}：" + (" / ".join(h.strip('# ') for h in head) or "见正文"))
        parts.append("")

    tasks = ctx.store.all("wbs", req_id=req["id"])
    if tasks:
        parts += ["## 拆好的任务（按顺序做）"]
        for w in tasks:
            parts.append(f"- [{w['id']}] {w['title']}（来源 {w['spec']}，估时 {w['est']}）")
        parts.append("")

    parts += ["## 工程约定",
              f"- 工作区：{task['fixture']}",
              f"- 门禁：{task['check']}　退出码 0 才算完成",
              "- 只做加法，不改原有行为；不许改门禁脚本；零外部依赖",
              "",
              "## 完成标准",
              f"运行 `python3 {task['check']}` 退出码为 0。你说完成不算，退出码才算。"]
    return "\n".join(parts)


def create_run(ctx, params, body):
    body = body or {}
    task_id = body.get("task", "pomodoro")
    reg = _registry()
    if task_id not in reg:
        return 400, {"error": f"没有任务 {task_id}"}
    task = reg[task_id]

    req_id = body.get("req_id")
    req = None
    if req_id:
        req = ctx.store.get("reqs", req_id)
        if not req:
            return 400, {"error": f"需求 {req_id} 不存在"}
        # 需求绑了工作区 → 以需求为准，忽略前端传的 task
        if req.get("workspace_id") and req["workspace_id"] in reg:
            task_id = req["workspace_id"]
            task = reg[task_id]

    prompt = (body.get("prompt") or "").strip()
    source = "custom"
    if not prompt and req:
        prompt = compose_prompt(ctx, req, task)      # ← 需求驱动
        source = "requirement"
    if not prompt:
        prompt = (DEMO / task["task"]).read_text(encoding="utf-8")
        source = "builtin"

    run_id = "RUN-" + uuid.uuid4().hex[:8]
    ctx.store.put("runs", {
        "id": run_id, "task": task_id, "req_id": req_id,
        "status": "running", "gate": None, "steps": None, "denied": 0,
        "prompt_source": source, "prompt": prompt,
        "started_at": time.time(),
    })
    with _lock:
        RUNS[run_id] = {"cancel": threading.Event()}
    threading.Thread(target=_worker, args=(ctx, run_id, task, prompt), daemon=True).start()
    ctx.bus.publish({"type": "run_created", "run": run_id, "task": task_id,
                     "req": req_id, "prompt_source": source})
    return 202, {"run": run_id, "prompt_source": source, "prompt": prompt}


def list_runs(ctx, params, body):
    return 200, {"items": ctx.store.all("runs")}


def get_run(ctx, params, body):
    row = ctx.store.get("runs", params["id"])
    if not row:
        return 404, {"error": "运行不存在"}
    return 200, {"item": row}


def stop_run(ctx, params, body):
    rid = params["id"]
    with _lock:
        rec = RUNS.get(rid)
    if not rec:
        return 404, {"error": "没有在跑的运行"}
    rec["cancel"].set()
    approvals.cancel_all()
    return 200, {"ok": True, "run": rid}
