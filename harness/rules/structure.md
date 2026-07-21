# 生成产物的强制目录结构

```
app.py                    # Flask 入口,含全部路由
requirements.txt
data/products.json        # 数据源
templates/
  ├── base.html           # 公共布局
  ├── list.html           # 商品列表页
  └── detail.html         # 商品详情页
static/
  ├── css/style.css       # 全部样式
  ├── js/main.js          # 全部脚本
  └── img/                # 本地占位图
```

## 命名规则
- Python:函数 `snake_case`,常量 `UPPER_CASE`
- 路由函数名与用途一致(如 `product_list` / `product_detail`)
- 模板文件全小写,单词用连字符
