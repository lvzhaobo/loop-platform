# 通用基座 · 测试要求(跨任务,强制)

产物必须自带可运行的单元测试,由 Harness 自动执行,不通过即判定不合格。

- 测试文件:`tests/test_app.py`
- 框架:Python 标准库 `unittest`(禁止引入 pytest 等额外依赖)
- 运行方式:在产物根目录 `python -m unittest discover -s tests`,退出码必须为 0
- 测试使用 Flask 的 `app.test_client()`,不依赖真实网络端口
- 必测用例(路由取自本用例 `case.json.routes`,至少覆盖以下四类):
  1. `GET {api_list}` 返回 200,响应体必须是**裸 JSON 数组**(形如 `[{...}, ...]`),长度 ≥ `min_items`;**不得**包成 `{"items": [...]}` / `{"data": [...]}` 等对象
  2. `GET {api_list}/1`(存在项)返回 200 且为含 `id` 的单个对象
  3. `GET {api_detail_missing}` 返回 404
  4. `GET {list}`(首页)返回 200
- 测试若需导入产物入口,应把产物根目录加入 `sys.path` 后 `from app import app`
