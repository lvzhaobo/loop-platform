"""harness-5 · 【可观测埋点】Phase 1 —— stdlib-only,追加写 output/events.jsonl。

设计目标:用最小侵入(只在 model.generate / gates.verify 两处埋点)记录一次运行的
完整链路。每条事件带 trace_id 串起来 → 天然支持"门禁失败 Top-N"聚合与会话回放。

事件 kind:
  - llm.call     : 一次真实 LLM 调用(real 模式),含 token 用量
  - check.result : 单条门禁结果 {check, ok, detail}

上下文(trace_id/case/attempt/mode)由 model.generate 维护,verify 紧随其后 emit 时
自动带上 —— 因此无需改动各层 Loop 文件。

关闭埋点: 设环境变量 HARNESS_OBSERV=0。
"""
import json
import os
from datetime import datetime

# 本文件在 harness-5/lib/ 下 → ROOT = harness-5
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS_PATH = os.path.join(ROOT, "output", "events.jsonl")

# 当前运行上下文:trace_id / case / attempt / mode
_CTX: dict[str, object] = {}
_SEQ = 0  # 进程内序号,保证同一秒/同一进程内多次 new_trace 也不撞


def set_context(**kw: object) -> None:
    """更新当前上下文(None 值忽略)。"""
    _CTX.update({k: v for k, v in kw.items() if v is not None})


def new_trace(case: str) -> str:
    """开一条新链路(通常在 attempt=1 时)。返回 trace_id。

    trace_id = 时间戳 + 进程号 + 进程内序号 + case,
    确保同一秒多个进程(或同一进程内多次运行,如 L4 跑两遍)不碰。
    """
    global _SEQ
    _SEQ += 1
    tid = f"{datetime.now():%Y%m%d-%H%M%S}-{os.getpid()}-{_SEQ}-{case}"
    _CTX["trace_id"] = tid
    _CTX["case"] = case
    return tid


def current(key: str) -> object:
    return _CTX.get(key)


def emit(kind: str, **fields: object) -> None:
    """追加一条结构化事件到 events.jsonl。"""
    if os.environ.get("HARNESS_OBSERV", "1") == "0":
        return
    ev: dict[str, object] = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
    }
    for k in ("trace_id", "case", "attempt", "mode"):
        if _CTX.get(k) is not None:
            ev[k] = _CTX[k]
    ev.update(fields)
    os.makedirs(os.path.dirname(EVENTS_PATH), exist_ok=True)
    with open(EVENTS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
