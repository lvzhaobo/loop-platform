- 实体(entity):`tomato_clock`
- min_items:8
| 字段 | 类型 | 必填 | 约束 | 说明 |
| id | int | 是 | sequential_from=1 | 唯一标识 |
| title | string | 是 | max_len=100 | 番茄时钟标题 |
| cover_image | string | 否 | max_len=500 | 封面图片URL |
| duration_minutes | int | 是 | gt=0 lte=60 | 番茄时钟时长(分钟) |
| description | string | 是 | min_len=10 max_len=2000 | 番茄时钟详情描述 |
| color_hex | string | 是 | max_len=7 | 番茄颜色十六进制码 |
| created_at | string | 是 | max_len=20 | 创建时间 |
| is_active | int | 是 | gte=0 lte=1 | 是否激活(0/1) |
