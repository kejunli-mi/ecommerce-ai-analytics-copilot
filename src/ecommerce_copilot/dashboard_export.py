from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ecommerce_copilot.copilot import ask
from ecommerce_copilot.settings import PROJECT_ROOT


def _query(connection: Any, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    cursor = connection.execute(sql, params or [])
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _year_data(connection: Any, year: int) -> dict[str, Any]:
    start = f"{year}-01-01"
    end = f"{year}-09-01"
    metrics = _query(
        connection,
        """
        SELECT
            ROUND(SUM(gmv), 2) AS gmv,
            COUNT(*) AS orders,
            ROUND(SUM(gmv) / NULLIF(COUNT(*), 0), 2) AS aov,
            COUNT(DISTINCT customer_unique_id) AS users
        FROM analytics.orders
        WHERE is_effective_order
          AND order_purchase_timestamp >= CAST(? AS TIMESTAMP)
          AND order_purchase_timestamp < CAST(? AS TIMESTAMP)
        """,
        [start, end],
    )[0]
    monthly = _query(
        connection,
        """
        SELECT
            strftime(date_trunc('month', order_purchase_timestamp), '%Y-%m') AS month,
            ROUND(SUM(gmv), 2) AS gmv,
            COUNT(*) AS orders
        FROM analytics.orders
        WHERE is_effective_order
          AND order_purchase_timestamp >= CAST(? AS TIMESTAMP)
          AND order_purchase_timestamp < CAST(? AS TIMESTAMP)
        GROUP BY 1
        ORDER BY 1
        """,
        [start, end],
    )
    categories = _query(
        connection,
        """
        SELECT
            replace(COALESCE(product_category, 'unknown_category'), '_', ' ') AS category,
            ROUND(SUM(price), 2) AS gmv,
            COUNT(*) AS units
        FROM analytics.order_items
        WHERE is_effective_order
          AND order_purchase_timestamp >= CAST(? AS TIMESTAMP)
          AND order_purchase_timestamp < CAST(? AS TIMESTAMP)
        GROUP BY 1
        ORDER BY gmv DESC
        LIMIT 10
        """,
        [start, end],
    )
    states = _query(
        connection,
        """
        SELECT
            COALESCE(customer_state, 'unknown') AS state,
            ROUND(SUM(gmv), 2) AS gmv,
            COUNT(*) AS orders,
            ROUND(AVG(CAST(is_late_delivery AS INTEGER)) FILTER (
                WHERE order_status = 'delivered' AND is_late_delivery IS NOT NULL
            ), 4) AS late_rate,
            ROUND(AVG(review_score) FILTER (WHERE review_score IS NOT NULL), 3) AS review
        FROM analytics.orders
        WHERE is_effective_order
          AND order_purchase_timestamp >= CAST(? AS TIMESTAMP)
          AND order_purchase_timestamp < CAST(? AS TIMESTAMP)
        GROUP BY 1
        ORDER BY gmv DESC
        LIMIT 12
        """,
        [start, end],
    )
    return {"metrics": metrics, "monthly": monthly, "categories": categories, "states": states}


def export_dashboard_data(db_path: Path, output_path: Path) -> dict[str, Any]:
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError('尚未安装 DuckDB，请运行：python -m pip install -e ".[dev]"') from exc

    connection = duckdb.connect(str(db_path), read_only=True)
    try:
        years = {str(year): _year_data(connection, year) for year in (2017, 2018)}
        segment_sql = (PROJECT_ROOT / "sql" / "analysis" / "customer_segments.sql").read_text(
            encoding="utf-8"
        )
        segments = _query(connection, segment_sql)
        example = ask(connection, "2018年GMV最高的前5个品类")
    finally:
        connection.close()

    evaluation_path = PROJECT_ROOT / "reports" / "generated" / "copilot_evaluation.json"
    evaluation = (
        json.loads(evaluation_path.read_text(encoding="utf-8"))
        if evaluation_path.exists()
        else None
    )
    payload = {
        "generated_from": "Olist public dataset; complete January-August periods",
        "years": years,
        "segments": segments,
        "copilot_example": example,
        "evaluation": evaluation,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return payload
