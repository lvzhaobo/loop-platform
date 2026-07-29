# API 契约 – 排序算法可视化后端服务 (FS-002)

> 本契约定义支撑排序动画演示所需的最小 REST API。  
> 前端为单个 HTML 文件，通过 `fetch` 调用本服务接口获取数据和控制状态。  
> 所有端点基础路径：`/api`

---

## 1. 通用约定

- 内容类型：`application/json; charset=utf-8`
- 编码：UTF‑8
- 错误响应格式：
  ```json
  {
    "error": {
      "code": "INVALID_INPUT",
      "message": "可读的错误描述"
    }
  }
  ```
- HTTP 状态码：
  - `200 OK` – 成功
  - `400 Bad Request` – 请求参数错误
  - `404 Not Found` – 端点不存在
  - `500 Internal Server Error` – 服务器内部异常

---

## 2. 端点定义

### 2.1 获取随机数组 → `GET /api/array`

**用途**：为前端提供初始化的随机整数数组，用于生成条形图。  
**查询参数**：

| 参数名 | 类型   | 必填 | 说明                         | 示例  |
| ------ | ------ | ---- | ---------------------------- | ----- |
| `size` | 整数   | 否   | 数组长度，默认 20，范围 5‑50 | `?size=25` |

**响应 (200)**：

```json
{
  "values": [12, 7, 33, 18, 5, 29, …]
}
```

**错误示例**：`?size=abc` → 400  
```json
{
  "error": {
    "code": "INVALID_SIZE",
    "message": "size must be an integer between 5 and 50"
  }
}
```

**与故事/AC 关联**：  
- US‑001, AC‑001 – 返回 `values` 字段，长度符合请求。
- US‑004, AC‑007 – `reset` 命令触发本端点的隐式调用，返回新 `values`。

---

### 2.2 启动排序并获取步骤序列 → `POST /api/sort`

**用途**：根据指定算法和待排序数组，返回完整的排序步骤列表，前端依序播放动画。  
**请求体 (JSON)**：

```json
{
  "algorithm": "bubble",
  "array": [5, 3, 8, 1, 9, 2]
}
```

**约束**：  
- `algorithm` 目前仅支持 `"bubble"`（后续可扩展）。  
- `array` 为整数数组，长度 ≥ 2，最大值 ≤ 100。

**响应 (200)**：

```json
{
  "steps": [
    {
      "type": "compare",
      "indices": [0, 1],
      "colors": {
        "compare": "#e74c3c",
        "swap": "#f39c12",
        "sorted": "#2ecc71"
      }
    },
    {
      "type": "swap",
      "indices": [1, 0],
      "colors": { … }
    },
    …
    {
      "type": "complete",
      "indices": [],
      "colors": { … }
    }
  ]
}
```

**步骤类型说明**：
- `compare` – 比较两个索引对应的条形，前端应将这些条形变为 `compare` 颜色（红）。
- `swap` – 交换两个索引并更新位置，交换过程中两条形变为 `swap` 颜色（橙），随后恢复。
- `complete` – 整个排序结束，所有已排序索引条形变为 `sorted` 颜色（绿）。

**错误示例**：
- 未知算法 → 400  
  ```json
  { "error": { "code": "UNSUPPORTED_ALGORITHM", "message": "Only 'bubble' algorithm is supported" } }
  ```
- 数组参数缺失 → 400  
  ```json
  { "error": { "code": "MISSING_ARRAY", "message": "Request body must contain 'array'" } }
  ```

**与故事/AC 关联**：  
- US‑002, AC‑003 – 响应含有 `steps` 数组，步素含 `type`, `indices`, `colors`。  
- US‑002, AC‑004 – 前端依据步骤序列完成颜色切换与位置动画。

---

### 2.3 控制排序状态 → `POST /api/sort/control`

**用途**：从前端发送暂停、继续、重置命令，管理动画播放状态。  
**请求体 (JSON)**：

```json
{
  "command": "pause" | "resume" | "reset",
  "options": {
    "resetSize": 20
  }
}
```

**说明**：
- `pause` – 暂停当前动画，服务端返回暂停状态，前端停止步骤消费。  
- `resume` – 继续播放，服务端返回运行状态。  
- `reset` – 终止当前动画，服务器重新生成随机数组（可指定大小 `resetSize`），返回新数组并清除步骤缓存。  
- `options` 字段仅在 `reset` 时使用，`resetSize` 默认 20。

**响应 (200)**：

- 对 `pause` / `resume`：
  ```json
  {
    "status": "paused"  // 或 "running"
  }
  ```
- 对 `reset`：
  ```json
  {
    "status": "reset",
    "values": [8, 23, 5, …]  // 新随机数组
  }
  ```

**错误示例**：
- 无效命令 → 400  
  ```json
  { "error": { "code": "INVALID_COMMAND", "message": "Supported commands: pause, resume, reset" } }
  ```
- 非法 `resetSize` → 400  
  ```json
  { "error": { "code": "INVALID_SIZE", "message": "resetSize must be between 5 and 50" } }
  ```

**与故事/AC 关联**：  
- US‑003, AC‑005 – `pause` 命令返回 `status: "paused"`。  
- US‑003, AC‑006 – `resume` 命令返回 `status: "running"`。  
- US‑004, AC‑007 – `reset` 命令返回 `status: "reset"` 及新 `values`。

---

### 2.4 获取应用元数据 → `GET /api/meta`

**用途**：提供全局标识等元信息，确保前端展示“Loop‑20260723”。  
**响应 (200)**：

```json
{
  "identifier": "Loop-20260723",
  "version": "1.0",
  "theme": {
    "background": "#f5f5f5",
    "defaultBar": "#3498db"
  }
}
```

**错误情况**：极少发生，若失败返回 500。  
**与故事/AC 关联**：  
- US‑005, AC‑008 – 响应包含 `identifier` 字段，值为 `"Loop-20260723"`。

---

## 3. 错误码汇总

| 错误码                | HTTP 状态 | 触发条件                         |
| --------------------- | --------- | -------------------------------- |
| `INVALID_SIZE`        | 400       | `size` 或 `resetSize` 不合法     |
| `UNSUPPORTED_ALGORITHM` | 400     | `algorithm` 未实现               |
| `MISSING_ARRAY`       | 400       | `/sort` 请求体缺少 `array`       |
| `INVALID_COMMAND`     | 400       | `/sort/control` 命令无效         |
| `INTERNAL_ERROR`      | 500       | 服务器内部异常                   |

---

## 4. 前端契约关联要点

- 前端在 `DOMContentLoaded` 时先调用 `GET /api/meta` 获取 `identifier`，渲染指定文字。  
- 同时调用 `GET /api/array?size=20` 获取初始数组并绘制条形图。  
- “开始排序”按钮 → `POST /api/sort`，获取 `steps`，通过定时器逐帧消费，依据 `type` 和 `indices` 控制颜色与位置。  
- “暂停”/“继续”按钮 → `POST /api/sort/control` 相应命令，控制动画定时器的启停。  
- “重置”按钮 → `POST /api/sort/control { "command": "reset" }` 获取新 `values`，清空步骤指针，重新绘制。  
- 所有 AC 中提及的字段名（`values`, `steps`, `type`, `indices`, `colors`, `status`, `identifier`）均已在本契约中定义，前后端一致。