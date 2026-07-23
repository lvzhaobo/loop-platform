# 番茄时钟-LOOP 需求规格

## 一句话概述
生成一个番茄时钟（Pomodoro Timer）单页交互工具，白色背景，中间使用番茄红色调，页面显示“Loop-20260721”文案。

## 核心交互
用户可启动/暂停/重置番茄时钟计时器，观察倒计时进度。

## 结构建议
- 前端：单页HTML（templates/index.html），CSS（static/css/style.css），JS（static/js/timer.js）处理计时逻辑和UI更新。
- 后端：Flask app.py 仅渲染首页（/），无额外JSON接口。
- 纯逻辑抽成独立Python模块：timer_core.py，包含计时核心函数（如计算剩余时间、状态转换），纯函数无副作用，便于单测。
- 测试：tests/test_timer_core.py 测试timer_core.py。

## 非目标
- 不是内容列表站，没有列表页/详情页/数据集/图鉴。
- 不涉及后端数据持久化（如JSON文件）。
- 不包含用户登录、历史记录等复杂功能。
