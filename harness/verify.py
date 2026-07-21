"""自动验证产物是否达标:结构/数据/依赖/接口/UI。返回非 0 即不合格。"""
import sys, os, json, subprocess, time, urllib.request, urllib.error


def fail(msg):
    print(f"[FAIL] {msg}")
    sys.exit(1)


def ok(msg):
    print(f"[OK]   {msg}")


if len(sys.argv) < 2:
    fail("用法: python verify.py <产物目录>")
out = sys.argv[1]  # 产物目录,如 output/20260719-201500

# 1. 结构检查
for p in ["app.py", "requirements.txt", "data/products.json",
          "templates/list.html", "templates/detail.html",
          "static/css/style.css", "static/js/main.js"]:
    if not os.path.exists(os.path.join(out, p)):
        fail(f"缺文件 {p}")
ok("结构完整")

# 2. 数据检查
data = json.load(open(os.path.join(out, "data/products.json"), encoding="utf-8"))
if not isinstance(data, list) or len(data) < 8:
    fail("商品数 < 8")
required = {"id", "title", "price", "sales", "image", "shop", "desc"}
for it in data:
    if not required <= set(it):
        fail(f"字段缺失: {it.get('id')}")
ok(f"数据 {len(data)} 条,字段齐全")

# 3. 依赖禁用项检查
req = open(os.path.join(out, "requirements.txt")).read().lower()
for ban in ["django", "sqlalchemy", "vue", "react", "jquery", "bootstrap"]:
    if ban in req:
        fail(f"命中禁用依赖 {ban}")
ok("无禁用依赖")

# 4. 启动 + 接口检查
proc = subprocess.Popen([sys.executable, "app.py"], cwd=out)
time.sleep(2)
try:
    r = urllib.request.urlopen("http://127.0.0.1:5000/api/products", timeout=3)
    arr = json.loads(r.read())
    if r.status != 200 or len(arr) < 8:
        fail("/api/products 异常")
    ok("接口 200 且数据 >= 8")
    try:
        urllib.request.urlopen("http://127.0.0.1:5000/api/products/9999", timeout=3)
        fail("不存在商品未返回 404")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            ok("404 分支正确")
        else:
            fail(f"错误码 {e.code}")
finally:
    proc.terminate()

# 5. UI 数值检查(补齐 UI 盲区,让 checklist 承诺的都能被验)
css = open(os.path.join(out, "static/css/style.css"), encoding="utf-8").read().lower()
if "#ff5000" not in css:
    fail("主色 #FF5000 未出现在 CSS")
if "grid-template-columns" not in css and "grid" not in css and "flex" not in css:
    fail("未见栅格/弹性布局声明")
ok("UI 主色与布局声明存在")

print("\n✅ 全部验收通过")
