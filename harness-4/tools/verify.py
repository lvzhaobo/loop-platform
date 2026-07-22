"""Harness-4 验证器(case 驱动,深化版)。

相对 harness-3 的升级:
  1. 就绪轮询:不再固定 sleep,轮询列表路由直到 200(降低 CI flaky);
  2. 量化约束:按 case.field_rules 校验字段长度/数值范围/id 连续性(不止"存在+类型");
  3. 安全扫描:扫描 .py 是否出现 constraints.banned_code_patterns 危险调用;
  4. run 隔离报告:把逐项结果写入 <out>/reports/verify-report.json 与 summary.md;
  5. 全部检查收集后统一判定,一次看清所有问题(而非首错即停)。

用法: python harness-4/tools/verify.py <case> <产物目录>
"""
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

HARNESS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY_PORT = int(os.environ.get("HARNESS_VERIFY_PORT", "5060"))
BASE = f"http://127.0.0.1:{VERIFY_PORT}"

RESULTS = []


def record(name, ok, detail=""):
    RESULTS.append({"check": name, "ok": bool(ok), "detail": detail})
    print(f"[{'OK' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
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


# ---------- 静态检查 ----------

def check_structure(out, constraints, case):
    required = list(constraints["base_required_files"]) + list(case.get("extra_required_files", []))
    missing = [f for f in required if not os.path.exists(os.path.join(out, f))]
    record("结构:必备文件齐全", not missing, "缺失: " + ", ".join(missing) if missing else "")


def check_deps(out, constraints):
    path = os.path.join(out, "requirements.txt")
    if not os.path.exists(path):
        return record("依赖:requirements.txt 存在", False, "文件缺失")
    text = read(path).lower()
    hit = [d for d in constraints["banned_deps"] if d.lower() in text]
    record("依赖:无禁用项", not hit, "命中禁用: " + ", ".join(hit) if hit else "")


def check_security(out, constraints):
    patterns = constraints.get("banned_code_patterns", [])
    hits = []
    for root, _, files in os.walk(out):
        for fn in files:
            if fn.endswith(".py") and not fn.startswith("_"):
                text = read(os.path.join(root, fn))
                for p in patterns:
                    if p in text:
                        rel = os.path.relpath(os.path.join(root, fn), out)
                        hits.append(f"{rel}:{p}")
    record("安全:无危险调用", not hits, "; ".join(hits) if hits else "")


def check_conventions(out, constraints, case):
    app = os.path.join(out, "app.py")
    if not os.path.exists(app):
        return record("规范:app.py 存在", False, "缺失")
    src = read(app)
    loader = case["loader_function"]
    n = len(re.findall(r"def\s+" + re.escape(loader) + r"\s*\(", src))
    record(f"规范:{loader} 唯一定义", n == 1, f"出现 {n} 次")
    missing_fn = [fn for fn in case["route_functions"] if not re.search(r"def\s+" + re.escape(fn) + r"\s*\(", src)]
    record("规范:路由函数齐全", not missing_fn, "缺失: " + ", ".join(missing_fn) if missing_fn else "")
    total_inline = 0
    for tpl in ("templates/list.html", "templates/detail.html", "templates/base.html"):
        p = os.path.join(out, tpl)
        if os.path.exists(p):
            total_inline += read(p).count("style=")
    limit = constraints.get("max_inline_style", 2)
    record(f"规范:内联 style ≤ {limit}", total_inline <= limit, f"实际 {total_inline}")


def _field_error(rule, value):
    t = rule.get("type")
    if t == "int" and not isinstance(value, int):
        return "应为 int"
    if t == "number" and not isinstance(value, (int, float)):
        return "应为 number"
    if t == "string" and not isinstance(value, str):
        return "应为 string"
    if "max_len" in rule and isinstance(value, str) and len(value) > rule["max_len"]:
        return f"长度 {len(value)} > {rule['max_len']}"
    if "min_len" in rule and isinstance(value, str) and len(value) < rule["min_len"]:
        return f"长度 {len(value)} < {rule['min_len']}"
    if "gt" in rule and isinstance(value, (int, float)) and not value > rule["gt"]:
        return f"{value} 应 > {rule['gt']}"
    if "gte" in rule and isinstance(value, (int, float)) and not value >= rule["gte"]:
        return f"{value} 应 >= {rule['gte']}"
    return None


def check_data(out, case):
    path = os.path.join(out, case["data_file"])
    if not os.path.exists(path):
        return record("数据:文件存在", False, f"缺失 {case['data_file']}")
    try:
        arr = load_json(path)
    except Exception as e:  # noqa: BLE001
        return record("数据:JSON 合法", False, str(e))
    record("数据:JSON 合法", True)
    record(f"数据:条数 ≥ {case['min_items']}", len(arr) >= case["min_items"], f"实际 {len(arr)}")

    req = case["required_fields"]
    miss_rows = [i for i, it in enumerate(arr) if any(f not in it for f in req)]
    record("数据:必填字段齐全", not miss_rows, f"缺字段行: {miss_rows[:5]}" if miss_rows else "")

    rules = case.get("field_rules", {})
    errs = []
    for i, it in enumerate(arr):
        for f, rule in rules.items():
            if f in it:
                e = _field_error(rule, it[f])
                if e:
                    errs.append(f"#{i}.{f}: {e}")
    record("数据:field_rules 量化约束", not errs, "; ".join(errs[:6]) if errs else "")

    id_rule = rules.get("id", {})
    if "sequential_from" in id_rule:
        start = id_rule["sequential_from"]
        ids = [it.get("id") for it in arr]
        expect = list(range(start, start + len(arr)))
        record("数据:id 连续", ids == expect, f"实际 {ids[:8]}")

    if case.get("needs_images"):
        field = case.get("image_field")
        miss_img = []
        for it in arr:
            rel = it.get(field)
            if rel and not os.path.exists(os.path.join(out, str(rel).lstrip("/"))):
                miss_img.append(rel)
        record("数据:图片文件齐全", not miss_img, f"缺图: {miss_img[:5]}" if miss_img else "")


def check_css_colors(out, case):
    path = os.path.join(out, "static/css/style.css")
    if not os.path.exists(path):
        return record("UI:style.css 存在", False, "缺失")
    css = read(path).lower()
    missing = [c for c in case.get("colors", []) if c.lower() not in css]
    record("UI:CSS 含全部配色", not missing, "缺配色: " + ", ".join(missing) if missing else "")


# ---------- 测试层 ----------

def check_unittest(out):
    try:
        r = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            cwd=out, capture_output=True, text=True, timeout=120,
        )
        ok = r.returncode == 0
        tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
        record("测试:unittest 全绿", ok, " / ".join(tail) if not ok else "")
    except Exception as e:  # noqa: BLE001
        record("测试:unittest 全绿", False, str(e))


