"""最小可用的上下文压缩 —— 演示用。

真实实现要看保留清单、摘要模型、校验；这里只保留"能看见效果"的部分：
  ① 估 token  ② 判定水位  ③ 切分（保留 system + 最近 K 轮）④ 摘要中间段
  ⑤ 返回新消息列表 + 前后对比
"""

def estimate_tokens(messages) -> int:
    n = 0
    for m in messages:
        c = m.get("content")
        if isinstance(c, list):
            c = " ".join(str(x) for x in c)
        n += len(str(c or ""))
    return max(1, int(n / 2.4))          # 中英混合的经验系数

def snapshot(messages, limit=280):
    out = []
    for i, m in enumerate(messages):
        c = m.get("content")
        if isinstance(c, list):
            c = " ".join(str(x) for x in c)
        c = str(c or "")
        out.append({"i": i, "role": m.get("role", "?"),
                    "chars": len(c), "preview": c[:limit],
                    "truncated": len(c) > limit,
                    "calls": [tc["function"]["name"] for tc in (m.get("tool_calls") or [])]})
    return out

def summarize(text, budget=60):
    """极简摘要：取前几句 + 标记省略。真实场景应交给 LLM。"""
    t = " ".join(str(text).split())
    if len(t) <= budget:
        return t
    return t[:budget] + "…"

def compact(messages, keep_last=3, keep_first=1):
    """保留前 keep_first 条（system）+ 最近 keep_last 条，中间压成一条摘要。"""
    if len(messages) <= keep_first + keep_last + 1:
        return {"skipped": True, "reason": "消息太少，压缩是纯亏",
                "before": None, "after": None, "messages": messages}

    head = messages[:keep_first]
    middle = messages[keep_first:len(messages) - keep_last]
    tail = messages[len(messages) - keep_last:]

    lines = []
    for m in middle:
        role = m.get("role", "?")
        c = m.get("content") or ""
        if isinstance(c, list):
            c = " ".join(str(x) for x in c)
        if m.get("tool_calls"):
            names = ",".join(tc["function"]["name"] for tc in m["tool_calls"])
            lines.append(f"[{role}] 调用了工具：{names}")
        else:
            lines.append(f"[{role}] {summarize(c)}")

    summary = {
        "role": "user",
        "content": ("【压缩摘要 · 覆盖前 " + str(len(middle)) + " 条消息】\n" + "\n".join(lines[:40])
                    + "\n（原始事件仍在日志里，可回放）"),
    }
    new_msgs = head + [summary] + tail

    before = {"count": len(messages), "tokens": estimate_tokens(messages)}
    after = {"count": len(new_msgs), "tokens": estimate_tokens(new_msgs)}
    return {"skipped": False, "before": before, "after": after,
            "ratio": round(after["tokens"] / max(1, before["tokens"]), 3),
            "covered": len(middle), "messages": new_msgs}
