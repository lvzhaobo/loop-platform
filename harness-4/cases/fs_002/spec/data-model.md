- 实体(entity): `tomato`
- min_items: 8
| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| id | int | 是 | sequential_from=1 | 唯一标识 |
| name | string | 是 | max_len=100 | 番茄时钟名称 |
| duration | int | 是 | gt=0 lte=60 | 专注时长(分钟) |
| break_duration | int | 是 | gt=0 lte=30 | 休息时长(分钟) |
| color | string | 是 | max_len=7 | 番茄颜色(十六进制) |
| image | string | 否 | max_len=500 | 封面图片URL |
| description | string | 否 | min_len=10 max_len=2000 | 详情正文 |
| created_at | string | 是 | max_len=20 | 创建时间 |
| loop_count | int | 否 | gte=0 | 循环次数 |
| status | string | 是 | max_len=20 | 状态(active/paused/completed) |
