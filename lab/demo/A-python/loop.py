"""Agent loop —— 整个 harness 的心脏，只有几十行。

一个 turn = 一次任务；一个 step = 一次模型调用。
终止：模型不再调工具 / 步数耗尽 / 重复超限升级 / 被取消。
"""
import json
import compact


def _cli_emit(ev):
    """命令行下的默认输出（保持和以前一致的观感）。"""
    t = ev.get("type")
    if t == "tool_call":
        print(f"\n[step {ev['step']}] → {ev['name']}({_short(ev['args'])})")
    elif t == "tool_result":
        if ev.get("denied"):
            print(f"        ⛔ 被拒：{ev.get('reason')}")
        elif ev.get("code") is not None:
            print(f"        → code={ev['code']}")
        elif ev.get("path"):
            print(f"        ✓ {ev['path']}")
    elif t == "assistant":
        if ev.get("content"):
            print(f"\n[step {ev['step']}] 模型结束：{ev['content'][:160]}")
    elif t == "escalate":
        print(f"\n[step {ev['step']}] ⚠ {ev['reason']} → 升级人工")


def _short(args, n=110):
    s = json.dumps(args, ensure_ascii=False) if not isinstance(args, str) else args
    return s if len(s) <= n else s[:n] + " …"


def run(cfg, llm, tools, session, budget, task, emit=None, cancel=None):
    emit = emit or _cli_emit
    messages = [
        {"role": "system", "content": __import__("llm").SYSTEM},
        {"role": "user", "content": task},
    ]
    session.append("task_start", task=task)
    emit({"type": "run_start", "task": task,
          "model": "MOCK" if cfg["bool"]("MOCK") else cfg.get("DEEPSEEK_MODEL"),
          "workspace": str(cfg["WORKSPACE_PATH"])})
    emit({"type": "context", "step": 0, "messages": compact.snapshot(messages),
          "tokens": compact.estimate_tokens(messages)})

    status, last_gate = "max_steps", None

    while budget.tick():
        if cancel is not None and cancel.is_set():
            status = "cancelled"
            emit({"type": "run_end", "status": status, "reason": "用户停止",
                  "gate": last_gate, "denied": tools.denied, **budget.summary()})
            return {"status": status, "gate": last_gate, "denied": tools.denied, **budget.summary()}

        step = budget.steps
        resp = llm.chat(messages, tools.spec())
        content = resp.get("content") or ""
        calls = resp.get("tool_calls") or []
        session.append("assistant", step=step, content=content,
                       calls=[c["function"]["name"] for c in calls])
        emit({"type": "assistant", "step": step, "content": content,
              "calls": [c["function"]["name"] for c in calls]})

        if not calls:
            status = "done"
            break

        messages.append({"role": "assistant", "content": content or None, "tool_calls": calls})

        stop = False
        for c in calls:
            name = c["function"]["name"]
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}

            sig = name + json.dumps(args, sort_keys=True, ensure_ascii=False)[:200]
            if budget.observe(sig) == "escalate":
                session.append("escalate", step=step, tool=name)
                emit({"type": "escalate", "step": step, "tool": name,
                      "reason": f"同一动作重复超过 {budget.max_retries} 次"})
                status, stop = "escalated", True
                break

            emit({"type": "tool_call", "step": step, "name": name, "args": args})
            result = tools.call(name, args)
            if name == "run_check":
                last_gate = result.get("code")
            session.append("tool_result", step=step, tool=name,
                           denied=bool(result.get("denied")),
                           code=result.get("code"), result=result)
            emit({"type": "tool_result", "step": step, "name": name,
                  "denied": bool(result.get("denied")),
                  "code": result.get("code"),
                  "reason": result.get("reason"),
                  "path": result.get("path"),
                  "bytes": result.get("bytes")})

            messages.append({"role": "tool", "tool_call_id": c["id"], "name": name,
                             "content": json.dumps(result, ensure_ascii=False)[:4000]})

        emit({"type": "context", "step": step, "messages": compact.snapshot(messages),
              "tokens": compact.estimate_tokens(messages)})
        if stop:
            break

    session.append("task_end", status=status, gate=last_gate, **budget.summary())
    emit({"type": "run_end", "status": status, "gate": last_gate,
          "denied": tools.denied, **budget.summary(),
          "messages": compact.snapshot(messages),
          "tokens": compact.estimate_tokens(messages)})
    return {"status": status, "gate": last_gate, "denied": tools.denied,
            **budget.summary(), "messages": messages}
