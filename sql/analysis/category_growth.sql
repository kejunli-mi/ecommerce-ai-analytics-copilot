-- 同期品类增长贡献：2017年与2018年1至8月。
-- GMV为有效订单商品金额，不含运费；未匹配品类保留为 unknown_category。
WITH base AS (
    SELECT
        CASE
            WHEN order_purchase_timestamp < TIMESTAMP '2018-01-01' THEN 2017
            ELSE 2018
        END AS period_year,
        COALESCE(product_category, 'unknown_category') AS product_category,
        order_id,
        price
    FROM analytics.order_items
    WHERE is_effective_order
      AND (
          order_purchase_timestamp >= TIMESTAMP '2017-01-01'
          AND order_purchase_timestamp < TIMESTAMP '2017-09-01'
          OR order_purchase_timestamp >= TIMESTAMP '2018-01-01'
          AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
      )
),
category_metrics AS (
    SELECT
        product_category,
        SUM(price) FILTER (WHERE period_year = 2017) AS gmv_2017,
        SUM(price) FILTER (WHERE period_year = 2018) AS gmv_2018,
        COUNT(*) FILTER (WHERE period_year = 2017) AS units_2017,
        COUNT(*) FILTER (WHERE period_year = 2018) AS units_2018,
        COUNT(DISTINCT order_id) FILTER (WHERE period_year = 2017) AS category_orders_2017,
        COUNT(DISTINCT order_id) FILTER (WHERE period_year = 2018) AS category_orders_2018
    FROM base
    GROUP BY 1
),
item_totals AS (
    SELECT
        SUM(price) FILTER (WHERE period_year = 2017) AS total_gmv_2017,
        SUM(price) FILTER (WHERE period_year = 2018) AS total_gmv_2018,
        COUNT(*) FILTER (WHERE period_year = 2017) AS total_units_2017,
        COUNT(*) FILTER (WHERE period_year = 2018) AS total_units_2018
    FROM base
),
order_totals AS (
    SELECT
        COUNT(*) FILTER (
            WHERE order_purchase_timestamp >= TIMESTAMP '2017-01-01'
              AND order_purchase_timestamp < TIMESTAMP '2017-09-01'
        ) AS total_orders_2017,
        COUNT(*) FILTER (
            WHERE order_purchase_timestamp >= TIMESTAMP '2018-01-01'
              AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
        ) AS total_orders_2018
    FROM analytics.orders
    WHERE is_effective_order
      AND order_purchase_timestamp >= TIMESTAMP '2017-01-01'
      AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
)
SELECT
    product_category,
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
    ROUND(
        COALESCE(gmv_2018, 0) / NULLIF(total_gmv_2018, 0)
        - COALESCE(gmv_2017, 0) / NULLIF(total_gmv_2017, 0),
        6
    ) AS gmv_share_change,
    units_2017,
    units_2018,
    ROUND(units_2018 * 1.0 / NULLIF(units_2017, 0) - 1, 4) AS unit_growth_rate,
    category_orders_2017,
    category_orders_2018,
    ROUND(category_orders_2017 * 1.0 / NULLIF(total_orders_2017, 0), 6)
        AS order_penetration_2017,
    ROUND(category_orders_2018 * 1.0 / NULLIF(total_orders_2018, 0), 6)
        AS order_penetration_2018,
    ROUND(COALESCE(gmv_2017, 0) / NULLIF(units_2017, 0), 2) AS avg_item_price_2017,
    ROUND(COALESCE(gmv_2018, 0) / NULLIF(units_2018, 0), 2) AS avg_item_price_2018,
    ROUND(
        (COALESCE(gmv_2018, 0) / NULLIF(units_2018, 0))
        / NULLIF(COALESCE(gmv_2017, 0) / NULLIF(units_2017, 0), 0) - 1,
        4
    ) AS avg_item_price_growth,
    ROUND(total_gmv_2017, 2) AS total_gmv_2017,
    ROUND(total_gmv_2018, 2) AS total_gmv_2018,
    total_units_2017,
    total_units_2018,
    total_orders_2017,
    total_orders_2018
FROM category_metrics
CROSS JOIN item_totals
CROSS JOIN order_totals
ORDER BY gmv_change DESC, product_category;
