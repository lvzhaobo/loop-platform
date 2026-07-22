"""Harness-4 验收器(Spec 驱动 / TC-AC 版)。

与 verify.py 的关系:
  - verify.py 是 **catalog 门禁**:硬读 case.json 的 catalog 字段(loader/list_marker/
    detail_markers/min_items...),即"必须是列表+详情站"。它是 --source fixed 的实现。
  - verify_ac.py 是 **Spec 门禁**:一行都不认应用类型,只做两件事——
      1) 通用安全护栏(禁用依赖 / 危险调用),与产物形态无关,任何应用都该过;
      2) 逐条执行 Spec 里声明的验收标准(TC/AC),来自 cases/<case>/spec/acceptance.json。
    这样"番茄时钟""芯片代码""语音模型"都不需要在门禁里穷举——门禁只认 Spec 声明了什么。

裁判不是运动员:acceptance.json 由 Spec(人写/人审)提供,门禁只负责忠实执行,
不自己发明验收标准。LLM 只能在 step2 把需求"解析成"这份 TC/AC,不能既解析又当门禁。

acceptance.json 结构:
  {
    "name": "pomodoro",
    "ready_route": "/",              # 可选,http 类断言前的就绪探测路由,默认 "/"
    "acceptance": [
      {"id":"TC1","type":"http_status","route":"/","expect":200,"desc":"首页可访问"},
      {"id":"TC2","type":"http_body_contains","route":"/","needle":"25:00","desc":"默认 25:00"},
      {"id":"TC3","type":"http_json_min","route":"/api/x","min":3,"desc":"接口返回≥3条"},
      {"id":"TC4","type":"file_exists","file":"static/js/timer.js","desc":"有计时脚本"},
      {"id":"TC5","type":"text_contains","file":"static/js/timer.js","needle":"setInterval"},
      {"id":"TC6","type":"text_absent","file":"app.py","needle":"list_marker"},
      {"id":"TC7","type":"unit_test","test":"tests/test_timer.py","desc":"单测全绿"},
      {"id":"AC1","type":"manual","desc":"结束有明显提示(声音/颜色),人工确认"}
    ]
  }

断言原语(闭集,可判定的自动执行,主观的落人工):
  file_exists      {file}
  text_contains    {file, needle, regex?}          文件含子串/正则
  text_absent      {file, needle, regex?}          文件不含
  http_status      {route, expect}                 起服务后 GET,状态码匹配
  http_body_contains {route, needle, status?}      响应体含子串(默认要求 200)
  http_json_min    {route, min}                    响应 JSON 数组长度 ≥ min
  unit_test        {test?}                          跑 unittest(指定文件或 discover)
  manual           {}                               人工抽检,不自动判定,报告里单列

用法: python harness-4/tools/verify_ac.py <case> <产物目录>
退出码: 全部可自动判定项通过=0,否则=1(manual 项不影响退出码,单独列出)。
"""
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

HARNESS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY_PORT = int(os.environ.get("HARNESS_VERIFY_PORT", "5060"))
BASE = f"http://127.0.0.1:{VERIFY_PORT}"

RESULTS = []  # {check, status: pass|fail|manual, detail}
HTTP_TYPES = {"http_status", "http_body_contains", "http_json_min"}


def record(name, ok, detail="", manual=False):
    status = "manual" if manual else ("pass" if ok else "fail")
    RESULTS.append({"check": name, "status": status, "detail": detail})
    tag = {"pass": "OK", "fail": "FAIL", "manual": "MANUAL"}[status]
    print(f"[{tag}] {name}" + (f" - {detail}" if detail else ""))
    return ok


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def http_get(path):
    """返回 (status, body_text);异常返回 (None, err)。"""
    try:
        with urllib.request.urlopen(BASE + path, timeout=8) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return None, str(e)


# ---------- 通用安全护栏(与应用类型无关,任何产物都该过) ----------

def check_security_guardrails(out, constraints):
    banned_deps = constraints.get("banned_deps", [])
    req = os.path.join(out, "requirements.txt")
    if banned_deps and os.path.exists(req):
        text = read(req).lower()
        hit = [d for d in banned_deps if d.lower() in text]
        record("护栏:无禁用依赖", not hit, "命中: " + ", ".join(hit) if hit else "")

    patterns = constraints.get("banned_code_patterns", [])
    hits = []
    for root, _, files in os.walk(out):
        if os.sep + "reports" in root:
            continue
        for fn in files:
            if fn.endswith(".py") and not fn.startswith("_"):
                text = read(os.path.join(root, fn))
                for p in patterns:
                    if p in text:
                        rel = os.path.relpath(os.path.join(root, fn), out)
                        hits.append(f"{rel}:{p}")
    if patterns:
        record("护栏:无危险调用", not hits, "; ".join(hits) if hits else "")


# ---------- 静态断言(无需起服务) ----------

