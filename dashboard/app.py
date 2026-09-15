from __future__ import annotations

import json
from datetime import date
from typing import Any

import duckdb
import streamlit as st

from ecommerce_copilot.copilot import ask
from ecommerce_copilot.settings import PROJECT_ROOT, Settings


def _period(year: int) -> tuple[date, date]:
    return date(year, 1, 1), date(year, 9, 1)


@st.cache_data(show_spinner=False)
def _query(db_path: str, sql: str, params: tuple[Any, ...] = ()) -> Any:
    connection = duckdb.connect(db_path, read_only=True)
    try:
        return connection.execute(sql, list(params)).df()
    finally:
        connection.close()


def _format_number(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,.2f}"


def _overview(db_path: str, year: int) -> None:
    start, end = _period(year)
    metrics = _query(
        db_path,
        """
        SELECT
            SUM(gmv) AS gmv,
            COUNT(*) AS orders,
            SUM(gmv) / NULLIF(COUNT(*), 0) AS aov,
            COUNT(DISTINCT customer_unique_id) AS users
        FROM analytics.orders
        WHERE is_effective_order
          AND order_purchase_timestamp >= ?
          AND order_purchase_timestamp < ?
        """,
        (start, end),
    ).iloc[0]
    columns = st.columns(4)
    columns[0].metric("GMV", _format_number(float(metrics["gmv"])))
    columns[1].metric("有效订单", f"{int(metrics['orders']):,}")
    columns[2].metric("客单价", f"{float(metrics['aov']):,.2f}")
    columns[3].metric("购买用户", f"{int(metrics['users']):,}")

    monthly = _query(
        db_path,
        """
        SELECT
            CAST(date_trunc('month', order_purchase_timestamp) AS DATE) AS month,
            SUM(gmv) AS gmv,
            COUNT(*) AS orders
        FROM analytics.orders
        WHERE is_effective_order
          AND order_purchase_timestamp >= ?
          AND order_purchase_timestamp < ?
        GROUP BY 1
        ORDER BY 1
        """,
        (start, end),
    )
    st.subheader("月度GMV")
    st.line_chart(monthly.set_index("month")[["gmv"]], color="#2563EB")
    st.caption("GMV为有效订单商品金额，不含运费。")


def _categories(db_path: str, year: int) -> None:
    start, end = _period(year)
    rows = _query(
        db_path,
        """
        SELECT
            COALESCE(product_category, 'unknown_category') AS product_category,
            SUM(price) AS gmv,
            COUNT(*) AS units,
            COUNT(DISTINCT order_id) AS category_orders
        FROM analytics.order_items
        WHERE is_effective_order
          AND order_purchase_timestamp >= ?
          AND order_purchase_timestamp < ?
        GROUP BY 1
        ORDER BY gmv DESC
        LIMIT 15
        """,
        (start, end),
    )
    st.subheader("品类GMV Top 15")
    st.bar_chart(rows.set_index("product_category")[["gmv"]], color="#0F766E")
    st.dataframe(rows, hide_index=True, use_container_width=True)
    st.caption("一笔订单可包含多个品类，category_orders不可直接加总。")


def _regions(db_path: str, year: int) -> None:
    start, end = _period(year)
    rows = _query(
        db_path,
        """
        SELECT
            COALESCE(customer_state, 'unknown_state') AS customer_state,
            SUM(gmv) AS gmv,
            COUNT(*) AS orders,
            AVG(CAST(is_late_delivery AS INTEGER)) FILTER (
                WHERE order_status = 'delivered' AND is_late_delivery IS NOT NULL
            ) AS late_delivery_rate,
            AVG(review_score) FILTER (WHERE review_score IS NOT NULL) AS avg_review_score
        FROM analytics.orders
        WHERE is_effective_order
          AND order_purchase_timestamp >= ?
          AND order_purchase_timestamp < ?
        GROUP BY 1
        ORDER BY gmv DESC
        """,
        (start, end),
    )
    chart_column, table_column = st.columns([1.1, 1])
    with chart_column:
        st.subheader("地区GMV")
        st.bar_chart(rows.head(12).set_index("customer_state")[["gmv"]], color="#2563EB")
    with table_column:
        st.subheader("履约与评分")
        display = rows[
            ["customer_state", "orders", "late_delivery_rate", "avg_review_score"]
        ].copy()
        display["late_delivery_rate"] = display["late_delivery_rate"].map(
            lambda value: f"{value:.1%}"
        )
        display["avg_review_score"] = display["avg_review_score"].map(
            lambda value: f"{value:.2f}"
        )
        st.dataframe(display, hide_index=True, use_container_width=True, height=430)


