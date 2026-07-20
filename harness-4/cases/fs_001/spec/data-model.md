- 实体(entity): `course`
- min_items: 8

| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| id | int | 是 | sequential_from=1 | 课程唯一标识 |
| title | string | 是 | max_len=200 | 课程标题 |
| description | string | 是 | min_len=100 | 课程详细描述 |
| cover_image | string | 否 | | 课程封面图片URL |
| instructor | string | 是 | max_len=100 | 授课教师 |
| duration | number | 是 | gt=0 | 课程时长(小时) |
| category | string | 是 | max_len=50 | 课程分类 |
| price | number | 否 | gte=0 | 课程价格 |
