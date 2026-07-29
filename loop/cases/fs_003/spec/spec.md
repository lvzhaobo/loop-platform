# 图书电商Dashboard 需求规格

## 一句话概述
一个图书电商运营数据看板（Dashboard），以可视化卡片和图表展示关键业务指标，符合Dashboard风格。

## 核心交互
- 用户打开页面即看到仪表盘布局，包含多个数据卡片/图表（如销售额、订单量、库存、用户增长等）。
- 用户可查看实时或近实时更新的图书电商核心指标。
- 用户可通过交互（如点击、悬停）查看指标详情或切换时间范围（可选）。

## 结构建议
- 前端：单页HTML（templates/index.html），CSS（static/css/style.css），JS（static/js/dashboard.js）负责数据请求和渲染。
- 后端：Flask app.py 渲染首页（/），并提供少量JSON接口（如 /api/summary）返回模拟或静态数据。
- 纯逻辑抽成独立Python模块：`dashboard_core.py`，包含数据生成、计算、格式化等纯函数，无副作用，便于单测。
- 测试：tests/test_dashboard_core.py 测试核心逻辑。

## 非目标
- 不是内容列表站，没有列表页/详情页/数据集/图鉴。
- 不涉及用户登录、权限管理。
- 不涉及真实数据库或外部API调用（数据为模拟/静态）。
