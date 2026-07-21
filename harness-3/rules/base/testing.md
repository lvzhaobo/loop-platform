# 通用基座 · 测试要求(跨任务,强制)

产物必须自带可运行的单元测试,由 Harness 自动执行,不通过即判定不合格。

- 测试文件:`tests/test_app.py`
- 框架:Python 标准库 `unittest`(禁止引入 pytest 等额外依赖)
- 运行方式:在产物根目录 `python -m unittest discover -s tests`,退出码必须为 0
- 必测用例(至少):
  1. `GET /api/products` 返回 200,且为长度 ≥ 8 的数组
  2. `GET /api/products/1` 返回 200 且为单个对象,含 id 字段
  3. `GET /api/products/9999` 返回 404
  4. `GET /` 返回 200
- 测试使用 Flask 的 `app.test_client()`,不依赖真实网络端口
