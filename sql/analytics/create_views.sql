CREATE OR REPLACE VIEW analytics.payment_by_order AS
SELECT
    order_id,
    SUM(payment_value) AS payment_value,
    MAX(payment_installments) AS max_payment_installments,
    COUNT(*) AS payment_record_count,
    COUNT(DISTINCT payment_type) AS payment_type_count
FROM raw.order_payments
GROUP BY order_id;

CREATE OR REPLACE VIEW analytics.review_by_order AS
WITH ranked AS (
    SELECT
        order_id,
        review_id,
        review_score,
        review_creation_date,
        review_answer_timestamp,
        COUNT(*) OVER (PARTITION BY order_id) AS review_count,
        ROW_NUMBER() OVER (
            PARTITION BY order_id
            ORDER BY review_answer_timestamp DESC, review_creation_date DESC, review_id DESC
        ) AS review_recency_rank
    FROM raw.order_reviews
)
SELECT
    order_id,
    review_id AS latest_review_id,
    review_score,
    review_count,
    review_creation_date AS latest_review_creation_date,
    review_answer_timestamp AS latest_review_answer_timestamp
FROM ranked
WHERE review_recency_rank = 1;

CREATE OR REPLACE VIEW analytics.item_by_order AS
SELECT
    order_id,
    COUNT(*) AS item_count,
    COUNT(DISTINCT product_id) AS distinct_product_count,
    COUNT(DISTINCT seller_id) AS seller_count,
    SUM(price) AS gmv,
    SUM(freight_value) AS freight_value
FROM raw.order_items
GROUP BY order_id;

CREATE OR REPLACE VIEW analytics.orders AS
SELECT
    o.order_id,
    o.customer_id,
    c.customer_unique_id,
    c.customer_city,
    c.customer_state,
    o.order_status,
    o.order_purchase_timestamp,
    o.order_approved_at,
    o.order_delivered_carrier_date,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,
    COALESCE(i.item_count, 0) AS item_count,
    COALESCE(i.distinct_product_count, 0) AS distinct_product_count,
    COALESCE(i.seller_count, 0) AS seller_count,
    COALESCE(i.gmv, 0) AS gmv,
    COALESCE(i.freight_value, 0) AS freight_value,
    p.payment_value,
    p.max_payment_installments,
    p.payment_record_count,
    r.review_score,
    r.review_count,
    CASE
        WHEN o.order_purchase_timestamp IS NOT NULL
         AND o.order_status NOT IN ('canceled', 'unavailable')
        THEN TRUE ELSE FALSE
    END AS is_effective_order,
    CASE
        WHEN o.order_delivered_customer_date IS NULL
          OR o.order_estimated_delivery_date IS NULL
        THEN NULL
        WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
        THEN TRUE
        ELSE FALSE
    END AS is_late_delivery,
    date_diff(
        'day',
        CAST(o.order_purchase_timestamp AS TIMESTAMP),
        CAST(o.order_delivered_customer_date AS TIMESTAMP)
    ) AS delivery_days
FROM raw.orders AS o
LEFT JOIN raw.customers AS c USING (customer_id)
LEFT JOIN analytics.item_by_order AS i USING (order_id)
LEFT JOIN analytics.payment_by_order AS p USING (order_id)
LEFT JOIN analytics.review_by_order AS r USING (order_id);

CREATE OR REPLACE VIEW analytics.order_items AS
SELECT
    oi.order_id,
    oi.order_item_id,
    o.customer_unique_id,
    o.order_status,
    o.order_purchase_timestamp,
    o.is_effective_order,
    oi.product_id,
    COALESCE(t.product_category_name_english, pr.product_category_name) AS product_category,
    oi.seller_id,
    s.seller_city,
    s.seller_state,
    oi.price,
    oi.freight_value
FROM raw.order_items AS oi
JOIN analytics.orders AS o USING (order_id)
LEFT JOIN raw.products AS pr USING (product_id)
LEFT JOIN raw.sellers AS s USING (seller_id)
LEFT JOIN raw.category_translation AS t USING (product_category_name);