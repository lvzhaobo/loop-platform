# 架构选型与技术设计 – FS-002

## 1. 整体技术栈
- **后端**：Python 3.9+ / Flask
- **数据交换**：JSON
- **数据存储**：无持久化数据库，使用内存数据结构 + JSON 配置文件。
- **前端**：单页面原生 HTML + CSS + JavaScript，无打包工具，直接由 Flask 作为静态文件 hosting（或直接浏览器打开，后端仅提供 API）。
- **部署**：开发环境 `flask run`，调试模式开启，监听 `127.0.0.1:5000`。

## 2. 系统组件图
```
+------------+       HTTP/JSON        +-------------+
|   Browser  | <--------------------> |  Flask API  |
| (HTML/CSS) |  fetch('/api/...')     |  (Python)   |
+------------+                        +------+------+
                                      |  Memory  |
                                      |  steps   |
                                      +----------+
                                      |  config.json (colors, defaults)
                                      +----------+
```

## 3. 后端架构
- **Flask 应用**：单一文件 `app.py`，包含所有路由。
- **路由**：
  - `GET  /api/array` – 生成随机数组
  - `POST /api/sort` – 计算排序步骤
  - `POST /api/sort/control` – 管理状态（pause/resume/reset）
  - `GET  /api/meta` – 返回元数据
- **状态管理**：由于前端的暂停/继续仅控制前端动画，后端无需维护会话状态；`reset` 命令仅返回新数组，不关联旧步骤。因此服务端为**无状态**设计，所有请求独立。
- **配置**：`config.json` 文件存储默认数组大小范围、颜色映射等，服务启动时加载。格式示例：
  ```json
  {
    "defaultSize": 20,
    "minSize": 5,
    "maxSize": 50,
    "colors": {
      "compare": "#e74c3c",
      "swap": "#f39c12",
      "sorted": "#2ecc71",
      "default": "#3498db"
    },
    "identifier": "Loop-20260723"
  }
  ```
- **排序算法**：`algorithms.py` 模块，当前仅实现冒泡排序并生成步骤列表。输入数组，返回步骤列表。
- **错误处理**：全局异常捕获，返回统一 JSON 错误格式。

## 4. 前端架构
- **文件**：`index.html`，内嵌 CSS 和 JS。
- **状态机**：`idle` → `sorting` →（`paused`↔`sorting`）→ `complete` → `idle`
- **数据流**：
  1. DOMContentLoaded → 请求 `meta`、`array`，初始化 UI。
  2. 用户点击“开始排序” → 构造请求 → 获取 `steps` → 启动动画循环。
  3. 动画循环通过 `setTimeout` 迭代 `steps` 数组，根据 `type` 和 `indices` 更新条形高度与颜色。
  4. 控制按钮直接发送 `/sort/control` 命令，暂停/继续通过清除/重启定时器实现；重置先终止动画，使用新数组重绘。
- **条形图渲染**：使用 `div` 元素绝对定位，每个条形宽度固定，高度与数值成正比，背景色通过 CSS 控制。

## 5. 数据存储说明
- **JSON 文件存储**：本系统无持久化业务数据需求，采用 `config.json` 存储配置，`algorithms.json` 可选列出可用算法及其显示名。这满足“JSON 文件存储”的技术栈要求。
- **运行时数据**：数组、步骤序列仅存在于请求-响应生命周期中，不落盘。

## 6. 关键设计决策
- 后端无状态：简化并发和状态管理，可由前端完全控制动画进度。
- 步骤序列全量返回：冒泡排序步骤有限（最大 1225 步），全量传输安全，避免多次请求。
- 配置集中：颜色、范围等参数统一在 `config.json`，修改无需改动代码。