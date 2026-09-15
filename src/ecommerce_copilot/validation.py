from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _query_one(connection: Any, sql: str) -> dict[str, Any]:
    cursor = connection.execute(sql)
    columns = [description[0] for description in cursor.description]
    return dict(zip(columns, cursor.fetchone()))


def _query_all(connection: Any, sql: str) -> list[dict[str, Any]]:
    cursor = connection.execute(sql)
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def validate_warehouse(db_path: Path) -> dict[str, Any]:
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError('尚未安装 DuckDB，请运行：python -m pip install -e ".[dev]"') from exc

    connection = duckdb.connect(str(db_path), read_only=True)
    try:
        grain = _query_one(
            connection,
            """
            SELECT
                (SELECT COUNT(*) FROM raw.orders) AS raw_orders,
                (SELECT COUNT(*) FROM analytics.orders) AS analytics_orders,
                (SELECT COUNT(*) FROM raw.order_items) AS raw_order_items,
                (SELECT COUNT(*) FROM analytics.order_items) AS analytics_order_items
            """,
        )
        foreign_keys = _query_one(
            connection,
            """
            SELECT
                (SELECT COUNT(*) FROM raw.orders o LEFT JOIN raw.customers c USING (customer_id)
                 WHERE c.customer_id IS NULL) AS orders_without_customer,
                (SELECT COUNT(*) FROM raw.order_items i LEFT JOIN raw.orders o USING (order_id)
                 WHERE o.order_id IS NULL) AS items_without_order,
                (SELECT COUNT(*) FROM raw.order_items i LEFT JOIN raw.products p USING (product_id)
                 WHERE p.product_id IS NULL) AS items_without_product,
                (SELECT COUNT(*) FROM raw.order_items i LEFT JOIN raw.sellers s USING (seller_id)
                 WHERE s.seller_id IS NULL) AS items_without_seller,
                (SELECT COUNT(*) FROM raw.order_payments p LEFT JOIN raw.orders o USING (order_id)
                 WHERE o.order_id IS NULL) AS payments_without_order,
                (SELECT COUNT(*) FROM raw.order_reviews r LEFT JOIN raw.orders o USING (order_id)
                 WHERE o.order_id IS NULL) AS reviews_without_order
            """,
        )
        reviews = _query_one(
            connection,
            """
            WITH order_reviews AS (
                SELECT
                    order_id,
                    COUNT(*) AS review_count,
                    COUNT(DISTINCT review_score) AS score_count
                FROM raw.order_reviews
                GROUP BY order_id
            )
            SELECT
                (SELECT COUNT(*) FROM raw.order_reviews) AS review_rows,
                (SELECT COUNT(DISTINCT review_id) FROM raw.order_reviews) AS distinct_review_ids,
                (SELECT COUNT(DISTINCT (review_id, order_id)) FROM raw.order_reviews)
                    AS distinct_review_order_pairs,
                COUNT(*) FILTER (WHERE review_count > 1) AS orders_with_multiple_reviews,
                COUNT(*) FILTER (WHERE score_count > 1) AS orders_with_conflicting_scores
            FROM order_reviews
            """,
        )
        payment_reconciliation = _query_one(
            connection,
            """
            WITH compared AS (
                SELECT
                    order_id,
                    gmv + freight_value AS expected_payment,
                    payment_value AS actual_payment
                FROM analytics.orders
                WHERE item_count > 0 AND payment_value IS NOT NULL
            )
            SELECT
                COUNT(*) AS compared_orders,
                COUNT(*) FILTER (
                    WHERE ABS(actual_payment - expected_payment) <= 0.01
                ) AS reconciled_orders,
                ROUND(AVG(ABS(actual_payment - expected_payment)), 2) AS mean_absolute_gap,
                ROUND(MAX(ABS(actual_payment - expected_payment)), 2) AS maximum_absolute_gap,
                ROUND(SUM(actual_payment) - SUM(expected_payment), 2) AS total_gap
            FROM compared
            """,
        )
        headline = _query_one(
            connection,
            """
            WITH users AS (
                SELECT customer_unique_id, COUNT(*) AS order_count
                FROM analytics.orders
                WHERE is_effective_order
                GROUP BY customer_unique_id
            )
            SELECT
                COUNT(*) FILTER (WHERE is_effective_order) AS effective_orders,
                ROUND(SUM(gmv) FILTER (WHERE is_effective_order), 2) AS gmv,
                ROUND(
                    SUM(gmv) FILTER (WHERE is_effective_order)
                    / NULLIF(COUNT(*) FILTER (WHERE is_effective_order), 0),
                    2
                ) AS average_order_value,
                ROUND(AVG(review_score), 3) AS average_latest_review_score,
                ROUND(
                    AVG(CAST(is_late_delivery AS INTEGER)) FILTER (
                        WHERE order_status = 'delivered'
                    ),
                    4
                ) AS late_delivery_rate,
                (SELECT COUNT(*) FROM users) AS effective_users,
                (SELECT COUNT(*) FROM users WHERE order_count >= 2) AS repeat_users,
                ROUND(
                    (SELECT COUNT(*) FROM users WHERE order_count >= 2) * 1.0
                    / NULLIF((SELECT COUNT(*) FROM users), 0),
                    4
                ) AS repeat_purchase_rate
            FROM analytics.orders
            """,
        )
        date_range = _query_one(
            connection,
            """
            SELECT
                MIN(order_purchase_timestamp) AS first_purchase,
                MAX(order_purchase_timestamp) AS last_purchase,
                MIN(order_delivered_customer_date) AS first_delivery,
                MAX(order_delivered_customer_date) AS last_delivery
            FROM raw.orders
            """,
        )
        status_distribution = _query_all(
            connection,
            """
            SELECT
                order_status,
                COUNT(*) AS orders,
                COUNT(*) FILTER (WHERE item_count = 0) AS orders_without_items,
                ROUND(SUM(gmv), 2) AS gmv
            FROM analytics.orders
            GROUP BY order_status
            ORDER BY orders DESC
            """,
        )
    finally:
        connection.close()

    return {
        "grain": grain,
        "foreign_keys": foreign_keys,
        "reviews": reviews,
        "payment_reconciliation": payment_reconciliation,
        "headline": headline,
        "date_range": date_range,
        "status_distribution": status_distribution,
    }


