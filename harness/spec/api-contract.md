# 接口契约(路由 / 入参 / 响应 / 状态码)

## 1. 商品列表页(HTML)
`GET /`
- 响应:渲染 `list.html`,展示全部商品卡片

## 2. 商品详情页(HTML)
`GET /product/<int:id>`
- 响应:渲染 `detail.html`;id 不存在返回 404

## 3. 商品列表(JSON API)
`GET /api/products`
- 响应 200,body 为商品数组(结构见 data-model)

## 4. 商品详情(JSON API)
`GET /api/products/<int:id>`
- 存在:响应 200,body 为单个商品对象
- 不存在:响应 404,body 为 `{"error": "product not found"}`
