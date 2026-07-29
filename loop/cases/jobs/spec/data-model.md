- 实体(entity):`job`
- min_items:8
| 字段 | 类型 | 必填 | 约束 | 说明 |
| id | int | 是 | sequential_from=1 | 职位唯一标识 |
| title | string | 是 | max_len=100 | 职位名称 |
| company | string | 是 | max_len=100 | 公司名称 |
| salary | string | 是 | max_len=50 | 薪资范围 |
| city | string | 是 | max_len=50 | 工作城市 |
| cover | string | 否 | | 职位封面图片URL |
| responsibilities | string | 是 | min_len=100 | 岗位职责详情 |
| requirements | string | 是 | min_len=100 | 任职要求详情 |
