- 实体(entity): `tomato`
- min_items: 8
| 字段 | 类型 | 必填 | 约束 | 说明 |
| id | int | 是 | sequential_from=1 | 唯一标识 |
| name | string | 是 | max_len=100 | 番茄时钟名称 |
| duration | int | 是 | gt=0 | 工作时长(分钟) |
| break_duration | int | 是 | gt=0 | 休息时长(分钟) |
| color | string | 是 | max_len=7 | 番茄颜色(十六进制) |
| image | string | 否 | | 封面图片URL |
| description | string | 是 | min_len=10 | 番茄时钟详情描述 |
| created_at | string | 是 | | 创建时间 |
| status | string | 是 | max_len=20 | 状态(active/inactive) |
