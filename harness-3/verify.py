"""Harness-3 综合验证(case 驱动):标尺全部来自唯一事实源,无任何硬编码数值/字段。

用法: python harness-3/verify.py <case> <产物目录>
检查: 1 结构  2 数据  3 依赖  4 编码规范  5 单元测试(产物自带)  6 接口+真渲染 UI
任一失败返回非 0。
"""
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = os.environ.get("HARNESS_VERIFY_PORT", "5050")
BASE = f"http://127.0.0.1:{PORT}"


def fail(msg):
    print(f"[FAIL] {msg}")
    sys.exit(1)


def ok(msg):
    print(f"[OK]   {msg}")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def type_ok(value, kind):
    if kind == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def wait_ready(url, proc, timeout=15):
    """轮询等待被测应用就绪;启动即退出或超时 → 干净 fail(而非抛 traceback)。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            fail("被测应用启动即退出(app.py 崩溃,或端口被占)")
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except urllib.error.HTTPError:
            return  # 已响应(哪怕 4xx)即视为就绪
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.4)
    fail("被测应用 15s 内未就绪(端口未监听或启动过慢)")


if len(sys.argv) < 3:
    fail("用法: python harness-3/verify.py <case> <产物目录>")
case_name, out = sys.argv[1], sys.argv[2]
constraints = load_json(os.path.join(HARNESS_DIR, "constraints.json"))
case = load_json(os.path.join(HARNESS_DIR, "cases", case_name, "case.json"))
required = list(constraints["base_required_files"]) + list(case.get("extra_required_files", []))
min_items = case["min_items"]

# 1. 结构
for rel in required:
    if not os.path.exists(os.path.join(out, rel)):
        fail(f"缺文件 {rel}")
ok(f"结构完整(含 README / tests,共 {len(required)} 个必需文件)")

# 2. 数据
data = load_json(os.path.join(out, case["data_file"]))
if not isinstance(data, list) or len(data) < min_items:
    fail(f"数据条数 < {min_items}")
req_fields = set(case["required_fields"])
for it in data:
    if not req_fields <= set(it):
        fail(f"字段缺失: id={it.get('id')}")
    for fname, kind in case.get("numeric_fields", {}).items():
        if not type_ok(it.get(fname), kind):
            fail(f"字段类型错误: id={it.get('id')} {fname} 应为 {kind}")
ok(f"数据 {len(data)} 条,字段与类型齐全")

# 3. 依赖
req = read(os.path.join(out, "requirements.txt")).lower()
for ban in constraints["banned_deps"]:
    if ban in req:
        fail(f"命中禁用依赖 {ban}")
ok("无禁用依赖")

# 4. 编码规范
app_src = read(os.path.join(out, "app.py"))
loader = case["loader_function"]
if len(re.findall(rf"def\s+{re.escape(loader)}\s*\(", app_src)) != 1:
    fail(f"{loader} 必须且只能定义一次")
for fn in case["route_functions"]:
    if f"def {fn}" not in app_src:
        fail(f"缺路由函数 def {fn}")
inline = sum(read(p).count('style="') for p in glob.glob(os.path.join(out, "templates", "*.html")))
if inline > constraints["max_inline_style"]:
    fail(f"内联 style 过多({inline} 处,上限 {constraints['max_inline_style']})")
ok("编码规范(单函数/命名/内联样式)达标")

# 5. 单元测试(产物自带,stdlib unittest)
r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                   cwd=out, capture_output=True, text=True)
if r.returncode != 0:
    print(r.stdout[-800:] + r.stderr[-800:])
    fail("产物单元测试未通过")
ok("产物单元测试通过")

# 6. 接口 + 真渲染 UI
routes = case["routes"]
env = dict(os.environ, PORT=PORT)
proc = subprocess.Popen([sys.executable, "app.py"], cwd=out, env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    wait_ready(f"{BASE}{routes['list']}", proc)
    arr = json.loads(urllib.request.urlopen(f"{BASE}{routes['api_list']}", timeout=4).read())
    if len(arr) < min_items:
        fail(f"{routes['api_list']} 数据 < {min_items}")
    ok(f"接口 {routes['api_list']} 200 且 >= {min_items}")
    try:
        urllib.request.urlopen(f"{BASE}{routes['api_detail_missing']}", timeout=4)
        fail("不存在资源未返回 404")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            fail(f"错误码 {e.code}")
    ok("404 分支正确")

    # 真渲染:列表页标记数应 >= 数据条数
    html_list = urllib.request.urlopen(f"{BASE}{routes['list']}", timeout=4).read().decode("utf-8")
    cards = html_list.count(case["list_marker"])
    if cards < len(arr):
        fail(f"列表页渲染 {case['list_marker']} 数 {cards} < 数据条数 {len(arr)}")
    ok(f"真渲染:列表页 {cards} 个 {case['list_marker']}")

    # 真渲染:详情页必须包含全部 detail_markers
    html_detail = urllib.request.urlopen(f"{BASE}{routes['detail_sample']}", timeout=4).read().decode("utf-8")
    for m in case["detail_markers"]:
        if m not in html_detail:
            fail(f"详情页缺少标记 {m}")
    ok(f"真渲染:详情页标记齐全 {case['detail_markers']}")
finally:
    proc.terminate()

# UI 配色(来自事实源)
css = read(os.path.join(out, "static/css/style.css")).lower()
for color in case["colors"]:
    if color.lower() not in css:
        fail(f"CSS 缺少规定配色 {color}")
ok(f"UI 配色齐全 {case['colors']}")

print(f"\n✅ 用例 [{case_name}] 全部验收通过")
