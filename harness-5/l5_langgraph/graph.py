"""L5 · 用 LangGraph 组装同一个 Loop —— Maker/Checker 完全复用 lib/,只换编排。

和 L3 (l3_guardrails/loop_guarded.py) 功能等价:自洽性门禁 → 生成 → 卡死检测
→ 验收 → (通过/护栏/回喂) 三选一。区别在于:这里把手写的 while 显式建成
一张【状态图】:

  - 循环   = 图里的一条回边(route 返回 "maker")
  - 状态   = LoopState(TypedDict),节点读写它,而不是函数间传参
  - 护栏   = 条件边里的路由函数(after_consistency / after_stuck / route)
  - 检查点 = Checkpointer(每一步可回放/可恢复),而不是只落一个终态 state.json

Maker(lib/model.py)、Checker(lib/gates.py)、common(lib/common.py)一行不改。
"""
import hashlib
import os
import sys
from typing import Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver  # 生产可换 SqliteSaver
from langgraph.graph import END, StateGraph

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lib import gates, model  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]


class LoopState(TypedDict):
    """图里传来传去的共享状态,取代 L3 里的一堆局部变量。"""
    spec_text: str
    facts: dict[str, Any]
    constraints: dict[str, Any]
    out_dir: str
    attempt: int
    cost: int
    feedback: str | None
    prev_hash: str | None
    results: list[dict[str, Any]]
    stop_reason: str


# ============ 节点:每个节点承载一件事 ============

def n_consistency(s: LoopState) -> LoopState:
    """生成前门禁:facts 声明的函数都能在规格里找到落点。"""
    fails = gates.check_consistency(s["spec_text"], s["facts"])
    if fails:
        s["stop_reason"] = "abort:自洽性门禁未过 — " + "; ".join(fails)
    else:
        print("[L5] 自洽性门禁通过 ✓")
    return s


def n_maker(s: LoopState) -> LoopState:
    """Maker:调 model.generate 落盘,并累计花费。"""
    s["attempt"] += 1
    g = s["constraints"].get("loop", {})
    print(f"\n===== 第 {s['attempt']} 轮 (已花 {s['cost']}/{g.get('max_cost')}) =====")
    model.generate(s["out_dir"], s["spec_text"], s["facts"], s["constraints"],
                   attempt=s["attempt"], feedback=s["feedback"])
    s["cost"] += g.get("cost_per_attempt", 0)
    return s


def _product_hash(out_dir: str) -> str | None:
    """整个产物目录的指纹(排序后拼接每个文件的 相对路径+内容)。

    比 L3 只 hash facts["module"] 更健全:mall 这类多文件任务里,
    变化的是 products.json 而非 app.py,只看单个模块会误报卡死。
    """
    if not os.path.isdir(out_dir):
        return None
    h = hashlib.sha256()
    files = []
    for base, _dirs, names in os.walk(out_dir):
        for name in names:
            if name == "state.json" or name.endswith(".pyc"):  # 过程态/字节码,不算产物
                continue
            files.append(os.path.join(base, name))
    for p in sorted(files):  # 排序保证确定性
        h.update(os.path.relpath(p, out_dir).encode("utf-8"))
        with open(p, "rb") as f:  # 按字节读,二进制安全
            h.update(f.read())
    return h.hexdigest() if files else None


def n_stuck(s: LoopState) -> LoopState:
    """护栏③ 卡死检测:本轮产物与上轮字节完全相同 → 修不动了。"""
    cur = _product_hash(s["out_dir"])
    if s["prev_hash"] is not None and cur == s["prev_hash"]:
        s["stop_reason"] = "abort:触发【卡死检测】本轮产物与上轮完全相同"
    s["prev_hash"] = cur
    return s


def n_checker(s: LoopState) -> LoopState:
    """Checker:跑验收门禁 + 定收敛/护栏结论。

    ⚠️ 决策必须写在【节点】里:LangGraph 只持久化节点的返回值,
       条件边(route)里对 state 的赋值【不会保存】,所以 stop_reason/feedback
       都在这里定好,route 只做纯读取路由。
    """
    s["results"] = gates.verify(s["out_dir"], s["facts"], s["constraints"])
    print(gates.format_report(s["results"]))
    g = s["constraints"].get("loop", {})
    if gates.all_ok(s["results"]):
        s["stop_reason"] = f"pass:验收通过 ✓(共 {s['attempt']} 轮,花费 {s['cost']})"
    elif s["attempt"] >= g.get("max_iterations", 5):  # 护栏① 迭代上限
        s["stop_reason"] = f"abort:触发【迭代上限】{g.get('max_iterations')} 轮仍未通过"
    elif s["cost"] + g.get("cost_per_attempt", 0) > g.get("max_cost", 10**9):  # 护栏② 花费上限
        s["stop_reason"] = f"abort:触发【花费上限】再跑一轮将超预算 {g.get('max_cost')}"
    else:
        s["feedback"] = gates.format_report(s["results"])  # 回喂
        print(f"[L5] 第 {s['attempt']} 轮未过,回喂继续...")
    return s


# ============ 条件边:纯读取 state,决定去哪个节点(不改 state) ============

def after_consistency(s: LoopState) -> str:
    return END if s["stop_reason"] else "maker"


def after_stuck(s: LoopState) -> str:
    return END if s["stop_reason"] else "checker"


def route(s: LoopState) -> str:
    """验收后:有结论(pass/abort)→END;否则回喂→maker。"""
    return END if s["stop_reason"] else "maker"


def build():
    """组装状态图。节点=部件,边=控制流,回边=循环。"""
    g = StateGraph(LoopState)
    g.add_node("consistency", n_consistency)
    g.add_node("maker", n_maker)
    g.add_node("stuck_check", n_stuck)
    g.add_node("checker", n_checker)

    g.set_entry_point("consistency")
    g.add_conditional_edges("consistency", after_consistency, {"maker": "maker", END: END})
    g.add_edge("maker", "stuck_check")
    g.add_conditional_edges("stuck_check", after_stuck, {"checker": "checker", END: END})
    g.add_conditional_edges("checker", route, {"maker": "maker", END: END})

    return g.compile(checkpointer=MemorySaver())
