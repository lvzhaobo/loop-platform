# 任务约束 · 强制目录结构

固定骨架(所有用例共用,见 `constraints.json.base_required_files`):

```
app.py                    # Flask 入口,含全部路由
requirements.txt
README.md                 # 见 base/documentation.md
templates/
  ├── base.html
  ├── list.html           # 列表页
  └── detail.html         # 详情页
static/
  ├── css/style.css
  ├── js/main.js
  └── img/                # 本地占位图(按需,由 Harness 可补齐)
tests/
  └── test_app.py         # 见 base/testing.md
```

外加本用例专属文件(见 `case.json.extra_required_files`,如数据文件 `data/<entity>.json`)。

## 命名规则(具体名字取自 `case.json`,不得臆造)
- 路由函数:见 `case.json.route_functions`,顺序为「列表 / 详情 / JSON 列表 / JSON 详情」
- 数据加载函数:见 `case.json.loader_function`,**必须且只能定义一次**
- Python 函数 snake_case,常量 UPPER_CASE
- 模板文件全小写
