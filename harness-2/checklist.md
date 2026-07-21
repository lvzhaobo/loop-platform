# 验收清单(harness-2,7 类,每项须打勾)

## 1 结构
- [ ] 含 app.py / requirements.txt / README.md / data / templates×3 / static / tests/test_app.py
- [ ] 结构与 baseline/manifest.json 一致

## 2 数据
- [ ] products.json 合法且 ≥ 8 条
- [ ] 必填字段齐全,price/sales 类型正确

## 3 依赖
- [ ] requirements.txt 只含 Flask,无禁用依赖(含 pytest)

## 4 编码规范
- [ ] load_products 仅定义一次
- [ ] 四个路由函数命名正确
- [ ] 模板内联 style ≤ 2 处

## 5 测试层
- [ ] 产物自带 tests/test_app.py
- [ ] python -m unittest 全部通过

## 6 接口 + 真渲染 UI
- [ ] /api/products 200 且 ≥ 8;/api/products/9999 → 404
- [ ] 列表页渲染出的 product-card 数 ≥ 商品数
- [ ] 详情页含 btn-cart + btn-buy 两个按钮
- [ ] CSS 含 #FF5000 与 #FF0036

## 7 确定性
- [ ] _run_meta.json 记录 model/temperature/seed/version
