# 接口契约(路由 / 响应 / 状态码)

## 路由清单(compile_spec 从此表派生 case.json.routes)
| 名称               | 路径              |
|--------------------|-------------------|
| list               | /                 |
| detail_sample      | /recipe/1         |
| api_list           | /api/recipes      |
| api_detail_ok      | /api/recipes/1    |
| api_detail_missing | /api/recipes/9999 |