def _customers(db_path: str) -> None:
    segments = _query(
        db_path,
        (PROJECT_ROOT / "sql" / "analysis" / "customer_segments.sql").read_text(
            encoding="utf-8"
        ),
    )
    labels = {
        "active_repeat": "活跃复购",
        "at_risk_repeat": "沉睡复购",
        "recent_one_time": "近期首购",
        "dormant_one_time": "沉睡一次性",
    }
    segments["segment"] = segments["customer_segment"].map(labels)
    repeat_rate = segments.loc[
        segments["customer_segment"].isin(["active_repeat", "at_risk_repeat"]), "users"
    ].sum() / segments["users"].sum()
    st.metric("截止2018-08的复购率", f"{repeat_rate:.1%}")
    st.subheader("用户与GMV分层占比")
    st.bar_chart(
        segments.set_index("segment")[["user_share", "gmv_share"]],
        color=["#2563EB", "#0F766E"],
    )
    st.dataframe(
        segments[
            ["segment", "users", "user_share", "gmv", "gmv_share", "avg_customer_gmv"]
        ],
        hide_index=True,
        use_container_width=True,
    )


def _copilot(db_path: str) -> None:
    st.subheader("自然语言取数")
    question = st.text_input(
        "输入问题",
        value="2018年GMV最高的前5个品类",
        help="支持GMV、订单、客单价、品类、地区、商家、履约、评分和复购。",
    )
    if st.button("运行查询", type="primary"):
        connection = duckdb.connect(db_path, read_only=True)
        try:
            result = ask(connection, question)
        finally:
            connection.close()
        if result["status"] == "ok":
            import pandas as pd

            st.success(result["explanation"])
            st.dataframe(
                pd.DataFrame(result["rows"], columns=result["columns"]),
                hide_index=True,
                use_container_width=True,
            )
            with st.expander("查看SQL"):
                st.code(result["sql"], language="sql")
        elif result["status"] == "blocked":
            st.error(result["message"])
        else:
            st.warning(result["message"])

    evaluation_path = PROJECT_ROOT / "reports" / "generated" / "copilot_evaluation.json"
    if evaluation_path.exists():
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        semantic = evaluation["semantic"]
        columns = st.columns(3)
        columns[0].metric("离线答案准确率", f"{semantic['answer_accuracy']:.1%}")
        columns[1].metric("安全拦截率", f"{semantic['safety_accuracy']:.1%}")
        columns[2].metric("中位延迟", f"{semantic['median_latency_ms']:.1f} ms")
        st.caption("数值来自本地50道回归评测，不代表真实世界泛化能力。")


def main() -> None:
    st.set_page_config(page_title="电商经营数据分析 Copilot", layout="wide")
    st.title("电商经营数据分析 Copilot")
    st.caption("Olist公开数据：经营分析、履约洞察与可控自然语言取数")
    db_path = Settings().db_path
    if not db_path.exists():
        st.error("未找到分析数据库，请先运行 ecommerce-copilot build。")
        st.stop()

    year = st.sidebar.selectbox("同期年份（1至8月）", options=[2018, 2017])
    st.sidebar.caption("所有年度比较固定使用1至8月完整月份。")
    overview_tab, category_tab, region_tab, customer_tab, copilot_tab = st.tabs(
        ["经营大盘", "品类", "地区与履约", "用户", "Copilot"]
    )
    with overview_tab:
        _overview(str(db_path), year)
    with category_tab:
        _categories(str(db_path), year)
    with region_tab:
        _regions(str(db_path), year)
    with customer_tab:
        _customers(str(db_path))
    with copilot_tab:
        _copilot(str(db_path))


if __name__ == "__main__":
    main()
