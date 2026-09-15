-- 用户分层截止日固定为2018-09-01，确保结果可复现。
WITH customer_metrics AS (
    SELECT
        customer_unique_id,
        COUNT(*) AS order_count,
        SUM(gmv) AS gmv,
        date_diff('day', MAX(CAST(order_purchase_timestamp AS DATE)), DATE '2018-09-01')
            AS recency_days
    FROM analytics.orders
    WHERE is_effective_order
      AND customer_unique_id IS NOT NULL
      AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
    GROUP BY 1
),
segmented AS (
    SELECT
        *,
        CASE
            WHEN order_count >= 2 AND recency_days <= 90 THEN 'active_repeat'
            WHEN order_count >= 2 THEN 'at_risk_repeat'
            WHEN recency_days <= 90 THEN 'recent_one_time'
            ELSE 'dormant_one_time'
        END AS customer_segment
    FROM customer_metrics
),
totals AS (
    SELECT COUNT(*) AS total_users, SUM(gmv) AS total_gmv FROM segmented
)
SELECT
    customer_segment,
    COUNT(*) AS users,
    ROUND(COUNT(*) * 1.0 / total_users, 6) AS user_share,
    ROUND(SUM(gmv), 2) AS gmv,
    ROUND(SUM(gmv) / total_gmv, 6) AS gmv_share,
    ROUND(AVG(order_count), 3) AS avg_orders,
    ROUND(AVG(gmv), 2) AS avg_customer_gmv,
    ROUND(AVG(recency_days), 1) AS avg_recency_days,
    total_users,
    ROUND(total_gmv, 2) AS total_gmv
FROM segmented
CROSS JOIN totals
GROUP BY customer_segment, total_users, total_gmv
ORDER BY gmv DESC;
