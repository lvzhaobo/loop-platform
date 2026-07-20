| 文件名 | 路径 | 类型 | 层级 | 作用 | 大致内容 | 是否事实源 | 参与门禁阶段 | 行数 |
|---|---|---|---|---|---|---|---|---|
| constraints.json | harness-4/constraints.json | JSON | 全局事实源 | 定义全局硬约束(技术栈/必备文件/禁用项/安全模式/用例集/运行集) | tech 块、base_required_files、banned_deps、banned_code_patterns、max_inline_style、cases、run_cases | ✅ 是 | 全阶段读取 | 44 |
| VERSION | harness-4/VERSION | 文本 | 元信息 | 记录 Harness 版本号 | `4.0.0` | 否 | 无 | 1 |
| README.md | harness-4/README.md | Markdown | 文档 | 框架总览、理念、用法说明 | 设计理念、目录结构、运行命令、确定性说明 | 否 | 无 | 105 |
| checklist.md | harness-4/checklist.md | Markdown | 文档 | 人工验收/新增用例检查清单 | 分步 checklist 条目 | 否 | 无(人工参考) | 47 |
| config.env | harness-4/config.env | Shell env | 配置 | 运行时开关与确定性参数 | 模型名、temperature、seed、验证端口、HARNESS_CASES、DET_CHECK、MODE | 否 | 被 generate.sh 载入 | 25 |
| prompt.md | harness-4/prompt.md | Markdown | 提示词 | 场景中立的系统提示(喂给 LLM) | 输出信封协议、角色、通用生成规则(无领域词汇) | 否 | 生成阶段 | 22 |
| gate.sh | harness-4/gate.sh | Bash | 编排入口 | 门禁总入口,串联三关 | 依次调 check_consistency → build_schema → generate.sh | 否 | 门禁总控 | 21 |
| generate.sh | harness-4/generate.sh | Bash | 编排 | 多用例生成+验证闭环 | 用例循环、失败带反馈重试、确定性复跑、写 runs.jsonl | 否 | 门禁 3/3 | 78 |
| setup.sh | harness-4/setup.sh | Bash | 脚手架 | 初始化虚拟环境/依赖 | 建 venv、装 Flask | 否 | 无 | 16 |
| tools/run_model.py | harness-4/tools/run_model.py | Python | 生成器 | 调 DeepSeek 或离线生成器产出代码 | real 模式调 API+解析信封+补图;sample 模式转发;写 meta | 否 | 生成阶段 | 206 |
| tools/verify.py | harness-4/tools/verify.py | Python | 验证器 | 对产物做全维度硬校验 | 结构/依赖/安全/规范/数据(field_rules)/CSS/unittest/真渲染/UI子元素 + 隔离报告 | 否 | 门禁 3/3(验收) | 311 |
| tools/check_consistency.py | harness-4/tools/check_consistency.py | Python | 门禁 | 校验 case.json ↔ spec 不漂移 | 用例登记一致性、字段/数值/marker/颜色在 spec 有落点 | 否 | 门禁 1/3 | 92 |
| tools/build_schema.py | harness-4/tools/build_schema.py | Python | 派生工具 | 从 case.json 派生 JSON Schema | 遍历 required_fields+field_rules → draft-07 schema | 否(派生物) | 门禁 2/3 | 65 |
| tools/sample_generator.py | harness-4/tools/sample_generator.py | Python | 离线生成器 | 无密钥确定性产出可过 verify 的参考实现 | 纯字符串拼接生成 app/模板/CSS/数据/测试,支持图片与卡片子元素 | 否 | 生成阶段(sample) | 307 |
| ci/github-actions.yml | harness-4/ci/github-actions.yml | YAML | CI | GitHub Actions 流水线 | checkout→setup→sample 模式跑 gate | 否 | CI | 38 |
| rules/base/security.md | harness-4/rules/base/security.md | Markdown | 通用规则 | 安全基线规则 | 禁危险调用、输入校验等 | 否 | 生成阶段(喂模型) | 8 |
| rules/base/error-and-logging.md | harness-4/rules/base/error-and-logging.md | Markdown | 通用规则 | 错误处理与日志规则 | 异常捕获、日志规范 | 否 | 生成阶段 | 6 |
| rules/base/testing.md | harness-4/rules/base/testing.md | Markdown | 通用规则 | 测试要求(场景中立) | 4 个必测用例用占位符引用 routes | 否 | 生成阶段 | 14 |
| rules/base/documentation.md | harness-4/rules/base/documentation.md | Markdown | 通用规则 | 文档/注释规则 | README、docstring 要求 | 否 | 生成阶段 | 10 |
| rules/task/tech-stack.md | harness-4/rules/task/tech-stack.md | Markdown | 任务规则 | 技术栈约束 | Flask/Jinja/stdlib,引用 case.json 字段 | 否 | 生成阶段 | 15 |
| rules/task/structure.md | harness-4/rules/task/structure.md | Markdown | 任务规则 | 目录结构约束 | 文件布局,引用 data_file/loader 等 | 否 | 生成阶段 | 27 |
| rules/task/conventions.md | harness-4/rules/task/conventions.md | Markdown | 任务规则 | 编码规范 | 唯一 loader、路由函数命名等 | 否 | 生成阶段 | 7 |
| cases/ecommerce/case.json | harness-4/cases/ecommerce/case.json | JSON | 用例事实源 | 电商用例专属事实 | entity/字段/field_rules/路由/marker/配色/图片 | ✅ 是 | 全阶段(该用例) | 31 |
| cases/ecommerce/spec/data-model.md | harness-4/cases/ecommerce/spec/data-model.md | Markdown | 用例契约 | 电商数据模型契约 | 字段表、数据量、示例 JSON | 否(契约) | 门禁 1/3 | 31 |
| cases/ecommerce/spec/api-contract.md | harness-4/cases/ecommerce/spec/api-contract.md | Markdown | 用例契约 | 电商接口契约 | 路由/响应/状态码/404 | 否(契约) | 门禁 1/3 | 15 |
| cases/ecommerce/spec/ui-spec.md | harness-4/cases/ecommerce/spec/ui-spec.md | Markdown | 用例契约 | 电商 UI 规范 | 配色、列表/详情结构、marker | 否(契约) | 门禁 1/3 | 21 |
| cases/blog/case.json | harness-4/cases/blog/case.json | JSON | 用例事实源 | 博客用例专属事实 | entity/字段/field_rules/路由/marker/配色 | ✅ 是 | 全阶段(该用例) | 30 |
| cases/blog/spec/data-model.md | harness-4/cases/blog/spec/data-model.md | Markdown | 用例契约 | 博客数据模型契约 | 字段表、数据量、示例 JSON | 否(契约) | 门禁 1/3 | 27 |
| cases/blog/spec/api-contract.md | harness-4/cases/blog/spec/api-contract.md | Markdown | 用例契约 | 博客接口契约 | 路由/响应/状态码/404 | 否(契约) | 门禁 1/3 | 15 |
| cases/blog/spec/ui-spec.md | harness-4/cases/blog/spec/ui-spec.md | Markdown | 用例契约 | 博客 UI 规范 | 配色、列表/详情结构、marker | 否(契约) | 门禁 1/3 | 20 |
| cases/education/case.json | harness-4/cases/education/case.json | JSON | 用例事实源 | 教育用例专属事实 | entity/字段/field_rules/路由/marker/配色/图片/list_card_children | ✅ 是 | 全阶段(该用例) | 32 |
| cases/education/spec/data-model.md | harness-4/cases/education/spec/data-model.md | Markdown | 用例契约 | 教育数据模型契约 | 字段表、数据量、示例 JSON | 否(契约) | 门禁 1/3 | 30 |
| cases/education/spec/api-contract.md | harness-4/cases/education/spec/api-contract.md | Markdown | 用例契约 | 教育接口契约 | 路由/响应/状态码/404 | 否(契约) | 门禁 1/3 | 15 |
| cases/education/spec/ui-spec.md | harness-4/cases/education/spec/ui-spec.md | Markdown | 用例契约 | 教育 UI 规范 | 配色、卡片四件套子元素(硬性)、详情结构 | 否(契约) | 门禁 1/3 | 25 |
| schemas/ecommerce.data.schema.json | harness-4/schemas/ecommerce.data.schema.json | JSON | 派生产物 | 电商数据 JSON Schema | 由 build_schema 生成的 draft-07 schema | 否(派生物) | 门禁 2/3 输出 | 44 |
| schemas/blog.data.schema.json | harness-4/schemas/blog.data.schema.json | JSON | 派生产物 | 博客数据 JSON Schema | 由 build_schema 生成 | 否(派生物) | 门禁 2/3 输出 | 39 |
| schemas/education.data.schema.json | harness-4/schemas/education.data.schema.json | JSON | 派生产物 | 教育数据 JSON Schema | 由 build_schema 生成 | 否(派生物) | 门禁 2/3 输出 | 48 |
