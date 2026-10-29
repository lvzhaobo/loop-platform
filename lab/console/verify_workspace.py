#!/usr/bin/env python3
"""工作区绑定自检 —— 需求绑定哪个工作区，就真的改哪个仓库、过哪个门禁。"""
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


def call(m, p, b=None, timeout=25):
    d = json.dumps(b).encode() if b is not None else None
    req = urllib.request.Request(BASE + p, data=d, method=m,
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
    print("\n═══ 工作区绑定自检 ═══\n")
    subprocess.run([sys.executable, str(DEMO / "reset.py")], capture_output=True)

    print("[1] 工作区注册表")
    _, r = call("GET", "/api/workspaces")
    ids = [w["id"] for w in r.get("items", [])]
    check("至少两个工作区", len(ids) >= 2, ids)
    print(f"       → {ids}")

    print("\n[2] 建两个需求，绑不同工作区")
    _, a = call("POST", "/api/reqs", {"title": "番茄钟加自定义时长",
                                      "acceptance": "非法值回退", "workspace_id": "pomodoro"})
    _, b = call("POST", "/api/reqs", {"title": "客服意图识别",
                                      "acceptance": "连续两次 unknown 转人工", "workspace_id": "cs"})
    ra, rb = a["item"]["id"], b["item"]["id"]
    check("需求记住了工作区", a["item"]["workspace_id"] == "pomodoro"
          and b["item"]["workspace_id"] == "cs", (a["item"], b["item"]))
    print(f"       → {ra}=pomodoro　{rb}=cs")

    print("\n[3] 不合法的工作区被拒")
    code, _ = call("POST", "/api/reqs", {"title": "x", "workspace_id": "nope"})
    check("不存在的工作区返回 400", code == 400, code)

    print("\n[4] 只传 req_id 起运行 —— task 由需求决定")
    for _ in range(60):
        code, s = call("POST", "/api/specs/generate", {"req_id": rb, "mode": "batch"})
        if code == 202:
            break
        time.sleep(0.2)
    for _ in range(80):
        _, p = call("GET", f"/api/specs/progress?req_id={rb}")
        if p.get("generated") == 14:
            break
        time.sleep(0.1)

    code, r = call("POST", "/api/runs", {"req_id": rb})   # 故意不传 task
    run = r.get("run")
    check("运行已创建", code == 202 and run, r)

    approved, status, dl = 0, None, time.time() + 40
    while time.time() < dl:
        _, pa = call("GET", "/api/approvals")
        for it in pa.get("pending", []):
            call("POST", f"/api/approvals/{it['id']}", {"decision": "allow"})
            approved += 1
        _, st = call("GET", f"/api/runs/{run}")
        if st.get("item", {}).get("status") not in (None, "running"):
            status = st["item"]
            break
        time.sleep(0.15)
    check("运行结束", bool(status), "超时")
    check("跑的是 cs 工作区，不是 pomodoro",
          status and status.get("task") == "cs", status and status.get("task"))
    print(f"       → task={status.get('task')} gate={status.get('gate')} 批了 {approved} 次")

    print("\n[5] 产物真的落在 cs 里")
    sup = (DEMO / "shared" / "fixture" / "cs" / "support.py").read_text(encoding="utf-8")
    check("cs/support.py 被改了（有 RULES 表）", "RULES = [" in sup and "退款" in sup,
          sup[:60].replace("\n", " "))
    p = subprocess.run([sys.executable, str(DEMO / "shared" / "check-cs.py")],
                       capture_output=True, text=True)
    check("cs 门禁绿（9/9）", p.returncode == 0, p.stdout[-120:])

    print("\n[6] 另一个工作区没被误伤")
    js = (DEMO / "shared" / "fixture" / "pomodoro" / "app.js").read_text(encoding="utf-8")
    check("pomodoro 仍是原始版本", "clampMinutes" not in js, "被误改了")
    p2 = subprocess.run([sys.executable, str(DEMO / "shared" / "check.py")],
                        capture_output=True, text=True)
    check("pomodoro 门禁仍是红的（4/7）", "4/7" in p2.stdout, p2.stdout[-80:])

    subprocess.run([sys.executable, str(DEMO / "reset.py")], capture_output=True)
    print("\n" + "═" * 46)
    print(f"  {len(OK)} 通过 / {len(FAIL)} 失败")
    if FAIL:
        print("  失败项：" + "、".join(FAIL))
    print("═" * 46 + "\n")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
