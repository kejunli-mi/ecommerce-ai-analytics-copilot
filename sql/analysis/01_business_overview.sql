-- 1. 月度经营趋势：GMV、订单量、客单价
SELECT
    date_trunc('month', order_purchase_timestamp) AS month,
    SUM(gmv) AS gmv,
    COUNT(DISTINCT order_id) AS orders,
    SUM(gmv) / NULLIF(COUNT(DISTINCT order_id), 0) AS average_order_value
FROM analytics.orders
WHERE is_effective_order
  -- 2016年仅有零散订单，2018年9月之后数据不完整，趋势分析使用完整月份。
  AND order_purchase_timestamp >= TIMESTAMP '2017-01-01'
  AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
GROUP BY 1
ORDER BY 1;

-- 2. 整体履约与评价表现
SELECT
    AVG(delivery_days) FILTER (WHERE order_status = 'delivered') AS avg_delivery_days,
    AVG(CAST(is_late_delivery AS INTEGER)) FILTER (
        WHERE order_status = 'delivered'
          AND order_estimated_delivery_date IS NOT NULL
    ) AS late_delivery_rate,
    AVG(review_score) AS avg_review_score,
    AVG(CASE WHEN review_score <= 2 THEN 1.0 ELSE 0.0 END) FILTER (
        WHERE review_score IS NOT NULL
    ) AS low_review_rate
FROM analytics.orders;

-- 3. 品类销售贡献
SELECT
    product_category,
    SUM(price) AS gmv,
    COUNT(*) AS units,
    COUNT(DISTINCT order_id) AS orders
FROM analytics.order_items
WHERE is_effective_order
  AND order_purchase_timestamp >= TIMESTAMP '2017-01-01'
  AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
GROUP BY 1
ORDER BY gmv DESC;
