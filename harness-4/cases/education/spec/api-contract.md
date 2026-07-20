# 接口契约(路由 / 响应 / 状态码)

## 1. 课程列表页(HTML)
`GET /` → 渲染 list.html,展示全部课程卡片

## 2. 课程详情页(HTML)
`GET /course/<int:id>` → 渲染 detail.html;id 不存在返回 404

## 3. 课程列表(JSON)
`GET /api/courses` → 200,body 为课程数组

## 4. 课程详情(JSON)
`GET /api/courses/<int:id>`
- 存在:200,单个课程对象
- 不存在:404,`{"error": "course not found"}`

## 路由清单(compile_spec 从此表派生 case.json.routes)
| 名称               | 路径                |
|--------------------|---------------------|
| list               | /                   |
| detail_sample      | /course/1           |
| api_list           | /api/courses        |
| api_detail_ok      | /api/courses/1      |
| api_detail_missing | /api/courses/9999   |
