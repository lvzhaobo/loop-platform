# 追溯矩阵 – 排序算法可视化网页 (FS-002)

## 映射说明
- **REQ**：采用验收条件编号（AC‑001 至 AC‑008），代表最低可验证需求。
- **US**：对应的用户故事编号（US‑001 至 US‑005）。
- **API**：涉及的 API 端点（方法 + 路径）。
- **TC**：测试策略中定义的测试用例 ID。

## 映射表

| REQ      | US      | API 端点                                      | TC ID   |
|----------|---------|-----------------------------------------------|---------|
| AC‑001   | US‑001  | GET /api/array                                | TC‑001  |
| AC‑002   | US‑001  | GET /api/array (前端渲染)                     | TC‑002  |
| AC‑003   | US‑002  | POST /api/sort                                | TC‑003  |
| AC‑004   | US‑002  | POST /api/sort (前端动画)                     | TC‑004  |
| AC‑005   | US‑003  | POST /api/sort/control (command: pause)       | TC‑005  |
| AC‑006   | US‑003  | POST /api/sort/control (command: resume)      | TC‑006  |
| AC‑007   | US‑004  | POST /api/sort/control (command: reset)       | TC‑007  |
| AC‑008   | US‑005  | GET /api/meta                                 | TC‑008  |

## 附加说明
- 每个 AC 至少对应一个 TC，覆盖了 API 响应和必要的前端行为。
- 对于既涉及 API 又涉及前端视觉的 AC（如 AC‑002、AC‑004、AC‑005/006/007 的前端部分），在 TC 中已注明判定方式（自动/人工），确保可追溯。
- 所有 API 端点均被 AC 覆盖，无遗漏。