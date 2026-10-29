"""Spec 模块 —— 需求 → 14 份 Spec（MumuSpec 风格）+ 审核状态机 + 依赖失效传播。

三个设计要点：
  ① 14 份不是平铺的，是有依赖的 DAG。上游变了，下游必须标 stale。
  ② 审核有三种模式（逐份 / 分组 / 统一），逐份模式会真的阻塞线程。
  ③ 生成优先用 LLM（有 key 且非 MOCK），否则退回模板。每份记录 engine 字段。
"""
import threading
import time
from pathlib import Path

# ---------- 14 份的定义（MumuSpec 分层） ----------
# (n, 名称, 分组, 依赖, 目标字数)
SPEC_DEFS = [
    (1,  '立项提案与范围说明', '需求层', [],           900),
    (2,  '术语表与角色定义',   '需求层', [1],          600),
    (3,  '产品需求说明（PRD）','需求层', [1],         1200),
    (4,  '用户故事与验收标准', '需求层', [3],          860),
    (5,  '功能规格说明',       '设计层', [3, 4],      1400),
    (6,  '系统约束（非功能+安全）','设计层', [3],      700),
    (7,  '系统架构与技术选型', '设计层', [5, 6],      1100),
    (8,  '数据模型与存储规格', '设计层', [5],          980),
    (9,  'API 接口规格',       '设计层', [8],         1420),
    (10, '页面与交互规格',     '设计层', [4],          760),
    (11, '错误与边界',         '实现层', [5, 9],       430),
    (12, '测试策略与质量门禁', '实现层', [4, 9],       900),
    (13, '观测与告警',         '交付层', [7],          520),
    (14, '需求追踪矩阵',       '交付层', [1,2,3,4,5,6,7,8,9,10], 480),
]
GROUPS = ['需求层', '设计层', '实现层', '交付层']

PENDING_REVIEW = {}      # spec_id -> threading.Event（逐份审时阻塞用）
_lock = threading.Lock()


def _defs():
    return [{"n": n, "name": name, "group": g, "dep": dep, "words": w}
            for n, name, g, dep, w in SPEC_DEFS]


SPEC_DEMO = Path(__file__).resolve().parent.parent.parent / "demo"


def _llm_ready():
    """有 key 且不是 MOCK 才走模型"""
    try:
        import sys
        sys.path.insert(0, str(SPEC_DEMO / "A-python"))
        import config
        cfg = config.load()
        if cfg["bool"]("MOCK"):
            return None
        key = cfg.get("DEEPSEEK_API_KEY", "")
        if not key or key.startswith("sk-在这里"):
            return None
        return cfg
    except Exception:
        return None


def _gen_via_llm(cfg, req, d, upstream_names, on_delta=None):
    """调 DeepSeek 流式生成一份 Spec 正文；每个 chunk 回调给总线"""
    import sys
    sys.path.insert(0, str(SPEC_DEMO / "A-python"))
    import llm

    up = "、".join(upstream_names) if upstream_names else "无"
    prompt = f"""你在为一个企业研发项目写规格文档。请只输出 Markdown 正文，不要任何解释。

## 需求
标题：{req['title']}
验收要点：{req.get('acceptance') or '（未填写）'}

## 你要写的这一份
第 {d['n']:02d} 份：《{d['name']}》
所属阶段：{d['group']}
上游文档：{up}

## 要求
- 600–1200 字，结构清晰，用二级标题分节
- 必须**具体到这个需求**，不要写「按上游确定」这类空话
- 这一份的职责范围要明确，不要越界去写别的文档
- 需要给出表格的地方用 Markdown 表格
- 不要重复需求的原文，要往下推进一步（设计层给方案，实现层给规则）

直接输出正文，第一行是 `# {d['n']:02d}. {d['name']}`。"""

    parts = []
    for ch in llm.LLM(cfg).chat_stream(
            [{"role": "system", "content": "你是资深技术文档作者，写规格文档，不写废话。"},
             {"role": "user", "content": prompt}]):
        parts.append(ch)
        if on_delta:
            on_delta(ch)
    txt = "".join(parts).strip()
    return txt if len(txt) > 80 else None


