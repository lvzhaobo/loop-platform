你是代码生成器。严格依据随后提供的【通用基座 rules/base】【任务约束 rules/task】【本用例规格 spec】【唯一事实源 case.json】生成一个可运行的 Flask 项目,不得自由发挥。

要求:
1. 完全遵守技术栈与禁用项;端口从环境变量 PORT 读取,默认 5000。
2. 完全遵守目录结构与命名(含 README.md 与 tests/test_app.py)。
3. 数据文件按 data-model 生成不少于 case.json.min_items 条真实感数据,字段与类型严格匹配 required_fields / numeric_fields。
4. 路由、状态码严格匹配 api-contract;不存在资源按规范返回 404。
5. 样式严格匹配 ui-spec 的数值,并确保出现 case.json 里的 list_marker / detail_markers / colors。
6. app.py 中数据加载函数命名须等于 case.json.loader_function,且只定义一次;路由函数命名须等于 case.json.route_functions。
7. tests/test_app.py 用 stdlib unittest + app.test_client() 覆盖:列表页、详情页、JSON 列表、404 四类用例。
8. README.md 内容需真实对应本产物。
9. 生成后必须能通过 harness-3/verify.py 的全部检查项。

只输出代码文件,不输出解释。
