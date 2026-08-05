# 任务约束 · 技术栈(强制,禁止偏离)

- 语言:Python 3.11+
- 后端框架:Flask 3.0.x(仅标准 Flask)
- 模板引擎:Jinja2
- 前端:原生 HTML5 + CSS3 + 原生 JavaScript(ES6)
- 数据存储:项目内 JSON 文件(具体路径见 `case.json.data_file`,如 `data/products.json` 或 `data/posts.json`)
- 依赖清单:`requirements.txt` 只允许 `Flask==3.0.*`(测试用 stdlib unittest,不新增依赖)
- 端口:`PORT = int(os.environ.get("PORT", 5000))`

## 禁用项(出现即不合格,以 `constraints.json.banned_deps` 为准)
- ❌ 任何数据库 / ORM
- ❌ 任何前端框架(React / Vue / jQuery / Bootstrap…)
- ❌ 任何 CDN 外链(JS / CSS 必须本地化)
- ❌ 构建工具、缓存中间件
