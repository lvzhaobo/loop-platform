# 任务约束 · 编码规范

- `app.py` 顶部集中定义常量(`DATA_PATH`、`PORT`)
- 读 JSON 统一封装成**唯一一个** `case.json.loader_function` 指定的函数,禁止多处散读文件
- 涉及金额的字段,渲染保留两位小数;单位以 `spec/` 为准
- HTML 语义化;样式写在 `static/css/style.css`,模板中禁止大量内联 `style`(内联 style 出现次数 ≤ `constraints.json.max_inline_style`)
- 关键函数需 1 行中文注释