# ---------- 运行时真渲染 ----------

def _tcp_open(port, host="127.0.0.1", timeout=1.0):
    """端口是否已被监听(用于区分'进程还在但没绑端口' vs '已绑但没答 200')。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _drain(pipe):
    """读尽管道剩余内容(调用前须确保进程已结束,否则会阻塞)。"""
    if not pipe:
        return ""
    try:
        return pipe.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


def wait_ready(proc, path, timeout=40.0):
    """轮询列表路由直到 200;返回 (ok, reason)。
    reason: 'ok' | 'exit:<code>'(进程启动即退出) | 'timeout'(进程在跑但没答 200)。
    超时给到 40s:部分环境(host=0.0.0.0 时 getfqdn 反向解析慢)werkzeug 启动会白等几秒。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        rc = proc.poll()
        if rc is not None:
            return False, f"exit:{rc}"
        if http_get(path)[0] == 200:
            return True, "ok"
        time.sleep(0.3)
    return False, "timeout"


def startup_diag(proc, reason):
    """就绪失败时收集可操作诊断:被杀/自退 vs 超时,端口是否在听,stderr 尾部。
    关键:这段信息会被 generate.sh 回灌给下一轮生成,空诊断=白修。"""
    listening = _tcp_open(VERIFY_PORT)
    if proc.poll() is None:  # 超时:进程仍在,先终止才能非阻塞读管道
        try:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=3)
        except Exception:  # noqa: BLE001
            proc.kill()
            try:
                proc.wait(timeout=2)
            except Exception:  # noqa: BLE001
                pass
    tail = _drain(getattr(proc, "stderr", None)).strip()[-400:]
    if reason.startswith("exit:"):
        rc = reason.split(":", 1)[1].strip()
        killed = rc.startswith("-")  # 负数=被信号杀死(如 -9=SIGKILL,常见于 OOM 内存不足)
        head = (f"app.py 启动即退出 code={rc}(疑似被系统杀死,可能 OOM 内存不足)"
                if killed else f"app.py 启动即退出 code={rc}")
    else:
        head = f"未在超时内就绪(进程仍在运行,端口{'已监听但未答 200' if listening else '未监听'})"
    return head + ("; " + tail if tail else "; 无 stderr 输出")


