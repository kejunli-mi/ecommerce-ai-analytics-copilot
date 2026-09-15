-- 首购月队列留存；为保证可比性，仅使用2017-01至2018-08完整月份。
WITH base AS (
    SELECT
        customer_unique_id,
        order_id,
        CAST(date_trunc('month', order_purchase_timestamp) AS DATE) AS purchase_month,
        gmv
    FROM analytics.orders
    WHERE is_effective_order
      AND customer_unique_id IS NOT NULL
      AND order_purchase_timestamp >= TIMESTAMP '2017-01-01'
      AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
),
first_purchase AS (
    SELECT customer_unique_id, MIN(purchase_month) AS cohort_month
    FROM base
    GROUP BY 1
),
cohort_activity AS (
    SELECT
        fp.cohort_month,
        date_diff('month', fp.cohort_month, b.purchase_month) AS month_number,
        COUNT(DISTINCT b.customer_unique_id) AS retained_users,
        COUNT(DISTINCT b.order_id) AS orders,
        SUM(b.gmv) AS gmv
    FROM base AS b
    JOIN first_purchase AS fp USING (customer_unique_id)
    GROUP BY 1, 2
),
with_size AS (
    SELECT
        *,
        MAX(retained_users) FILTER (WHERE month_number = 0)
            OVER (PARTITION BY cohort_month) AS cohort_size
    FROM cohort_activity
)
SELECT
    cohort_month,
    month_number,
    cohort_size,
    retained_users,
    ROUND(retained_users * 1.0 / NULLIF(cohort_size, 0), 6) AS retention_rate,
    orders,
    ROUND(gmv, 2) AS gmv
FROM with_size
WHERE month_number BETWEEN 0 AND 12
ORDER BY cohort_month, month_number;