def run_static(out, tc):
    t = tc["type"]
    desc = tc.get("desc") or ""
    name = f"{tc.get('id', t)}:{desc or t}"

    if t == "manual":
        return record(name, True, "需人工抽检", manual=True)

    if t == "file_exists":
        p = os.path.join(out, tc["file"])
        return record(name, os.path.exists(p), "" if os.path.exists(p) else f"缺失 {tc['file']}")

    if t in ("text_contains", "text_absent"):
        p = os.path.join(out, tc["file"])
        if not os.path.exists(p):
            return record(name, False, f"文件缺失 {tc['file']}")
        src = read(p)
        needle = tc["needle"]
        if tc.get("regex"):
            found = re.search(needle, src) is not None
        else:
            found = needle in src
        want = (t == "text_contains")
        ok = (found == want)
        return record(name, ok, "" if ok else (f"应含 '{needle}'" if want else f"不应含 '{needle}'"))

    if t == "unit_test":
        spec = tc.get("test")
        cmd = [sys.executable, "-m", "unittest"]
        cmd += [spec.replace("/", ".").rsplit(".py", 1)[0]] if spec else ["discover", "-s", "tests"]
        try:
            r = subprocess.run(cmd, cwd=out, capture_output=True, text=True, timeout=120)
            ok = r.returncode == 0
            tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
            return record(name, ok, " / ".join(tail) if not ok else "")
        except Exception as e:  # noqa: BLE001
            return record(name, False, str(e))

    return record(name, False, f"未知断言类型: {t}")


# ---------- 运行时断言(起一次服务,批量执行) ----------

def wait_ready(proc, path, timeout=40.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        status, _ = http_get(path)
        if status is not None:
            return True
        time.sleep(0.3)
    return False


def run_http_batch(out, http_tcs, ready_route):
    env = dict(os.environ)
    env["PORT"] = str(VERIFY_PORT)
    env.pop("WERKZEUG_SERVER_FD", None)
    env.pop("WERKZEUG_RUN_MAIN", None)
    proc = subprocess.Popen(
        [sys.executable, "app.py"], cwd=out, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    try:
        if not wait_ready(proc, ready_route):
            err = proc.stderr.read().decode("utf-8", "replace")[-300:] if proc.stderr else ""
            record("运行时:服务可启动", False, "未在超时内就绪; " + err)
            for tc in http_tcs:  # 服务起不来,http 断言全判失败
                record(f"{tc.get('id', tc['type'])}:{tc.get('desc') or tc['type']}", False, "服务未就绪")
            return
        record("运行时:服务可启动", True)

        for tc in http_tcs:
            t = tc["type"]
            name = f"{tc.get('id', t)}:{tc.get('desc') or t}"
            st, body = http_get(tc["route"])
            if t == "http_status":
                record(name, st == tc["expect"], f"status={st} 期望 {tc['expect']}")
            elif t == "http_body_contains":
                want_st = tc.get("status", 200)
                ok = st == want_st and tc["needle"] in body
                record(name, ok, f"status={st} 含'{tc['needle']}'={tc['needle'] in body}")
            elif t == "http_json_min":
                ok = st == 200
                n = -1
                try:
                    n = len(json.loads(body))
                    ok = ok and n >= tc["min"]
                except Exception:  # noqa: BLE001
                    ok = False
                record(name, ok, f"status={st} 条数={n} 期望≥{tc['min']}")
    finally:
        try:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()


# ---------- 报告 ----------

def write_reports(out, name):
    passed = sum(1 for r in RESULTS if r["status"] == "pass")
    failed = sum(1 for r in RESULTS if r["status"] == "fail")
    manual = sum(1 for r in RESULTS if r["status"] == "manual")
    auto = passed + failed
    all_ok = failed == 0
    report = {
        "case": name,
        "source": "spec",
        "passed": passed,
        "failed": failed,
        "manual": manual,
        "auto_total": auto,
        "all_ok": all_ok,
        "checks": RESULTS,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    rdir = os.path.join(out, "reports")
    os.makedirs(rdir, exist_ok=True)
    with open(os.path.join(rdir, "verify-ac-report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    lines = [f"# 验收报告(Spec/TC-AC) · {name}", "",
             f"自动 {passed}/{auto} 通过；{manual} 项待人工抽检", ""]
    for r in RESULTS:
        mark = {"pass": "x", "fail": " ", "manual": "~"}[r["status"]]
        lines.append(f"- [{mark}] {r['check']}" + (f" — {r['detail']}" if r['detail'] else ""))
    with open(os.path.join(rdir, "summary-ac.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return all_ok


def main():
    if len(sys.argv) < 3:
        sys.exit("用法: python harness-4/tools/verify_ac.py <case> <产物目录>")
    case_name, out = sys.argv[1], sys.argv[2]

    ac_path = os.path.join(HARNESS_DIR, "cases", case_name, "spec", "acceptance.json")
    if not os.path.exists(ac_path):
        sys.exit(f"缺少验收标准: {ac_path}\n"
                 f"(Spec 门禁需要 spec/acceptance.json;若走 catalog 请用 verify.py)")
    spec = load_json(ac_path)
    name = spec.get("name", case_name)
    acceptance = spec.get("acceptance", [])
    if not acceptance:
        sys.exit(f"acceptance.json 里 acceptance 为空: {ac_path}")

    constraints_path = os.path.join(HARNESS_DIR, "constraints.json")
    if os.path.exists(constraints_path):
        check_security_guardrails(out, load_json(constraints_path))

    http_tcs = [tc for tc in acceptance if tc["type"] in HTTP_TYPES]
    for tc in acceptance:
        if tc["type"] not in HTTP_TYPES:
            run_static(out, tc)
    if http_tcs:
        run_http_batch(out, http_tcs, spec.get("ready_route", "/"))

    all_ok = write_reports(out, name)
    passed = sum(1 for r in RESULTS if r["status"] == "pass")
    failed = sum(1 for r in RESULTS if r["status"] == "fail")
    manual = sum(1 for r in RESULTS if r["status"] == "manual")
    print(f"\n=== Spec 验收 {'通过' if all_ok else '未通过'}: "
          f"自动 {passed}/{passed + failed}，{manual} 项待人工 ===")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