def check_runtime(out, case):
    env = dict(os.environ)
    env["PORT"] = str(VERIFY_PORT)
    # 清除父进程(如 studio 的 Flask 调试重载器)注入的 werkzeug 套接字传递变量:
    # 否则被验收的 app.py 里 werkzeug 会去 socket.fromfd(继承来的 fd) 复用父进程套接字,
    # 在 Python 3.14 下触发 OSError: [Errno 9] Bad file descriptor,导致服务永远起不来。
    env.pop("WERKZEUG_SERVER_FD", None)
    env.pop("WERKZEUG_RUN_MAIN", None)
    proc = subprocess.Popen(
        [sys.executable, "app.py"], cwd=out, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    try:
        ok, reason = wait_ready(proc, case["routes"]["list"])
        if not ok:
            return record("运行时:服务可启动", False, startup_diag(proc, reason))
        record("运行时:服务可启动", True)

        arr_path = os.path.join(out, case["data_file"])
        n_data = len(load_json(arr_path)) if os.path.exists(arr_path) else 0
        routes = case["routes"]

        st, body = http_get(routes["api_list"])
        ok = st == 200
        try:
            ok = ok and len(json.loads(body)) >= case["min_items"]
        except Exception:  # noqa: BLE001
            ok = False
        record("接口:api_list 200 且数量达标", ok, f"status={st}")

        st, _ = http_get(routes["api_detail_missing"])
        record("接口:api_detail_missing → 404", st == 404, f"status={st}")

        st, html = http_get(routes["list"])
        list_html = html if st == 200 else ""
        cnt = html.count(case["list_marker"]) if st == 200 else 0
        record("渲染:列表页 list_marker 数达标", st == 200 and cnt >= n_data, f"marker={cnt} data={n_data}")

        # UI 结构硬校验:列表卡片必备子元素(每个 class 至少出现 n_data 次,即每张卡片都有)
        children = case.get("list_card_children") or []
        if children:
            n_expect = n_data if n_data else case["min_items"]
            missing = []
            for cls in children:
                c = len(re.findall(r'class="[^"]*\b' + re.escape(cls) + r'\b[^"]*"', html)) if st == 200 else 0
                if c < n_expect:
                    missing.append(f"{cls}({c}/{n_expect})")
            record("渲染:列表卡片必备子元素齐全", st == 200 and not missing,
                   ("缺/不足: " + ", ".join(missing)) if missing else "")

        st, html = http_get(routes["detail_sample"])
        missing_mk = [m for m in case["detail_markers"] if m not in html] if st == 200 else case["detail_markers"]
        record("渲染:详情页含全部 detail_markers", st == 200 and not missing_mk,
               f"status={st} 缺: {missing_mk}" if missing_mk else "")

        # 需求明确要求的字面文案:必须逐字出现在渲染后的页面(列表或详情任一)。
        # 这是把「需求关键约束」真正卡住的门禁:编译层保留进 case.must_contain_text,此处校验。
        must = case.get("must_contain_text") or []
        if must:
            rendered = list_html + (html if st == 200 else "")
            missing_txt = [t for t in must if t not in rendered]
            record("渲染:页面含全部指定文案", not missing_txt,
                   "缺文案: " + ", ".join(missing_txt) if missing_txt else "")
    finally:
        try:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()


# ---------- 报告 ----------

def write_reports(out, case):
    passed = sum(1 for r in RESULTS if r["ok"])
    total = len(RESULTS)
    report = {
        "case": case["name"],
        "passed": passed,
        "total": total,
        "all_ok": passed == total,
        "checks": RESULTS,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    rdir = os.path.join(out, "reports")
    os.makedirs(rdir, exist_ok=True)
    with open(os.path.join(rdir, "verify-report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    lines = [f"# 验收报告 · {case['name']}", "", f"通过 {passed}/{total}", ""]
    for r in RESULTS:
        lines.append(f"- [{'x' if r['ok'] else ' '}] {r['check']}" + (f" — {r['detail']}" if r['detail'] else ""))
    with open(os.path.join(rdir, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(out, "_verify.log"), "a", encoding="utf-8") as f:
        f.write(f"verify {passed}/{total} all_ok={passed == total} at={report['generated_at']}\n")
    return passed == total


def main():
    if len(sys.argv) < 3:
        sys.exit("用法: python harness-4/tools/verify.py <case> <产物目录>")
    case_name, out = sys.argv[1], sys.argv[2]
    constraints = load_json(os.path.join(HARNESS_DIR, "constraints.json"))
    case = load_json(os.path.join(HARNESS_DIR, "cases", case_name, "case.json"))

    check_structure(out, constraints, case)
    check_deps(out, constraints)
    check_security(out, constraints)
    check_conventions(out, constraints, case)
    check_data(out, case)
    check_css_colors(out, case)
    check_unittest(out)
    check_runtime(out, case)

    all_ok = write_reports(out, case)
    print(f"\n=== 验收 {'通过' if all_ok else '未通过'}: {sum(1 for r in RESULTS if r['ok'])}/{len(RESULTS)} ===")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
