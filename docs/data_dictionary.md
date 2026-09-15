# Olist 数据字典

## 表关系

```text
customers 1 ── N orders 1 ── N order_items N ── 1 products
                     │              └──────── N ── 1 sellers
                     ├── 1 ── N order_payments
                     └── 1 ── N order_reviews
```

## 文件与分析用途

| 分析表 | CSV文件 | 主键/粒度 | 用途 |
|---|---|---|---|
| `customers` | `olist_customers_dataset.csv` | `customer_id` | 订单客户、跨订单用户和地区 |
| `orders` | `olist_orders_dataset.csv` | `order_id` | 订单状态和完整时间链路 |
| `order_items` | `olist_order_items_dataset.csv` | `order_id + order_item_id` | 商品成交金额、运费、商家 |
| `order_payments` | `olist_order_payments_dataset.csv` | 订单内付款序号 | 支付方式、分期和支付金额 |
| `order_reviews` | `olist_order_reviews_dataset.csv` | `review_id + order_id` | 评分和评价文本 |
| `products` | `olist_products_dataset.csv` | `product_id` | 品类和商品物理属性 |
| `sellers` | `olist_sellers_dataset.csv` | `seller_id` | 商家地区 |
| `geolocation` | `olist_geolocation_dataset.csv` | 非唯一邮编坐标记录 | 地理可视化，可选 |
| `category_translation` | `product_category_name_translation.csv` | 葡语品类名 | 品类英文翻译，可选 |

## 关键建模注意事项

- `customer_id` 通常对应一笔订单；用户分析必须使用 `customer_unique_id`。
- `orders`、`order_items`、`payments`、`reviews` 粒度不同，直接全部连接会造成金额膨胀。
- 支付与评价需要先聚合到订单粒度，再连接订单主表。
- `review_id` 单列并不唯一；同一订单多条评价时保留最后提交的一条，并记录评价条数。
- 商品价格 `price` 与运费 `freight_value` 分开计算，GMV 默认不包含运费。
- 产品品类原字段为葡萄牙语；没有翻译时应保留原始值，不能丢弃订单。
