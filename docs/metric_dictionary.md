# 核心指标字典 v0.1

所有正式分析和 Copilot 回答都应引用这里的统一口径。

| 指标 | 定义 | 计算口径 | 主要时间字段 |
|---|---|---|---|
| GMV | 有效订单中的商品成交金额 | `SUM(order_items.price)`；不含运费 | `order_purchase_timestamp` |
| 有效订单量 | 已购买且未取消、未标记不可用的去重订单数 | `COUNT(DISTINCT order_id)` | `order_purchase_timestamp` |
| 销售件数 | 有效订单中的订单明细行数 | `COUNT(*)`；数据缺少商品件数列，单行视为一件 | `order_purchase_timestamp` |
| 客单价 | 每个有效订单的平均商品成交金额 | `GMV / 有效订单量` | `order_purchase_timestamp` |
| 件单价 | 每个订单明细的平均商品价格 | `GMV / 销售件数` | `order_purchase_timestamp` |
| 取消率 | 取消订单占全部已创建订单的比例 | `canceled订单数 / 全部订单数` | `order_purchase_timestamp` |
| 复购率 | 完成至少两笔有效订单的用户占完成至少一笔有效订单用户的比例 | 按 `customer_unique_id` 聚合 | `order_purchase_timestamp` |
| 平均配送时长 | 用户下单至实际送达的平均天数 | `delivered_customer_date - purchase_timestamp` | 实际送达时间 |
| 延迟配送率 | 实际送达晚于预计送达日期的已送达订单比例 | `actual_date > estimated_date` | 实际送达时间 |
| 平均评价分 | 有评价订单最终评价的平均星级 | 同一订单多条评价时取最后提交的一条 | `review_answer_timestamp` |
| 低评分率 | 1至2星评价订单占有评价订单的比例 | `review_score <= 2` | `review_creation_date` |
| 商家集中度 | 头部商家 GMV 占总 GMV 的比例 | 可分别计算 Top 10、Top 20 和 HHI | `order_purchase_timestamp` |
| 增长贡献 | 分类或地区对全站GMV净增量的贡献 | `维度GMV增量 / 全站GMV净增量` | `order_purchase_timestamp` |
| 队列留存 | 首购后指定月再次购买的用户比例 | `后续购买用户 / 首购队列用户` | `order_purchase_timestamp` |
| Copilot答案准确率 | 自然语言问题的预测查询与基准查询结果一致的比例 | 比较执行后的列、行和数值，不比较SQL文本 | 固定评测集 |

## 有效订单定义

第一版将满足以下条件的订单视为有效订单：

```sql
order_purchase_timestamp IS NOT NULL
AND order_status NOT IN ('canceled', 'unavailable')
```

该定义用于经营趋势和用户复购。履约专题会进一步限定 `order_status = 'delivered'`。

## 待验证事项

- 比较 `payment_value` 与商品价格加运费之间的差异，确认支付口径。
- 跟踪同一订单多次付款和多条评价的分布，确认聚合规则持续适用。
- 检查取消订单是否存在商品明细或支付记录。
- 确认极端高价、极长配送时间是否为合理业务值。
