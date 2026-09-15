-- 商家规模、集中度与履约表现，分析期为2017-01至2018-08。
WITH seller_sales AS (
    SELECT
        seller_id,
        COALESCE(seller_state, 'unknown_state') AS seller_state,
        SUM(price) AS gmv,
        COUNT(*) AS units,
        COUNT(DISTINCT order_id) AS order_count,
        COUNT(DISTINCT date_trunc('month', order_purchase_timestamp)) AS active_months
    FROM analytics.order_items
    WHERE is_effective_order
      AND order_purchase_timestamp >= TIMESTAMP '2017-01-01'
      AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
    GROUP BY 1, 2
),
seller_orders AS (
    SELECT DISTINCT seller_id, order_id
    FROM analytics.order_items
    WHERE is_effective_order
      AND order_purchase_timestamp >= TIMESTAMP '2017-01-01'
      AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
),
seller_service AS (
    SELECT
        so.seller_id,
        COUNT(*) FILTER (
            WHERE o.order_status = 'delivered'
              AND o.is_late_delivery IS NOT NULL
        ) AS delivered_orders,
        AVG(CAST(o.is_late_delivery AS INTEGER)) FILTER (
            WHERE o.order_status = 'delivered'
              AND o.is_late_delivery IS NOT NULL
        ) AS late_delivery_rate,
        AVG(o.delivery_days) FILTER (WHERE o.order_status = 'delivered') AS avg_delivery_days,
        AVG(o.review_score) FILTER (WHERE o.review_score IS NOT NULL) AS avg_review_score,
        AVG(CASE WHEN o.review_score <= 2 THEN 1.0 ELSE 0.0 END) FILTER (
            WHERE o.review_score IS NOT NULL
        ) AS low_review_rate
    FROM seller_orders AS so
    JOIN analytics.orders AS o USING (order_id)
    GROUP BY 1
),
combined AS (
    SELECT ss.*, sv.* EXCLUDE (seller_id)
    FROM seller_sales AS ss
    LEFT JOIN seller_service AS sv USING (seller_id)
),
ranked AS (
    SELECT
        *,
        SUM(gmv) OVER () AS total_gmv,
        ROW_NUMBER() OVER (ORDER BY gmv DESC, seller_id) AS gmv_rank
    FROM combined
)
SELECT
    seller_id,
    seller_state,
    ROUND(gmv, 2) AS gmv,
    units,
    order_count,
    active_months,
    ROUND(gmv / NULLIF(total_gmv, 0), 6) AS gmv_share,
    gmv_rank,
    ROUND(
        SUM(gmv) OVER (ORDER BY gmv DESC, seller_id ROWS UNBOUNDED PRECEDING)
        / NULLIF(total_gmv, 0),
        6
    ) AS cumulative_gmv_share,
    delivered_orders,
    ROUND(late_delivery_rate, 4) AS late_delivery_rate,
    ROUND(avg_delivery_days, 2) AS avg_delivery_days,
    ROUND(avg_review_score, 3) AS avg_review_score,
    ROUND(low_review_rate, 4) AS low_review_rate,
    ROUND(gmv / NULLIF(order_count, 0), 2) AS seller_order_value,
    ROUND(total_gmv, 2) AS total_gmv
FROM ranked
ORDER BY gmv_rank;
