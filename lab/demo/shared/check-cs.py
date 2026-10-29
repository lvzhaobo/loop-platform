#!/usr/bin/env python3
"""门禁 · 智能客服

和番茄钟那份的关键区别：这里被测的是 Python，所以门禁可以**直接 import 它、调用它**，
断的是行为，不是字符串。能直接调用时，门禁就该直接调用。
"""
import importlib
import re
import sys
from pathlib import Path

FIX = Path(__file__).resolve().parent / "fixture" / "cs"
SRC = FIX / "support.py"

CHECKS = []

def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco

def load_support():
    sys.path.insert(0, str(FIX))
    try:
        import support
        return importlib.reload(support)
    finally:
        sys.path.remove(str(FIX))


@check("support.py 能加载")
def _():
    if not SRC.exists():
        return False, "文件不存在"
    m = load_support()
    for fn in ("classify", "reply", "new_session", "ticket_no"):
        if not hasattr(m, fn):
            return False, f"缺少函数 {fn}"
    return True, ""


@check("三类意图识别正确")
def _():
    m = load_support()
    cases = {"我要退款": "refund", "快递到哪了": "logistics", "转人工": "human"}
    for text, want in cases.items():
        got = m.classify(text)
        if got != want:
            return False, f'classify("{text}") 得到 {got}，期望 {want}'
    return True, ""


@check("识别不了的是 unknown")
def _():
    m = load_support()
    if m.classify("今天天气怎么样") != "unknown":
        return False, "无关消息没有落到 unknown"
    return True, ""


@check("reply 返回结构完整")
def _():
    m = load_support()
    r = m.reply("我要退款", m.new_session())
    if not isinstance(r, dict):
        return False, "reply 没有返回 dict"
    for k in ("intent", "text", "escalate"):
        if k not in r:
            return False, f"缺少字段 {k}"
    if not isinstance(r["text"], str) or not r["text"]:
        return False, "text 不是非空字符串"
    if not isinstance(r["escalate"], bool):
        return False, "escalate 不是布尔值"
    return True, ""


@check("每条回复都带工单号")
def _():
    m = load_support()
    for text in ("我要退款", "快递到哪了", "转人工", "随便说点什么"):
        r = m.reply(text, m.new_session())
        if not re.search(r"工单号：CS-[0-9A-F]{4}", r["text"]):
            return False, f'"{text}" 的回复里没有工单号：{r["text"][:30]}'
    return True, ""


@check("连续两次识别失败才转人工")
def _():
    m = load_support()
    s = m.new_session()
    r1 = m.reply("今天天气怎么样", s)
    if r1["escalate"]:
        return False, "第一次 unknown 就转人工了（太早）"
    r2 = m.reply("你猜猜", s)
    if not r2["escalate"]:
        return False, "连续第二次 unknown 没有转人工"
    return True, ""


@check("识别成功会重置计数")
def _():
    m = load_support()
    s = m.new_session()
    m.reply("今天天气怎么样", s)          # unknown ×1
    m.reply("我要退款", s)                # 成功 → 清零
    r1 = m.reply("你猜猜", s)             # unknown ×1 → 不该转
    if r1["escalate"]:
        return False, "识别成功后没有重置计数（正常咨询会被误转）"
    r2 = m.reply("随便聊聊", s)           # unknown ×2 → 该转
    if not r2["escalate"]:
        return False, "从零开始数了两次 unknown，仍然没有转人工"
    return True, ""


@check("零依赖 · 只用了标准库")
def _():
    src = SRC.read_text(encoding="utf-8")
    mods = set(re.findall(r"^\s*(?:import|from)\s+([a-zA-Z_][\w]*)", src, re.M))
    stdlib = {"hashlib", "re", "json", "typing", "collections", "math", "time",
              "random", "string", "sys", "os", "dataclasses", "functools"}
    bad = mods - stdlib
    if bad:
        return False, "引用了非标准库：" + ", ".join(sorted(bad))
    if re.search(r"requests\.|urllib\.request|socket\.", src):
        return False, "看起来在联网"
    return True, ""


@check("门禁自身未被修改")
def _():
    src = Path(__file__).read_text(encoding="utf-8")
    if "ALLOW_" + "EDIT_CHECK" in src:
        return False, "门禁被改过"
    return True, ""


def main():
    print(f"\n门禁：{FIX}\n" + "─" * 56)
    bad = 0
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        print(("  ✅ " if ok else "  ❌ ") + name)
        if not ok:
            bad += 1
            if detail:
                print("       └─ " + detail)
    print("─" * 56)
    print(f"  {len(CHECKS)-bad}/{len(CHECKS)} 通过 —— " + ("门禁绿\n" if not bad else "门禁红\n"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
