你是代码生成器。严格依据以下约束生成一个可运行的电商项目,不得自由发挥:

【必读通用基座】harness-2/rules/base/ 下全部文件(安全 / 错误与日志 / 测试 / 文档)
【必读任务约束】harness-2/rules/task/ 下全部文件(技术栈 / 结构 / 规范)
【必读规格】harness-2/spec/ 下全部文件(数据 / 接口 / UI)

要求:
1. 完全遵守技术栈与禁用项;端口从环境变量 PORT 读取,默认 5000。
2. 完全遵守目录结构与命名(含 README.md 与 tests/test_app.py)。
3. data/products.json 按 data-model 生成 ≥8 条真实感数据。
4. 路由严格匹配 api-contract;不存在资源按规范返回 404。
5. 样式严格匹配 ui-spec 的数值(#FF5000 / #FF0036 / 4 列栅格 / product-card / btn-cart / btn-buy)。
6. tests/test_app.py 用 stdlib unittest + app.test_client() 覆盖 4 条必测用例。
7. README.md 内容需真实对应本产物。
8. 生成完成后,项目必须能通过 harness-2/checklist.md 全部检查项。

只输出代码文件,不输出解释。
