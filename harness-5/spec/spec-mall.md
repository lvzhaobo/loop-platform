# 规格:淘宝风商城 —— 商品列表 + 详情

> 这是**人读规格**(自然语言契约),沿用 harness-3 / harness-4 的电商用例(`ecommerce`)。
> 机器可读的唯一事实源见 `spec/facts.json`。门禁会检查:facts.json 里声明的每个函数/入口,
> 都必须能在本文件里找到落点(自洽性)。
>
> ⚠️ 这是一份「换个 task」的规格样例(对照原 `spec.md` 的 mathkit)。要让 harness-5 真正端到端
> 生成它,还需同步切换 `spec/facts.json`、`constraints.json`、`tests/`、`lib/model.py` 模板
> —— 详见文末「切换清单」。

## 目标

用 **Python3 + Flask + Jinja2** 生成一个淘宝风格的商品站:**列表页**展示所有商品卡片,**详情页**看单个商品。数据来自只读的 `data/products.json`,不引数据库、不引第三方前端框架。

## 数据模型:`data/products.json`(数组,每个元素如下)

| 字段         | 类型   | 必填 | 说明                          |
|--------------|--------|------|-------------------------------|
| id           | int    | 是   | 唯一,从 1 连续递增            |
| title        | string | 是   | 商品标题,≤ 40 字              |
| price        | float  | 是   | 现价(元),> 0                |
| origin_price | float  | 否   | 划线原价(元)                |
| sales        | int    | 是   | 月销量,≥ 0                    |
| image        | string | 是   | 本地图路径 `static/img/<id>.png` |
| shop         | string | 是   | 店铺名                        |
| desc         | string | 是   | 详情描述,≥ 30 字              |
| tags         | array  | 否   | 促销标签,如 `["包邮","7天无理由"]` |

### 数据量要求
- 至少 **8** 条商品,`id` 连续 `1~8`。

### 示例
```json
{
  "id": 1,
  "title": "2024新款纯棉短袖T恤男夏季",
  "price": 59.90,
  "origin_price": 129.00,
  "sales": 3821,
  "image": "static/img/1.png",
  "shop": "优衣佳旗舰店",
  "desc": "100%新疆长绒棉,亲肤透气,不易变形,夏季必备百搭款。",
  "tags": ["包邮", "7天无理由"]
}
```

## 接口契约(路由 / 响应 / 状态码)

| # | 方法与路径 | 说明 |
|---|-----------|------|
| 1 | `GET /` | 渲染 `list.html`,展示全部商品卡片 |
| 2 | `GET /product/<int:id>` | 渲染 `detail.html`;id 不存在返回 **404** |
| 3 | `GET /api/products` | `200`,body 为商品数组 |
| 4 | `GET /api/products/<int:id>` | 存在 `200`(单个对象);不存在 **404** `{"error": "product not found"}` |

## UI 规范(淘宝风格,确定数值)

### 配色
- 主色(淘宝橙):`#FF5000`
- 价格红:`#FF0036`
- 背景灰:`#F5F5F5`;文字主色 `#333333`;次要 `#999999`

### 列表页
- 顶部搜索栏高 `48px`,橙色搜索按钮。
- 商品栅格每行 **4 列**(桌面),卡片间距 `12px`;卡片白底、圆角 `4px`、hover 上浮。
- 卡片内容顺序:方图 → 标题(2 行截断)→ 红色价格 → 灰色划线原价 → 月销量 → 店铺。
- 每个商品卡片根元素带 class **`product-card`**(列表页验收标记)。

### 详情页
- 左侧大图 ≥ `400px` 方形,右侧信息区。
- 红色大号价格 + 划线原价 + 标签。
- 两个按钮:`加入购物车`(橙,class **`btn-cart`**)+ `立即购买`(红,class **`btn-buy`**)。
- 下方为描述区。

### 字号
- 标题 `14px`、价格 `20px`、次要 `12px`。

## 函数落点(供自洽性门禁校验)

> harness-5 的自洽性门禁会逐个检查 `facts.json` 声明的函数名是否出现在本文件。切换到本规格时,
> `facts.json` 应声明以下函数,它们的落点如下:

- **`load_products`** —— 数据加载器:只读加载 `data/products.json`,返回商品数组。
- **`product_list`** —— 路由 `GET /`:渲染列表页(含所有 `product-card`)。
- **`product_detail`** —— 路由 `GET /product/<int:id>`:渲染详情页(含 `btn-cart`/`btn-buy`),越界/不存在 404。
- **`api_products`** —— 路由 `GET /api/products`:返回商品数组 JSON。
- **`api_product_detail`** —— 路由 `GET /api/products/<int:id>`:返回单个商品或 404 JSON。

## 约束(与 constraints.json 一致)

- 技术栈:Python3 + Flask + Jinja2;数据源为 JSON 文件,**不引数据库、不引前端框架**。
- 数据加载只允许一个 loader(`load_products`),路由函数命名遵循上节。
- 禁止 `eval(` / `exec(` / `os.system` / `import os` / `subprocess` 等危险调用。
- 详情页 `id` 转 `int`,不存在一律 404,不得返回异常堆栈。

---

## 切换清单(把本规格接进 harness-5 流水线时需同步改)

| 文件 | 从(mathkit) | 改到(mall) |
|------|--------------|-------------|
| `spec/facts.json` | `module: mathkit.py` + 4 个数学函数 | `module`/`entity` 换成 product,`functions` 换成上节 5 个 loader/route |
| `constraints.json` | `module: mathkit.py`、行数上限 | 换成 Flask 项目约束(禁用依赖、必需文件、路由等) |
| `tests/` | `test_mathkit.py` | 换成起 Flask 打 4 条路由(list 200 含 `product-card`、detail 200、api 数组、缺失 404) |
| `lib/model.py` | `_CORRECT` / `_BUGGY`(mathkit 文本) | 换成生成 Flask 应用的模板(或切 `real` 模式让真实模型生成) |

> 想要我把上面这几处一并切过去、让 `python3 harness-5/l1_harness/gate.py` 能真正跑这个商城用例吗?
> 那会是一个更大的改动(等于给 harness-5 加一个"电商"任务档),但完全可做。
