# 数据模型:`data/recipes.json` 为数组,每个元素结构如下

> 本文件是「数据模型」的唯一事实源;case.json 的数据字段由 compile_spec 从下表派生。

- 实体(entity):`recipe`
- min_items:6

| 字段    | 类型   | 必填 | 约束              | 说明               |
|---------|--------|------|-------------------|--------------------|
| id      | int    | 是   | sequential_from=1 | 唯一,从 1 递增     |
| title   | string | 是   | max_len=40        | 菜名               |
| chef    | string | 是   |                   | 主厨               |
| cuisine | string | 是   |                   | 菜系:川/粤/日...   |
| minutes | int    | 是   | gt=0              | 烹饪时长(分钟)   |
| cover   | string | 是   |                   | 封面图 `static/img/<id>.png` |
| summary | string | 是   | max_len=100       | 一句话简介         |
| steps   | string | 是   | min_len=100       | 详细做法正文       |
