"""harness-5 · 【Checker(验收器)】—— Loop 中"验"的那一半,也是 Harness 的门禁核心。

门禁层:两道关卡,复用于 L1~L4。

  check_consistency(): 生成【之前】跑,最便宜。校验 facts.json 里声明的函数
                       是否都能在人读规格 spec.md 找到落点(防止事实源与规格漂移)。
  verify():            生成【之后】跑。结构(函数齐全)→ 安全(禁用模式)→ 行数
                       → 跑固定测试。收集全部结果,一次看清所有问题。
"""
import os
import subprocess
import sys
import json
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]
import observ  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]


def check_consistency(spec_text: str, facts: dict[str, Any]) -> list[str]:
    """返回失败信息列表(空=通过)。"""
    fails = []
    for fn in facts["functions"]:
        if fn["name"] not in spec_text:
            fails.append(f"facts 声明的函数 '{fn['name']}' 未在 spec.md 出现")
    return fails


def _run_tests(out_dir: str) -> tuple[bool, str]:
    """把产物目录加入 PYTHONPATH,跑固定验收测试。返回 (ok, 末尾输出)。"""
    env = dict(os.environ)
    env["PYTHONPATH"] = out_dir + os.pathsep + env.get("PYTHONPATH", "")
    try:
        r = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
            cwd=common.ROOT, env=env, capture_output=True, text=True, timeout=60,
        )
        tail = (r.stderr or r.stdout).strip().splitlines()[-4:]
        return r.returncode == 0, "\n".join(tail)
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _verify_data(out_dir: str, constraints: dict[str, Any], record) -> None:
    """mall 类任务:静态校验数据文件(数量/id 连续/字段规则)。不起服务。"""
    data_file = constraints["data_file"]
    path = os.path.join(out_dir, data_file)
    if not os.path.exists(path):
        record(f"数据:{data_file} 存在", False, "缺失")
        return
    try:
        items = json.loads(common.read(path))
    except Exception as e:  # noqa: BLE001
        record(f"数据:{data_file} 合法 JSON", False, str(e))
        return
    if not isinstance(items, list):
        record("数据:为数组", False, "顶层不是数组")
        return

    min_items = constraints.get("min_items", 0)
    record(f"数据:商品数 ≥ {min_items}", len(items) >= min_items, f"实际 {len(items)}")

    start = constraints.get("id_sequential_from")
    if start is not None:
        ids = [it.get("id") for it in items]
        expect = list(range(start, start + len(items)))
        record("数据:id 从 1 连续", ids == expect, f"实际 {ids}")

    rules = constraints.get("field_rules", {})
    bad: list[str] = []
    for it in items:
        for field, rule in rules.items():
            v = it.get(field)
            if "max_len" in rule and isinstance(v, str) and len(v) > rule["max_len"]:
                bad.append(f"id{it.get('id')}.{field} 超长({len(v)}>{rule['max_len']})")
            if "min_len" in rule and isinstance(v, str) and len(v) < rule["min_len"]:
                bad.append(f"id{it.get('id')}.{field} 过短({len(v)}<{rule['min_len']})")
            if "gt" in rule and isinstance(v, (int, float)) and not v > rule["gt"]:
                bad.append(f"id{it.get('id')}.{field} 非 >{rule['gt']}")
            if "gte" in rule and isinstance(v, (int, float)) and not v >= rule["gte"]:
                bad.append(f"id{it.get('id')}.{field} 非 ≥{rule['gte']}")
    if rules:
        record("数据:字段规则", not bad, "; ".join(bad[:5]))


def _verify_markers(out_dir: str, constraints: dict[str, Any], record) -> None:
    """mall 类任务:校验模板/源文件里必须出现的 UI 标记(product-card / btn-cart / btn-buy)。"""
    for rel, pats in constraints.get("markers", {}).items():
        path = os.path.join(out_dir, rel)
        if not os.path.exists(path):
            record(f"标记:{rel} 存在", False, "缺失")
            continue
        src = common.read(path)
        miss = [p for p in pats if p not in src]
        record(f"标记:{rel} 含 {', '.join(pats)}", not miss,
               "缺: " + ", ".join(miss) if miss else "")


def verify(out_dir: str, facts: dict[str, Any], constraints: dict[str, Any]) -> list[dict[str, Any]]:
    """返回逐项结果列表 [{check, ok, detail}]。"""
    results: list[dict[str, Any]] = []

    def record(name: str, ok: bool, detail: str = "") -> bool:
        results.append({"check": name, "ok": bool(ok), "detail": detail})
        observ.emit("check.result", check=name, ok=bool(ok), detail=detail)
        return ok

    module_path = os.path.join(out_dir, facts["module"])
    if not os.path.exists(module_path):
        record("结构:模块文件存在", False, f"缺失 {facts['module']}")
        return results
    record("结构:模块文件存在", True)
    src = common.read(module_path)

    # 结构:每个声明函数都要有定义
    missing = [fn["name"] for fn in facts["functions"]
               if f"def {fn['name']}(" not in src]
    record("结构:函数定义齐全", not missing, "缺失: " + ", ".join(missing) if missing else "")

    # 安全:禁用模式
    hits = [p for p in constraints.get("banned_patterns", []) if p in src]
    record("安全:无禁用模式", not hits, "命中: " + ", ".join(hits) if hits else "")

    # 行数上限
    n_lines = len(src.splitlines())
    limit = constraints.get("max_lines", 9999)
    record(f"规范:行数 ≤ {limit}", n_lines <= limit, f"实际 {n_lines}")

    # 任务分支:有 data_file 的(mall)走静态数据/标记校验;否则(mathkit)跑固定单测。
    if constraints.get("data_file"):
        _verify_data(out_dir, constraints, record)
        _verify_markers(out_dir, constraints, record)
    else:
        # 测试:固定验收测试全绿(最强的一关)
        ok, tail = _run_tests(out_dir)
        record("测试:unittest 全绿", ok, tail if not ok else "")

    return results


def format_report(results: list[dict[str, Any]]) -> str:
    """把 verify 结果渲染成可回喂给模型的文本报告。"""
    passed = sum(1 for r in results if r["ok"])
    lines = [f"验收 {passed}/{len(results)}:"]
    for r in results:
        mark = "PASS" if r["ok"] else "FAIL"
        lines.append(f"  [{mark}] {r['check']}" + (f" — {r['detail']}" if r["detail"] else ""))
    return "\n".join(lines)


def all_ok(results: list[dict[str, Any]]) -> bool:
    return bool(results) and all(r["ok"] for r in results)
