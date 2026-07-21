"""harness-5 · 【Maker】的 sample 素材:淘宝风商城(mall 任务)。

与 lib/model.py 里 mathkit 的内置 _CORRECT/_BUGGY 平行:提供"先错后对"两份产物,
让 mall 任务在 sample 模式(离线、不烧额度)下也能直观演示 Loop。

  - CORRECT:8 条商品、id 连续、字段合规,模板含 product-card / btn-cart / btn-buy。
  - BUGGY  :只生成 7 条商品(少于 min_items、id 不连续)→ 被 gates 的数据门禁抓到。
             这与 mathkit 版"factorial 先错后对"是同一套教学套路。

注:这是【静态可校验】的产物。harness-5 的 Checker 用静态数据/标记校验(不起服务),
    保持 dependency-light、现场逐行可讲;harness-4 走的是"真起 Flask 打路由",更生产味。
"""
import json

# 8 条淘宝风商品(desc 均 ≥ 30 字,title ≤ 40 字,price > 0,sales ≥ 0)
_PRODUCTS = [
    {"id": 1, "title": "2024新款纯棉短袖T恤男夏季", "price": 59.90, "origin_price": 129.00,
     "sales": 3821, "image": "static/img/1.png", "shop": "优衣佳旗舰店",
     "desc": "100%新疆长绒棉,亲肤透气不易变形,夏季必备百搭款,多色可选。", "tags": ["包邮", "7天无理由"]},
    {"id": 2, "title": "轻薄羽绒服女短款2024冬", "price": 299.00, "origin_price": 599.00,
     "sales": 1520, "image": "static/img/2.png", "shop": "南极人官方旗舰店",
     "desc": "90%白鸭绒填充,轻盈保暖不臃肿,防风防泼水,通勤出行两相宜。", "tags": ["包邮"]},
    {"id": 3, "title": "真无线蓝牙耳机降噪入耳式", "price": 159.00, "origin_price": 399.00,
     "sales": 8830, "image": "static/img/3.png", "shop": "小米有品",
     "desc": "主动降噪35dB,单次续航8小时,充电仓总续航30小时,低延迟游戏模式。", "tags": ["包邮", "7天无理由"]},
    {"id": 4, "title": "陶瓷不粘煎锅家用平底锅", "price": 89.00, "origin_price": 199.00,
     "sales": 2140, "image": "static/img/4.png", "shop": "苏泊尔厨具",
     "desc": "德国不粘涂层,少油更健康,电磁炉燃气通用,耐磨易清洗手感佳。", "tags": ["包邮"]},
    {"id": 5, "title": "纯棉四件套简约北欧床品", "price": 199.00, "origin_price": 459.00,
     "sales": 976, "image": "static/img/5.png", "shop": "水星家纺",
     "desc": "60支新疆长绒棉,亲肤透气不起球,活性印染不掉色,四季通用款。", "tags": ["包邮", "货到付款"]},
    {"id": 6, "title": "机械键盘青轴有线电竞游戏", "price": 129.00, "origin_price": 259.00,
     "sales": 3567, "image": "static/img/6.png", "shop": "雷蛇旗舰店",
     "desc": "104键全尺寸,青轴段落感清脆,混光背光可调,金属面板坚固耐用。", "tags": ["包邮"]},
    {"id": 7, "title": "保温杯316不锈钢大容量便携", "price": 69.00, "origin_price": 159.00,
     "sales": 5210, "image": "static/img/7.png", "shop": "膳魔师官方",
     "desc": "316医用级不锈钢,12小时长效保温,一键弹盖单手开合,防漏耐摔。", "tags": ["包邮", "7天无理由"]},
    {"id": 8, "title": "运动跑步鞋男透气减震轻便", "price": 219.00, "origin_price": 499.00,
     "sales": 4680, "image": "static/img/8.png", "shop": "李宁官方旗舰店",
     "desc": "云科技中底回弹减震,飞织鞋面轻盈透气,防滑耐磨大底,长跑不累脚。", "tags": ["包邮"]},
]

