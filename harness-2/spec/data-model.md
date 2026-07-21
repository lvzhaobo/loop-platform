# 数据模型:`data/products.json` 为数组,每个元素结构如下

| 字段         | 类型    | 必填 | 说明                        |
|--------------|---------|------|-----------------------------|
| id           | int     | 是   | 唯一,从 1 递增              |
| title        | string  | 是   | 商品标题,≤ 40 字            |
| price        | float   | 是   | 现价(元)                  |
| origin_price | float   | 否   | 划线原价(元)              |
| sales        | int     | 是   | 月销量                      |
| image        | string  | 是   | 本地图路径 `static/img/x.png` |
| shop         | string  | 是   | 店铺名                      |
| desc         | string  | 是   | 详情描述,≥ 30 字            |
| tags         | array   | 否   | 促销标签                    |

## 数据量要求
- 至少 8 条商品,id 连续 1~8

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
