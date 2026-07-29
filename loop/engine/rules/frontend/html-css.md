# HTML / CSS 基础规范

> 适用条件: 所有前端项目（含 manifest.required_files 中的 HTML/CSS 文件）
> 状态: ✅ 始终生效

## HTML
- 语义化标签: `<header>`、`<nav>`、`<main>`、`<section>`、`<footer>`
- 表单用 `<label>` + `<input>`，带 `for` 属性
- 图片带 `alt` 属性
- 不写内联样式（`style=` 属性 ≤ 3 处）
- 移动端加 `<meta name="viewport" content="width=device-width, initial-scale=1.0">`

## CSS
- 类名用 kebab-case（如 `.product-card`、`.price-text`）
- 颜色用十六进制（如 `#FF5000`）或 CSS 变量
- 不使用 `!important`
- 优先使用 Flexbox / Grid 布局
- 响应式: 桌面 ≥ 768px，移动 < 768px
- 字体单位: `px`（固定）或 `rem`（相对），不用 `pt`

## 性能
- CSS 放在 `<head>` 中
- 图片压缩，不使用超过 200KB 的单张图片
- 关键 CSS 内联，非关键 CSS 外链
