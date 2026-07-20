# 数据模型:`data/products.json` 为数组,每个元素结构如下

> 本文件是「数据模型」的**唯一事实源**。`case.json` 的数据字段
> (entity / min_items / required_fields / numeric_fields / field_rules)
> 由 `tools/compile_spec.py` 从下表**派生**,请勿手改 case.json 的这些字段。

- 实体(entity):`product`

| 字段         | 类型   | 必填 | 约束              | 说明                          |
|--------------|--------|------|-------------------|-------------------------------|
| id           | int    | 是   | sequential_from=1 | 唯一,从 1 递增                |
| title        | string | 是   | max_len=40        | 商品标题                      |
| price        | number | 是   | gt=0              | 现价(元)                    |
| origin_price | float  | 否   |                   | 划线原价(元)                |
| sales        | int    | 是   | gte=0             | 月销量                        |
| image        | string | 是   |                   | 本地图路径 `static/img/x.png` |
| shop         | string | 是   |                   | 店铺名                        |
| desc         | string | 是   | min_len=30        | 详情描述                      |
| tags         | array  | 否   |                   | 促销标签                      |

> 约束列语法:`key=value`,多个用空格分隔。可用键:
> `sequential_from` `max_len` `min_len` `gt` `gte` `lt` `lte`。

## 数据量要求
- min_items:8(id 连续 1~8)

## 示例
```json
{
  "id": 1,
  "title": "2024新款纯棉短袖T恤男夏季",
  "price": 59.90,
  "origin_price": 129.00,
  "sales": 3821,
  "image": "static/img/1.png",
  "shop": "优衣佳旗舰店",
  "desc": "100%新疆长绒棉,亲肤透气,不易变形,夏季必备百搭款。",
  "tags": ["包邮", "7天无理由"]
}
```
