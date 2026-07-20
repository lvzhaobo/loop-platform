# 数据模型:`data/courses.json` 为数组,每个元素结构如下

> 本文件是「数据模型」的**唯一事实源**;case.json 的数据字段由 tools/compile_spec.py 从下表派生,勿手改。

- 实体(entity):`course`

| 字段     | 类型   | 必填 | 约束              | 说明                          |
|----------|--------|------|-------------------|-------------------------------|
| id       | int    | 是   | sequential_from=1 | 唯一,从 1 递增                |
| title    | string | 是   | max_len=50        | 课程标题                      |
| teacher  | string | 是   |                   | 授课讲师名                    |
| level    | string | 是   |                   | 难度:入门 / 进阶 / 高级       |
| duration | int    | 是   | gt=0              | 课程总时长(分钟)            |
| cover    | string | 是   |                   | 封面图路径 `static/img/<id>.png` |
| summary  | string | 是   | max_len=120       | 一句话简介                    |
| content  | string | 是   | min_len=200       | 课程详情正文                  |

## 数据量要求
- min_items:6(id 连续 1~6)

## 示例
```json
{
  "id": 1,
  "title": "Flask 从入门到实战",
  "teacher": "李老师",
  "level": "入门",
  "duration": 480,
  "cover": "static/img/1.png",
  "summary": "用一个真实项目带你掌握 Flask 路由、模板与数据驱动页面。",
  "content": "本课程从零搭建一个完整的 Flask 应用……(此处应有 200 字以上正文,分多章节展开讲解)",
  "tags": ["Python", "Web"]
}
```