_APP_PY = '''\
"""mall —— 由 harness-5 生成(sample 正确版)。淘宝风商品列表 + 详情。"""
import json
from pathlib import Path

from flask import Flask, abort, jsonify, render_template

app = Flask(__name__)
DATA = Path(__file__).parent / "data" / "products.json"


def load_products():
    """只读加载商品数据。"""
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


def _find(pid):
    return next((x for x in load_products() if x["id"] == pid), None)


@app.route("/")
def product_list():
    return render_template("list.html", products=load_products())


@app.route("/product/<int:id>")
def product_detail(id):
    p = _find(id)
    if p is None:
        abort(404)
    return render_template("detail.html", p=p)


@app.route("/api/products")
def api_products():
    return jsonify(load_products())


@app.route("/api/products/<int:id>")
def api_product_detail(id):
    p = _find(id)
    if p is None:
        return jsonify({"error": "product not found"}), 404
    return jsonify(p)


if __name__ == "__main__":
    app.run(debug=True)
'''

_LIST_HTML = '''\
<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <title>商品列表</title>
  <style>
    body { background: #F5F5F5; color: #333; font-family: sans-serif; margin: 0; }
    .search { height: 48px; background: #FF5000; color: #fff; line-height: 48px; padding: 0 16px; }
    .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; padding: 12px; }
    .product-card { background: #fff; border-radius: 4px; padding: 8px; text-decoration: none;
                    color: #333; transition: transform .2s; }
    .product-card:hover { transform: translateY(-4px); }
    .product-card img { width: 100%; border-radius: 4px; }
    .title { font-size: 14px; height: 40px; overflow: hidden; }
    .price { color: #FF0036; font-size: 20px; }
    .origin { color: #999; font-size: 12px; text-decoration: line-through; }
    .meta { color: #999; font-size: 12px; }
  </style>
</head>
<body>
  <div class="search">🔍 搜索你想要的宝贝</div>
  <div class="grid">
    {% for p in products %}
    <a class="product-card" href="/product/{{ p.id }}">
      <img src="{{ p.image }}" alt="{{ p.title }}">
      <div class="title">{{ p.title }}</div>
      <div class="price">¥{{ p.price }}</div>
      <div class="origin">¥{{ p.origin_price }}</div>
      <div class="meta">月销 {{ p.sales }} · {{ p.shop }}</div>
    </a>
    {% endfor %}
  </div>
</body>
</html>
'''

_DETAIL_HTML = '''\
<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <title>{{ p.title }}</title>
  <style>
    body { background: #F5F5F5; color: #333; font-family: sans-serif; margin: 0; }
    .wrap { display: flex; gap: 24px; padding: 24px; background: #fff; }
    .big { width: 400px; height: 400px; object-fit: cover; border-radius: 4px; }
    .title { font-size: 18px; }
    .price { color: #FF0036; font-size: 28px; }
    .origin { color: #999; text-decoration: line-through; }
    .tags span { background: #FFF0EB; color: #FF5000; font-size: 12px; padding: 2px 6px; margin-right: 6px; }
    .btn-cart { background: #FF5000; color: #fff; border: none; padding: 12px 24px; font-size: 16px; }
    .btn-buy { background: #FF0036; color: #fff; border: none; padding: 12px 24px; font-size: 16px; }
    .desc { padding: 24px; color: #333; }
  </style>
</head>
<body>
  <div class="wrap">
    <img class="big" src="{{ p.image }}" alt="{{ p.title }}">
    <div>
      <h1 class="title">{{ p.title }}</h1>
      <div class="price">¥{{ p.price }}</div>
      <div class="origin">¥{{ p.origin_price }}</div>
      <div class="tags">{% for t in p.tags %}<span>{{ t }}</span>{% endfor %}</div>
      <div class="meta">月销 {{ p.sales }} · {{ p.shop }}</div>
      <button class="btn-cart">加入购物车</button>
      <button class="btn-buy">立即购买</button>
    </div>
  </div>
  <div class="desc">{{ p.desc }}</div>
</body>
</html>
'''


def files(buggy: bool) -> dict[str, str]:
    """返回 {相对路径: 内容}。buggy=True 时只放 7 条商品(触发数据门禁失败)。"""
    n = 7 if buggy else 8
    products = _PRODUCTS[:n]
    return {
        "app.py": _APP_PY,
        "templates/list.html": _LIST_HTML,
        "templates/detail.html": _DETAIL_HTML,
        "data/products.json": json.dumps(products, ensure_ascii=False, indent=2) + "\n",
    }
