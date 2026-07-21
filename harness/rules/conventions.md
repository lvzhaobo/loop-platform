# 编码规范

- `app.py` 顶部集中定义常量(`DATA_PATH`、`PORT=5000`)
- 读 JSON 统一封装成 `load_products()` 一个函数,禁止散落多处读文件
- 所有金额字段单位为「元」,渲染时保留两位小数
- HTML 语义化标签;CSS 用 class,禁止大量内联 `style`
- 关键函数需 1 行中文注释说明用途
