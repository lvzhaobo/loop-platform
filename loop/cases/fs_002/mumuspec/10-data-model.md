# 数据模型 – FS-002

以下模型定义 API 请求与响应的数据结构，字段名严格对齐 API 契约 (09‑api‑spec.md)。

## 1. 获取随机数组

### 请求参数 (Query String)
| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| `size` | integer | 否 | 5 ≤ size ≤ 50；默认 20 | 数组长度。若非整数或超限 → 400 `INVALID_SIZE` |

### 响应体 `GET /api/array`
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `values` | array of integer | 长度 = 请求的 size；元素范围 1～100 | 随机排列的整数数组 |

示例：
```json
{
  "values": [12, 7, 33, …]
}
```

## 2. 启动排序

### 请求体 `POST /api/sort`
| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| `algorithm` | string | 是 | 仅允许 `"bubble"` | 排序算法标识 |
| `array` | array of integer | 是 | 长度 ≥ 2，最大值 ≤ 50；元素范围 1～100 | 待排序数组 |

约束违反 → 相应错误码 `UNSUPPORTED_ALGORITHM` 或 `MISSING_ARRAY`。

### 响应体
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `steps` | array of step object | 非空数组 | 完整排序步骤序列 |

**step object 结构**：
| 子字段 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `type` | string | 枚举：`"compare"`, `"swap"`, `"complete"` | 步骤类型 |
| `indices` | array of integer | 数组长度依类型变化：compare/swap 时为 2，complete 时可为空 | 涉及的条形索引 |
| `colors` | object | 固定包含 `compare`, `swap`, `sorted` 三个 color 字段 | 颜色映射，值为 hex 字符串 |

示例：
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
    ...
  ]
}
```

## 3. 控制命令

### 请求体 `POST /api/sort/control`
| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| `command` | string | 是 | 枚举：`"pause"`, `"resume"`, `"reset"` | 操作指令 |
| `options` | object | 否 | 仅 `command` 为 `"reset"` 时可含 `resetSize` | 附加选项 |
| `options.resetSize` | integer | 否 | 5～50，默认 20 | 重置时生成数组长度 |

无效指令 → 400 `INVALID_COMMAND`；非法 resetSize → `INVALID_SIZE`。

### 响应体
- **pause / resume**：
  ```json
  {
    "status": "paused"  // 或 "running"
  }
  ```
- **reset**：
  ```json
  {
    "status": "reset",
    "values": [8, 23, …]
  }
  ```

## 4. 元数据

### 响应体 `GET /api/meta`
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `identifier` | string | 固定值 `"Loop-20260723"` | 页面展示的标识 |
| `version` | string | 固定 `"1.0"` | API 版本 |
| `theme` | object | 包含 `background`, `defaultBar` 字段 | 供前端使用的主题色 |

示例：
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

## 5. 错误响应
| 字段 | 类型 | 说明 |
|------|------|------|
| `error.code` | string | 错误码（如 `INVALID_SIZE`） |
| `error.message` | string | 面向用户的可读描述 |

所有 API 在非正常状态时返回此结构。