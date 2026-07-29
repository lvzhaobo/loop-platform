# 数据模型:`data/posts.json` 为数组,每个元素结构如下

> 本文件是「数据模型」的**唯一事实源**;case.json 的数据字段由 tools/compile_spec.py 从下表派生,勿手改。

- 实体(entity):`post`

| 字段     | 类型   | 必填 | 约束              | 说明                  |
|----------|--------|------|-------------------|-----------------------|
| id       | int    | 是   | sequential_from=1 | 唯一,从 1 递增        |
| title    | string | 是   | max_len=60        | 文章标题              |
| author   | string | 是   |                   | 作者名                |
| date     | string | 是   |                   | 发布日期 `YYYY-MM-DD` |
| summary  | string | 是   | max_len=120       | 摘要                  |
| content  | string | 是   | min_len=200       | 正文(可含段落)      |
| tags     | array  | 否   |                   | 分类标签              |

## 数据量要求
- min_items:6(id 连续 1~6)

## 示例
```json
{
  "id": 1,
  "title": "从零理解 Harness Engineering",
  "author": "老王",
  "date": "2026-07-19",
  "summary": "用确定性脚手架约束非确定性的大模型输出,核心是验证闭环。",
  "content": "很多人以为让 AI 写代码就是把需求丢给模型……(此处应有 200 字以上正文,分多段展开论述)",
  "tags": ["工程", "AI"]
}
```
