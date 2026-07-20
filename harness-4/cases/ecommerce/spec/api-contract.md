# 接口契约(路由 / 响应 / 状态码)

## 1. 商品列表页(HTML)
`GET /` → 渲染 list.html,展示全部商品卡片

## 2. 商品详情页(HTML)
`GET /product/<int:id>` → 渲染 detail.html;id 不存在返回 404

## 3. 商品列表(JSON)
`GET /api/products` → 200,body 为商品数组

## 4. 商品详情(JSON)
`GET /api/products/<int:id>`
- 存在:200,单个商品对象
- 不存在:404,`{"error": "product not found"}`

## 路由清单(compile_spec 从此表派生 case.json.routes)
| 名称               | 路径                 |
|--------------------|----------------------|
| list               | /                    |
| detail_sample      | /product/1           |
| api_list           | /api/products        |
| api_detail_ok      | /api/products/1      |
| api_detail_missing | /api/products/9999   |
