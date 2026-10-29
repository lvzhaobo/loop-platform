#!/usr/bin/env python3
"""端到端自检 —— 不开浏览器，纯 HTTP 走完整条链路。

  建需求 → 起运行 → 等审批 → 批准 → 门禁绿 → 核对产物

跑之前先起服务：python3 app.py
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8899"
DEMO = Path(__file__).resolve().parent.parent / "demo"
OK, FAIL = [], []


def call(method, path, body=None, timeout=20):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def check(name, cond, detail=""):
    (OK if cond else FAIL).append(name)
    print(("  ✅ " if cond else "  ❌ ") + name + ("" if cond else f"  ← {detail}"))


def main():
    print("\n═══ 平台后端端到端自检 ═══\n")

    # 0 复位 demo 的 fixture（否则上次跑完门禁已经是绿的）
    subprocess.run([sys.executable, str(DEMO / "reset.py")],
                   capture_output=True, text=True)

    print("[1] 健康检查")
    code, r = call("GET", "/api/health")
    check("服务在线", code == 200, code)

    print("\n[2] 建需求")
    code, r = call("POST", "/api/reqs", {
        "title": "番茄时钟支持自定义时长",
        "source": "飞书", "priority": "P1",
        "acceptance": "两个数字输入框；非法值回退 25/5；不改原有行为"})
    req_id = r.get("item", {}).get("id")
    check("需求创建成功", code == 201 and req_id, r)
    print(f"       → {req_id}")

    print("\n[3] 起运行")
    code, r = call("POST", "/api/runs", {"task": "pomodoro", "req_id": req_id})
    run_id = r.get("run")
    check("运行已创建", code == 202 and run_id, r)
    print(f"       → {run_id}")

    print("\n[4-6] 边跑边批（一次运行可能有多道审批）")
    approved, status, deadline = 0, None, time.time() + 40
    while time.time() < deadline:
        _, pa = call("GET", "/api/approvals")
        for item in pa.get("pending", []):
            call("POST", f"/api/approvals/{item['id']}", {"decision": "allow"})
            approved += 1
            print(f"       → 批准 {item['id']}：{item['action']} {item['detail']}")
        _, r = call("GET", f"/api/runs/{run_id}")
        it = r.get("item", {})
        if it.get("status") not in (None, "running"):
            status = it
            break
        time.sleep(0.15)
    check("至少批过一次（审批真的阻塞了工作线程）", approved >= 1, f"批了 {approved} 次")
    check("运行结束", bool(status), "40 秒没等到")
    if status:
        print(f"       → status={status.get('status')} gate={status.get('gate')} "
              f"steps={status.get('steps')} denied={status.get('denied')}")

    print("\n[7] 门禁真的绿了吗（绕过平台，直接跑脚本）")
    p = subprocess.run([sys.executable, str(DEMO / "shared" / "check.py")],
                       capture_output=True, text=True)
    tail = [l for l in p.stdout.splitlines() if "通过" in l]
    check("门禁退出码为 0", p.returncode == 0, p.stdout[-200:])
    print(f"       → {tail[-1].strip() if tail else '?'}")

    print("\n[8] 产物核对")
    js = (DEMO / "shared" / "fixture" / "pomodoro" / "app.js").read_text(encoding="utf-8")
    check("产物里有 clampMinutes", "clampMinutes" in js)
    check("产物里有上界判断", "MAX_MINUTES" in js)

    print("\n[9] 事件总线留下了痕迹")
    ev = (Path(__file__).resolve().parent / "data" / "events.jsonl")
    n = len(ev.read_text(encoding="utf-8").splitlines()) if ev.exists() else 0
    check("事件已落盘", n > 10, f"只有 {n} 条")
    print(f"       → {n} 条事件")

    print("\n[10] SSE 事件流（连接后先补发最近 50 条）")
    got = 0
    try:
        req = urllib.request.Request(BASE + "/api/events")
        with urllib.request.urlopen(req, timeout=3) as r:
            for _ in range(60):
                line = r.readline().decode().strip()
                if line.startswith("data:"):
                    got += 1
                    if got >= 5:
                        break
    except Exception as e:
        print(f"       （读超时属正常：SSE 是长连接）{type(e).__name__}")
    check("SSE 能补发历史事件", got >= 3, f"只收到 {got} 条")

    subprocess.run([sys.executable, str(DEMO / "reset.py")], capture_output=True)

    print("\n" + "═" * 46)
    print(f"  {len(OK)} 通过 / {len(FAIL)} 失败")
    if FAIL:
        print("  失败项：" + "、".join(FAIL))
    print("═" * 46 + "\n")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
