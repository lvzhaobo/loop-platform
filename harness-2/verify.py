"""Harness-2 综合验证:7 类检查,任一失败返回非 0。

1 结构  2 数据  3 依赖  4 编码规范  5 单元测试(产物自带)
6 接口 + 真渲染 UI  7 结构基线比对
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


if len(sys.argv) < 2:
    fail("用法: python harness-2/verify.py <产物目录>")
out = sys.argv[1]

# 1. 结构
manifest = json.load(open(os.path.join(HARNESS_DIR, "baseline", "manifest.json"), encoding="utf-8"))
for rel in manifest["required_files"]:
    if not os.path.exists(os.path.join(out, rel)):
        fail(f"缺文件 {rel}")
ok("结构完整(含 README / tests)")

# 2. 数据
data = json.load(open(os.path.join(out, "data/products.json"), encoding="utf-8"))
if not isinstance(data, list) or len(data) < 8:
    fail("商品数 < 8")
required_fields = {"id", "title", "price", "sales", "image", "shop", "desc"}
for it in data:
    if not required_fields <= set(it):
        fail(f"字段缺失: id={it.get('id')}")
    if not isinstance(it["price"], (int, float)) or not isinstance(it["sales"], int):
        fail(f"字段类型错误: id={it.get('id')}")
ok(f"数据 {len(data)} 条,字段与类型齐全")

# 3. 依赖
req = read(os.path.join(out, "requirements.txt")).lower()
for ban in ["django", "sqlalchemy", "vue", "react", "jquery", "bootstrap", "pytest"]:
    if ban in req:
        fail(f"命中禁用依赖 {ban}")
ok("无禁用依赖")

# 4. 编码规范
app_src = read(os.path.join(out, "app.py"))
if len(re.findall(r"def\s+load_products\s*\(", app_src)) != 1:
    fail("load_products 必须且只能定义一次")
for fn in ["def product_list", "def product_detail", "def api_products", "def api_product_detail"]:
    if fn not in app_src:
        fail(f"缺路由函数 {fn}")
inline = sum(read(p).count('style="') for p in glob.glob(os.path.join(out, "templates", "*.html")))
if inline > 2:
    fail(f"内联 style 过多({inline} 处,上限 2)")
ok("编码规范(单函数/命名/内联样式)达标")

# 5. 单元测试(产物自带,stdlib unittest)
r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                   cwd=out, capture_output=True, text=True)
if r.returncode != 0:
    print(r.stdout[-800:] + r.stderr[-800:])
    fail("产物单元测试未通过")
ok("产物单元测试通过")

# 6. 接口 + 真渲染 UI
env = dict(os.environ, PORT=PORT)
proc = subprocess.Popen([sys.executable, "app.py"], cwd=out, env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.5)
try:
    arr = json.loads(urllib.request.urlopen(f"{BASE}/api/products", timeout=4).read())
    if len(arr) < 8:
        fail("/api/products 数据 < 8")
    ok("接口 /api/products 200 且 >= 8")
    try:
        urllib.request.urlopen(f"{BASE}/api/products/9999", timeout=4)
        fail("不存在商品未返回 404")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            fail(f"错误码 {e.code}")
    ok("404 分支正确")

    # 真渲染:列表页卡片数应 == 商品数
    html_list = urllib.request.urlopen(f"{BASE}/", timeout=4).read().decode("utf-8")
    cards = html_list.count("product-card")
    if cards < len(arr):
        fail(f"列表页渲染卡片数 {cards} < 商品数 {len(arr)}")
    ok(f"真渲染:列表页 {cards} 张 product-card")

    # 真渲染:详情页两个按钮
    html_detail = urllib.request.urlopen(f"{BASE}/product/1", timeout=4).read().decode("utf-8")
    if html_detail.count("<button") < 2 or "btn-cart" not in html_detail or "btn-buy" not in html_detail:
        fail("详情页缺少 加入购物车/立即购买 两个按钮")
    ok("真渲染:详情页两个按钮存在")
finally:
    proc.terminate()

# UI 配色
css = read(os.path.join(out, "static/css/style.css")).lower()
if "#ff5000" not in css or "#ff0036" not in css:
    fail("CSS 缺少主色 #FF5000 或价格红 #FF0036")
ok("UI 配色 #FF5000 / #FF0036 存在")

# 7. 结构基线比对
produced = {os.path.relpath(p, out).replace(os.sep, "/")
            for p in glob.glob(os.path.join(out, "**", "*"), recursive=True)
            if os.path.isfile(p)}
missing = [f for f in manifest["required_files"] if f not in produced]
if missing:
    fail(f"结构基线缺项: {missing}")
ok("结构与基线 manifest 一致")

print("\n✅ 全部验收通过(7/7)")