def _spec_id(req_id, n):
    return f"{req_id}-S{n:02d}"


# ---------- 模板生成 ----------
def _gen_content(req, d, upstream):
    title = req["title"]
    acc = req.get("acceptance") or "（需求未填验收要点）"
    lines = [f"# {d['n']:02d}. {d['name']}", ""]
    lines += [f"> 需求：{req['id']} · {title}", f"> 版本：v1 · 生成方式：模板", ""]

    if d["group"] == "需求层":
        lines += ["## 1. 背景与目标", f"本次要解决的是：{title}。", ""]
        lines += ["## 2. 范围", "### 2.1 包含", "- 见验收要点"]
        lines += ["### 2.2 不包含", "- 不在本次范围内的改造不做", ""]
        lines += ["## 3. 验收要点", f"- {acc}", ""]
    elif d["group"] == "设计层":
        lines += ["## 1. 设计目标", f"支撑「{title}」的实现。", ""]
        lines += ["## 2. 方案", "| 项 | 说明 |", "| --- | --- |",
                  "| 入口 | 按上游 Spec 确定 |", "| 约束 | 见系统约束 |", ""]
        lines += ["## 3. 与上游的关系"]
        lines += [f"- 依赖：{', '.join(str(x) for x in d['dep']) or '无'}" for _ in [0]]
        lines += [""]
    elif d["group"] == "实现层":
        lines += ["## 1. 错误分类", "| 类型 | 处理 |", "| --- | --- |",
                  "| 输入非法 | 回退默认值 |", "| 依赖不可用 | 降级 + 告警 |", ""]
        lines += ["## 2. 质量门禁", "- 断言必须可机器判定", f"- 对应验收：{acc}", ""]
    else:
        lines += ["## 1. 观测项", "| 指标 | 阈值 |", "| --- | --- |",
                  "| 错误率 | < 1% |", "| P95 | < 1.2s |", ""]
        lines += ["## 2. 追踪", "| 需求 | Spec | 代码 |", "| --- | --- | --- |",
                  f"| {req['id']} | 本组 14 份 | 待实现 |", ""]

    if upstream:
        lines += ["## 附：上游摘要", *[f"- S{u:02d}：已生成" for u in upstream], ""]
    return "\n".join(lines)


def _word_count(text):
    return len("".join(text.split()))


