# 技术栈(强制,禁止偏离)

- 语言:Python 3.11
- 后端框架:Flask 3.0.x(仅用标准 Flask,不引入 Flask-RESTful 等扩展)
- 模板引擎:Jinja2(Flask 自带)
- 前端:原生 HTML5 + CSS3 + 原生 JavaScript(ES6)
- 数据存储:项目内 JSON 文件,路径 `data/products.json`
- 依赖清单:`requirements.txt` 只允许出现 `Flask==3.0.*`

## 禁用项(出现即判定不合格)
- ❌ 任何数据库(SQLite / MySQL / MongoDB…)
- ❌ 任何前端框架(React / Vue / jQuery / Bootstrap…)
- ❌ 任何 CDN 外链(所有 JS/CSS 必须本地化)
- ❌ ORM、缓存中间件、构建工具(webpack / vite…)
