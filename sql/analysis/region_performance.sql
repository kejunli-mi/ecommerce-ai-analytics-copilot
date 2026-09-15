-- 地区增长与履约体验。增长使用2017/2018年1至8月同期，服务指标使用完整分析期。
WITH state_metrics AS (
    SELECT
        COALESCE(customer_state, 'unknown_state') AS customer_state,
        SUM(gmv) FILTER (
            WHERE order_purchase_timestamp >= TIMESTAMP '2017-01-01'
              AND order_purchase_timestamp < TIMESTAMP '2017-09-01'
        ) AS gmv_2017,
        SUM(gmv) FILTER (
            WHERE order_purchase_timestamp >= TIMESTAMP '2018-01-01'
              AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
        ) AS gmv_2018,
        COUNT(*) FILTER (
            WHERE order_purchase_timestamp >= TIMESTAMP '2017-01-01'
              AND order_purchase_timestamp < TIMESTAMP '2017-09-01'
        ) AS orders_2017,
        COUNT(*) FILTER (
            WHERE order_purchase_timestamp >= TIMESTAMP '2018-01-01'
              AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
        ) AS orders_2018,
        COUNT(*) FILTER (
            WHERE order_status = 'delivered'
              AND is_late_delivery IS NOT NULL
        ) AS delivered_orders,
        AVG(CAST(is_late_delivery AS INTEGER)) FILTER (
            WHERE order_status = 'delivered'
              AND is_late_delivery IS NOT NULL
        ) AS late_delivery_rate,
        AVG(delivery_days) FILTER (WHERE order_status = 'delivered') AS avg_delivery_days,
        COUNT(*) FILTER (WHERE review_score IS NOT NULL) AS reviewed_orders,
        AVG(review_score) FILTER (WHERE review_score IS NOT NULL) AS avg_review_score,
        AVG(CASE WHEN review_score <= 2 THEN 1.0 ELSE 0.0 END) FILTER (
            WHERE review_score IS NOT NULL
        ) AS low_review_rate
    FROM analytics.orders
    WHERE is_effective_order
      AND order_purchase_timestamp >= TIMESTAMP '2017-01-01'
      AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
    GROUP BY 1
),
totals AS (
    SELECT
        SUM(gmv_2017) AS total_gmv_2017,
        SUM(gmv_2018) AS total_gmv_2018,
        SUM(orders_2017) AS total_orders_2017,
        SUM(orders_2018) AS total_orders_2018
    FROM state_metrics
)
SELECT
    customer_state,
    ROUND(COALESCE(gmv_2017, 0), 2) AS gmv_2017,
    ROUND(COALESCE(gmv_2018, 0), 2) AS gmv_2018,
    ROUND(COALESCE(gmv_2018, 0) - COALESCE(gmv_2017, 0), 2) AS gmv_change,
    ROUND(COALESCE(gmv_2018, 0) / NULLIF(gmv_2017, 0) - 1, 4) AS gmv_growth_rate,
    ROUND(
        (COALESCE(gmv_2018, 0) - COALESCE(gmv_2017, 0))
        / NULLIF(total_gmv_2018 - total_gmv_2017, 0),
        6
    ) AS growth_contribution,
    ROUND(COALESCE(gmv_2017, 0) / NULLIF(total_gmv_2017, 0), 6) AS gmv_share_2017,
    ROUND(COALESCE(gmv_2018, 0) / NULLIF(total_gmv_2018, 0), 6) AS gmv_share_2018,
    orders_2017,
    orders_2018,
    ROUND(orders_2018 * 1.0 / NULLIF(orders_2017, 0) - 1, 4) AS order_growth_rate,
    delivered_orders,
    ROUND(late_delivery_rate, 4) AS late_delivery_rate,
    ROUND(avg_delivery_days, 2) AS avg_delivery_days,
    reviewed_orders,
    ROUND(avg_review_score, 3) AS avg_review_score,
    ROUND(low_review_rate, 4) AS low_review_rate,
    ROUND(total_gmv_2017, 2) AS total_gmv_2017,
    ROUND(total_gmv_2018, 2) AS total_gmv_2018,
    total_orders_2017,
    total_orders_2018
FROM state_metrics
CROSS JOIN totals
ORDER BY gmv_change DESC, customer_state;
