# 接口契约(路由 / 响应 / 状态码)

## 1. 文章列表页(HTML)
`GET /` → 渲染 list.html,展示全部文章卡片

## 2. 文章详情页(HTML)
`GET /post/<int:id>` → 渲染 detail.html;id 不存在返回 404

## 3. 文章列表(JSON)
`GET /api/posts` → 200,body 为文章数组

## 4. 文章详情(JSON)
`GET /api/posts/<int:id>`
- 存在:200,单个文章对象
- 不存在:404,`{"error": "post not found"}`
