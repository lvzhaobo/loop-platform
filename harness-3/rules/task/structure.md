# 任务约束 · 强制目录结构

```
app.py                    # Flask 入口,含全部路由
requirements.txt
README.md                 # 见 base/documentation.md
data/products.json        # 数据源
templates/
  ├── base.html
  ├── list.html           # 商品列表页
  └── detail.html         # 商品详情页
static/
  ├── css/style.css
  ├── js/main.js
  └── img/                # 本地占位图(可由 Harness 补齐)
tests/
  └── test_app.py         # 见 base/testing.md
```

## 命名规则
- 路由函数:列表 `product_list`,详情 `product_detail`,JSON 接口 `api_products` / `api_product_detail`
- Python 函数 snake_case,常量 UPPER_CASE
- 模板文件全小写