# ---------- 生成线程 ----------
def _worker(ctx, req_id, mode, group_size, engine="auto"):
    req = ctx.store.get("reqs", req_id)
    specs = {d["n"]: ctx.store.put("specs", {
        "id": _spec_id(req_id, d["n"]), "req_id": req_id, "n": d["n"],
        "name": d["name"], "group": d["group"], "dep": d["dep"],
        "status": "未生成", "version": 0, "words": 0, "content": "",
        "reviewer": None, "stale_by": None,
    }) for d in _defs()}

    cfg = _llm_ready() if engine in ("auto", "llm") else None
    use_llm = cfg is not None
    ctx.bus.publish({"type": "spec_batch_start", "req": req_id,
                     "total": len(SPEC_DEFS), "mode": mode,
                     "engine": "llm" if use_llm else "template"})
    done = 0
    for d in _defs():
        sid = _spec_id(req_id, d["n"])
        ctx.store.patch("specs", sid, status="生成中")
        ctx.bus.publish({"type": "spec_generating", "spec": sid, "n": d["n"]})

        used = "template"
        content = None
        if use_llm:
            try:
                names = [f"S{x:02d} {next(y['name'] for y in _defs() if y['n']==x)}"
                         for x in d["dep"]]
                ctx.bus.publish({"type": "spec_stream_start", "spec": sid,
                                 "n": d["n"], "name": d["name"], "done": done + 1,
                                 "total": len(SPEC_DEFS)})
                content = _gen_via_llm(
                    cfg, req, d, names,
                    on_delta=lambda ch: ctx.bus.publish(
                        {"type": "spec_delta", "spec": sid, "n": d["n"], "text": ch}))
                ctx.bus.publish({"type": "spec_stream_end", "spec": sid,
                                 "n": d["n"], "chars": len(content or "")})
                used = "llm"
            except Exception as e:
                ctx.bus.publish({"type": "spec_llm_failed", "spec": sid,
                                 "error": f"{type(e).__name__}: {e}"})
        if not content:
            content = _gen_content(req, d, d["dep"])
            used = "template"

        ctx.store.patch("specs", sid, status="待审", content=content,
                        words=_word_count(content), version=1,
                        engine=used, generated_at=time.time())
        done += 1
        ctx.bus.publish({"type": "spec_generated", "spec": sid, "n": d["n"],
                         "words": _word_count(content), "done": done,
                         "total": len(SPEC_DEFS), "engine": used})

        # 逐份审：生成完就停下来等人
        if mode == "stepwise":
            ev = threading.Event()
            with _lock:
                PENDING_REVIEW[sid] = ev
            ctx.bus.publish({"type": "spec_review_wait", "spec": sid, "n": d["n"]})
            ev.wait(timeout=600)
            with _lock:
                PENDING_REVIEW.pop(sid, None)

        # 分组审：每 group_size 份停一次
        if mode == "group" and done % group_size == 0 and done < len(SPEC_DEFS):
            ctx.bus.publish({"type": "spec_group_done", "done": done,
                             "group": d["group"]})

    ctx.store.patch("reqs", req_id, status="已转 Spec")
    ctx.bus.publish({"type": "spec_batch_done", "req": req_id, "total": len(SPEC_DEFS)})


# ---------- 依赖失效传播 ----------
def _dependents(specs, n):
    """传递闭包：谁（直接或间接）依赖 n"""
    rev = {}
    for s in specs:
        for d in s["dep"]:
            rev.setdefault(d, []).append(s["n"])
    out, stack = set(), list(rev.get(n, []))
    while stack:
        cur = stack.pop()
        if cur in out:
            continue
        out.add(cur)
        stack.extend(rev.get(cur, []))
    return out


def _propagate_stale(ctx, req_id, changed_n):
    specs = ctx.store.all("specs", req_id=req_id)
    hit = _dependents(specs, changed_n)
    for s in specs:
        if s["n"] in hit:
            ctx.store.patch("specs", s["id"], status="需修改",
                            stale_by=changed_n, stale_at=time.time())
    if hit:
        ctx.bus.publish({"type": "spec_stale", "req": req_id,
                         "changed": changed_n, "affected": sorted(hit)})
    return sorted(hit)


# ---------- HTTP 处理 ----------
def generate(ctx, params, body):
    body = body or {}
    req_id = body.get("req_id")
    if not req_id or not ctx.store.get("reqs", req_id):
        return 400, {"error": "req_id 不存在"}
    mode = body.get("mode", "batch")          # batch | group | stepwise
    if mode not in ("batch", "group", "stepwise"):
        return 400, {"error": "mode 只能是 batch / group / stepwise"}
    engine = body.get("engine", "auto")       # auto | llm | template
    if engine not in ("auto", "llm", "template"):
        return 400, {"error": "engine 只能是 auto / llm / template"}

    cfg = _llm_ready() if engine in ("auto", "llm") else None
    ctx.store.patch("reqs", req_id, status="Spec 生成中")
    threading.Thread(target=_worker, daemon=True,
                     args=(ctx, req_id, mode, int(body.get("group_size") or 3),
                           engine)).start()
    return 202, {"req": req_id, "mode": mode, "total": len(SPEC_DEFS),
                 "engine": "llm" if cfg else "template"}