def _pct(numerator: float, denominator: float) -> str:
    return f"{numerator / denominator:.2%}" if denominator else "n.a."


def _markdown_report(result: dict[str, Any], db_path: Path) -> str:
    grain = result["grain"]
    foreign_keys = result["foreign_keys"]
    reviews = result["reviews"]
    payments = result["payment_reconciliation"]
    headline = result["headline"]
    dates = result["date_range"]

    grain_ok = (
        grain["raw_orders"] == grain["analytics_orders"]
        and grain["raw_order_items"] == grain["analytics_order_items"]
    )
    foreign_key_issues = sum(foreign_keys.values())
    payment_rate = _pct(payments["reconciled_orders"], payments["compared_orders"])

    lines = [
        "# 分析数据库校验报告",
        "",
        f"- 数据库：`{db_path}`",
        f"- 订单与明细粒度保持一致：{'是' if grain_ok else '否'}",
        f"- 未匹配外键记录：{foreign_key_issues:,}",
        f"- 支付金额对账通过率（误差不超过0.01）：{payment_rate}",
        "",
        "## 粒度检查",
        "",
        "| 数据层 | 订单行数 | 订单明细行数 |",
        "|---|---:|---:|",
        f"| 原始层 | {grain['raw_orders']:,} | {grain['raw_order_items']:,} |",
        f"| 分析层 | {grain['analytics_orders']:,} | {grain['analytics_order_items']:,} |",
        "",
        "## 外键完整性",
        "",
        "| 检查项 | 未匹配记录 |",
        "|---|---:|",
    ]
    labels = {
        "orders_without_customer": "订单缺少客户",
        "items_without_order": "订单明细缺少订单",
        "items_without_product": "订单明细缺少商品",
        "items_without_seller": "订单明细缺少商家",
        "payments_without_order": "支付记录缺少订单",
        "reviews_without_order": "评价记录缺少订单",
    }
    lines.extend(f"| {labels[key]} | {value:,} |" for key, value in foreign_keys.items())
    lines.extend(
        [
            "",
            "## 评价数据",
            "",
            f"- 评价记录：{reviews['review_rows']:,}",
            f"- 不同评价ID：{reviews['distinct_review_ids']:,}",
            f"- 不同评价ID与订单组合：{reviews['distinct_review_order_pairs']:,}",
            f"- 存在多条评价的订单：{reviews['orders_with_multiple_reviews']:,}",
            f"- 多条评价且评分不同的订单：{reviews['orders_with_conflicting_scores']:,}",
            "- 建模决策：以订单为粒度，保留 `review_answer_timestamp` 最晚的一条评价。",
            "",
            "## 支付对账",
            "",
            "| 对账订单 | 误差不超过0.01 | 平均绝对差额 | 最大绝对差额 | 总差额 |",
            "|---:|---:|---:|---:|---:|",
            (
                f"| {payments['compared_orders']:,} | {payments['reconciled_orders']:,} "
                f"| {payments['mean_absolute_gap']:.2f} "
                f"| {payments['maximum_absolute_gap']:.2f} "
                f"| {payments['total_gap']:.2f} |"
            ),
            "",
            "## 数据范围与基准指标",
            "",
            f"- 下单时间：{dates['first_purchase']} 至 {dates['last_purchase']}",
            f"- 有效订单：{headline['effective_orders']:,}",
            f"- GMV：{headline['gmv']:,.2f}",
            f"- 客单价：{headline['average_order_value']:,.2f}",
            f"- 有效用户：{headline['effective_users']:,}",
            f"- 复购用户：{headline['repeat_users']:,}",
            f"- 复购率：{headline['repeat_purchase_rate']:.2%}",
            f"- 最终评价平均分：{headline['average_latest_review_score']:.3f}",
            f"- 延迟配送率：{headline['late_delivery_rate']:.2%}",
            "",
            "## 订单状态",
            "",
            "| 状态 | 订单数 | 无商品明细订单 | 商品金额 |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in result["status_distribution"]:
        lines.append(
            f"| {row['order_status']} | {row['orders']:,} | "
            f"{row['orders_without_items']:,} | {row['gmv']:,.2f} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_validation_report(db_path: Path, report_dir: Path) -> dict[str, Any]:
    result = validate_warehouse(db_path)
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "warehouse_validation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (report_dir / "warehouse_validation.md").write_text(
        _markdown_report(result, db_path), encoding="utf-8"
    )
    return result
