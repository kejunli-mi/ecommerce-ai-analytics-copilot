-- 完整月份：2017-01至2018-08。GMV不含运费，只统计有效订单。
WITH monthly AS (
    SELECT
        CAST(date_trunc('month', order_purchase_timestamp) AS DATE) AS purchase_month,
        SUM(gmv) AS gmv,
        COUNT(DISTINCT order_id) AS order_count,
        COUNT(DISTINCT customer_unique_id) AS customer_count,
        SUM(item_count) AS item_count
    FROM analytics.orders
    WHERE is_effective_order
      AND order_purchase_timestamp >= TIMESTAMP '2017-01-01'
      AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
    GROUP BY 1
),
with_comparisons AS (
    SELECT
        *,
        LAG(gmv) OVER (ORDER BY purchase_month) AS previous_month_gmv,
        LAG(order_count) OVER (ORDER BY purchase_month) AS previous_month_orders,
        LAG(gmv, 12) OVER (ORDER BY purchase_month) AS previous_year_gmv,
        LAG(order_count, 12) OVER (ORDER BY purchase_month) AS previous_year_orders
    FROM monthly
)
SELECT
    purchase_month,
    ROUND(gmv, 2) AS gmv,
    order_count,
    customer_count,
    item_count,
    ROUND(gmv / NULLIF(order_count, 0), 2) AS average_order_value,
    ROUND(gmv / NULLIF(previous_month_gmv, 0) - 1, 4) AS gmv_mom_growth,
    ROUND(order_count * 1.0 / NULLIF(previous_month_orders, 0) - 1, 4)
        AS order_mom_growth,
    ROUND(gmv / NULLIF(previous_year_gmv, 0) - 1, 4) AS gmv_yoy_growth,
    ROUND(order_count * 1.0 / NULLIF(previous_year_orders, 0) - 1, 4)
        AS order_yoy_growth,
    ROUND(
        (gmv / NULLIF(order_count, 0))
        / NULLIF(previous_year_gmv / NULLIF(previous_year_orders, 0), 0) - 1,
        4
    ) AS aov_yoy_growth
FROM with_comparisons
ORDER BY purchase_month;