def list_specs(ctx, params, body):
    req_id = params.get("req_id")
    rows = ctx.store.all("specs", req_id=req_id) if req_id else ctx.store.all("specs")
    rows.sort(key=lambda r: r["n"])
    groups = []
    for g in GROUPS:
        items = [r for r in rows if r["group"] == g]
        groups.append({"group": g, "items": items,
                       "reviewed": sum(1 for r in items if r["status"] == "已审")})
    return 200, {"req_id": req_id, "total": len(rows),
                 "by_status": _count(rows), "groups": groups}


def _count(rows):
    out = {}
    for r in rows:
        out[r["status"]] = out.get(r["status"], 0) + 1
    return out


def get_spec(ctx, params, body):
    row = ctx.store.get("specs", params["id"])
    if not row:
        return 404, {"error": "Spec 不存在"}
    return 200, {"item": row}


def review(ctx, params, body):
    body = body or {}
    decision = body.get("decision")
    if decision not in ("approve", "request_change"):
        return 400, {"error": "decision 只能是 approve / request_change"}
    sid = params["id"]
    row = ctx.store.get("specs", sid)
    if not row:
        return 404, {"error": "Spec 不存在"}
    if row["status"] not in ("待审", "需修改"):
        return 409, {"error": f"当前状态 {row['status']} 不能审"}

    new_status = "已审" if decision == "approve" else "需修改"
    ctx.store.patch("specs", sid, status=new_status,
                    reviewer=body.get("by", "人"),
                    comment=body.get("comment", ""),
                    reviewed_at=time.time())
    ctx.bus.publish({"type": "spec_reviewed", "spec": sid,
                     "decision": decision, "by": body.get("by", "人")})

    with _lock:
        ev = PENDING_REVIEW.get(sid)
    if ev:
        ev.set()                                   # 唤醒逐份审的生成线程

    return 200, {"item": ctx.store.get("specs", sid)}


def regenerate(ctx, params, body):
    """重新生成一份，并把下游全部标 stale —— 这是 DAG 的意义。"""
    sid = params["id"]
    row = ctx.store.get("specs", sid)
    if not row:
        return 404, {"error": "Spec 不存在"}
    d = next(x for x in _defs() if x["n"] == row["n"])
    req = ctx.store.get("reqs", row["req_id"])
    content = _gen_content(req, d, d["dep"])
    v = (row.get("version") or 0) + 1
    ctx.store.patch("specs", sid, status="待审", content=content, version=v,
                    words=_word_count(content), stale_by=None,
                    generated_at=time.time())
    ctx.bus.publish({"type": "spec_regenerated", "spec": sid, "version": v})
    affected = _propagate_stale(ctx, row["req_id"], row["n"])
    return 200, {"item": ctx.store.get("specs", sid), "stale_affected": affected}


def graph(ctx, params, body):
    req_id = params.get("req_id")
    rows = ctx.store.all("specs", req_id=req_id) if req_id else []
    nodes = [{"id": r["id"], "n": r["n"], "name": r["name"],
              "group": r["group"], "status": r["status"]} for r in sorted(rows, key=lambda x: x["n"])]
    edges = [{"from": _spec_id(req_id, d), "to": _spec_id(req_id, r["n"])}
             for r in rows for d in r["dep"]]
    return 200, {"nodes": nodes, "edges": edges}


def stream_preview(ctx, params, body):
    return 400, {"error": "用 SSE 看：GET /api/events（事件 type=spec_delta）"}


def engine(ctx, params, body):
    cfg = _llm_ready()
    return 200, {"engine": "llm" if cfg else "template",
                 "model": (cfg or {}).get("DEEPSEEK_MODEL", "—")}


def progress(ctx, params, body):
    req_id = params.get("req_id")
    rows = ctx.store.all("specs", req_id=req_id)
    total = len(SPEC_DEFS)
    done = sum(1 for r in rows if r["status"] in ("待审", "已审", "需修改"))
    reviewed = sum(1 for r in rows if r["status"] == "已审")
    return 200, {"req_id": req_id, "total": total, "generated": done,
                 "reviewed": reviewed, "pct": round(done / total * 100)}
