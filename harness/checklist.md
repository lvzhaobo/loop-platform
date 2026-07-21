# 验收清单(每项必须能打勾,否则不合格)

## 结构
- [ ] 目录结构与 structure.md 完全一致
- [ ] requirements.txt 只含 Flask,无禁用依赖
- [ ] 无任何 CDN 外链、无前端框架

## 数据
- [ ] products.json 是合法 JSON 且 ≥ 8 条
- [ ] 每条含 data-model.md 全部必填字段,类型正确

## 运行
- [ ] pip install -r requirements.txt 成功
- [ ] python app.py 能启动,监听 5000

## 接口
- [ ] GET / 返回 200 且含商品卡片
- [ ] GET /api/products 返回 200 且为数组,长度 ≥ 8
- [ ] GET /api/products/1 返回 200 单对象
- [ ] GET /api/products/9999 返回 404

## UI
- [ ] 列表页每行 4 列卡片,主色 #FF5000 出现
- [ ] 价格为红色,详情页有两个按钮
