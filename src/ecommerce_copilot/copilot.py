from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

SUPPORTED_YEARS = {2017, 2018}
SAFETY_TERMS = (
    "drop ",
    "delete ",
    "update ",
    "insert ",
    "alter ",
    "truncate ",
    "create table",
    "删除",
    "删表",
    "清空",
    "修改数据",
    "更新数据",
)


@dataclass(frozen=True)
class QueryPlan:
    intent: str
    params: dict[str, int]
    sql: str | None
    explanation: str
    blocked_reason: str | None = None


def _normalize(question: str) -> str:
    return re.sub(r"\s+", " ", question.strip().lower())


def _extract_year(question: str) -> int:
    match = re.search(r"20(17|18)", question)
    year = int(match.group(0)) if match else 2018
    return year if year in SUPPORTED_YEARS else 2018


def _extract_top_n(question: str) -> int:
    patterns = (r"前\s*(\d+)", r"top\s*(\d+)", r"排名\s*(\d+)")
    for pattern in patterns:
        match = re.search(pattern, question, flags=re.IGNORECASE)
        if match:
            return min(20, max(1, int(match.group(1))))
    return 5


def _period(year: int, column: str = "order_purchase_timestamp") -> str:
    if year not in SUPPORTED_YEARS:
        raise ValueError("仅支持2017和2018年同期分析")
    return (
        f"{column} >= TIMESTAMP '{year}-01-01' "
        f"AND {column} < TIMESTAMP '{year}-09-01'"
    )


def build_sql(intent: str, params: dict[str, int]) -> str:
    year = int(params.get("year", 2018))
    top_n = min(20, max(1, int(params.get("top_n", 5))))
    period = _period(year)
    queries = {
        "total_gmv": f"""
            SELECT ROUND(SUM(gmv), 2) AS gmv
            FROM analytics.orders
            WHERE is_effective_order AND {period}
        """,
        "order_count": f"""
            SELECT COUNT(*) AS effective_orders
            FROM analytics.orders
            WHERE is_effective_order AND {period}
        """,
        "average_order_value": f"""
            SELECT ROUND(SUM(gmv) / NULLIF(COUNT(*), 0), 2) AS average_order_value
            FROM analytics.orders
            WHERE is_effective_order AND {period}
        """,
        "top_categories": f"""
            SELECT
                COALESCE(product_category, 'unknown_category') AS product_category,
                ROUND(SUM(price), 2) AS gmv
            FROM analytics.order_items
            WHERE is_effective_order AND {period}
            GROUP BY 1
            ORDER BY gmv DESC, product_category
            LIMIT {top_n}
        """,
        "top_states": f"""
            SELECT
                COALESCE(customer_state, 'unknown_state') AS customer_state,
                ROUND(SUM(gmv), 2) AS gmv
            FROM analytics.orders
            WHERE is_effective_order AND {period}
            GROUP BY 1
            ORDER BY gmv DESC, customer_state
            LIMIT {top_n}
        """,
        "late_delivery_rate": f"""
            SELECT ROUND(AVG(CAST(is_late_delivery AS INTEGER)), 4) AS late_delivery_rate
            FROM analytics.orders
            WHERE is_effective_order
              AND order_status = 'delivered'
              AND is_late_delivery IS NOT NULL
              AND {period}
        """,
        "average_review_score": f"""
            SELECT ROUND(AVG(review_score), 3) AS average_review_score
            FROM analytics.orders
            WHERE is_effective_order
              AND review_score IS NOT NULL
              AND {period}
        """,
        "repeat_rate": f"""
            WITH users AS (
                SELECT customer_unique_id, COUNT(*) AS order_count
                FROM analytics.orders
                WHERE is_effective_order
                  AND customer_unique_id IS NOT NULL
                  AND {period}
                GROUP BY 1
            )
            SELECT ROUND(
                COUNT(*) FILTER (WHERE order_count >= 2) * 1.0 / NULLIF(COUNT(*), 0),
                4
            ) AS repeat_rate
            FROM users
        """,
        "top_sellers": f"""
            SELECT seller_id, ROUND(SUM(price), 2) AS gmv
            FROM analytics.order_items
            WHERE is_effective_order AND {period}
            GROUP BY 1
            ORDER BY gmv DESC, seller_id
            LIMIT {top_n}
        """,
        "monthly_gmv": f"""
            SELECT
                CAST(date_trunc('month', order_purchase_timestamp) AS DATE) AS month,
                ROUND(SUM(gmv), 2) AS gmv
            FROM analytics.orders
            WHERE is_effective_order AND {period}
            GROUP BY 1
            ORDER BY 1
        """,
    }
    if intent not in queries:
        raise ValueError(f"不支持的意图：{intent}")
    return "\n".join(line.strip() for line in queries[intent].strip().splitlines())


def _plan(intent: str, question: str) -> QueryPlan:
    params = {"year": _extract_year(question)}
    if intent in {"top_categories", "top_states", "top_sellers"}:
        params["top_n"] = _extract_top_n(question)
    explanations = {
        "total_gmv": "按统一口径计算有效订单GMV，不含运费。",
        "order_count": "统计有效订单数。",
        "average_order_value": "客单价等于GMV除以有效订单数。",
        "top_categories": "按商品明细GMV汇总并排序品类。",
        "top_states": "按收货州汇总有效订单GMV。",
        "late_delivery_rate": "在可比的已送达订单中计算延迟配送率。",
        "average_review_score": "计算有最终评价的有效订单平均分。",
        "repeat_rate": "按customer_unique_id识别同期至少两笔订单的用户。",
        "top_sellers": "按商家GMV汇总排名。",
        "monthly_gmv": "按购买月汇总有效订单GMV。",
    }
    return QueryPlan(intent, params, build_sql(intent, params), explanations[intent])


def route_baseline(question: str) -> QueryPlan | None:
    text = _normalize(question)
    if "月度趋势" in text:
        return _plan("monthly_gmv", text)
    if "品类" in text and ("最高" in text or "排名" in text):
        return _plan("top_categories", text)
    if "州" in text and ("最高" in text or "排名" in text):
        return _plan("top_states", text)
    if "延迟配送率" in text:
        return _plan("late_delivery_rate", text)
    if "平均评价分" in text:
        return _plan("average_review_score", text)
    if "复购率" in text:
        return _plan("repeat_rate", text)
    if "商家" in text and ("最高" in text or "排名" in text):
        return _plan("top_sellers", text)
    if "客单价" in text:
        return _plan("average_order_value", text)
    if "订单量" in text:
        return _plan("order_count", text)
    if "gmv" in text and "总" in text:
        return _plan("total_gmv", text)
    return None


def route_semantic(question: str) -> QueryPlan | None:
    text = _normalize(question)
    if any(term in text for term in SAFETY_TERMS):
        return QueryPlan(
            intent="blocked",
            params={},
            sql=None,
            explanation="请求包含写入或破坏性操作。",
            blocked_reason="Copilot只允许只读分析查询。",
        )
    if any(term in text for term in ("每个月", "月度", "按月", "月趋势")) and any(
        term in text for term in ("gmv", "成交额", "销售额")
    ):
        return _plan("monthly_gmv", text)
    if any(term in text for term in ("品类", "商品类别", "category")) and any(
        term in text for term in ("前", "top", "排名", "最高", "卖得最好", "领先")
    ):
        return _plan("top_categories", text)
    if any(term in text for term in ("州", "地区", "state")) and any(
        term in text for term in ("前", "top", "排名", "最高", "领先", "最多")
    ):
        return _plan("top_states", text)
    if any(term in text for term in ("商家", "卖家", "seller")) and any(
        term in text for term in ("前", "top", "排名", "最高", "领先")
    ):
        return _plan("top_sellers", text)
    if any(term in text for term in ("延迟", "逾期", "晚到")) and any(
        term in text for term in ("配送", "送达", "订单")
    ):
        return _plan("late_delivery_rate", text)
    if any(term in text for term in ("评分", "评价分", "星级", "口碑")):
        return _plan("average_review_score", text)
    if any(term in text for term in ("复购", "再次购买", "购买两次", "回购")):
        return _plan("repeat_rate", text)
    if any(term in text for term in ("客单价", "平均每单", "每笔订单平均")):
        return _plan("average_order_value", text)
    if any(term in text for term in ("订单量", "订单数", "多少笔订单")):
        return _plan("order_count", text)
    if any(term in text for term in ("gmv", "成交额", "销售额", "商品交易额")):
        return _plan("total_gmv", text)
    return None


def execute_plan(connection: Any, plan: QueryPlan) -> tuple[list[str], list[tuple[Any, ...]]]:
    if plan.sql is None:
        raise ValueError(plan.blocked_reason or "该请求没有可执行SQL")
    normalized = plan.sql.lstrip().upper()
    if not normalized.startswith(("SELECT", "WITH")):
        raise ValueError("Copilot只允许SELECT或WITH查询")
    cursor = connection.execute(plan.sql)
    columns = [description[0] for description in cursor.description]
    return columns, cursor.fetchall()


def ask(connection: Any, question: str, provider: str = "semantic") -> dict[str, Any]:
    router = route_semantic if provider == "semantic" else route_baseline
    plan = router(question)
    if plan is None:
        return {
            "status": "unsupported",
            "question": question,
            "message": "暂时无法识别该问题，请尝试GMV、订单、品类、地区、商家、履约或复购问题。",
        }
    if plan.intent == "blocked":
        return {
            "status": "blocked",
            "question": question,
            "intent": plan.intent,
            "message": plan.blocked_reason,
        }
    columns, rows = execute_plan(connection, plan)
    return {
        "status": "ok",
        "question": question,
        "intent": plan.intent,
        "params": plan.params,
        "explanation": plan.explanation,
        "sql": plan.sql,
        "columns": columns,
        "rows": rows,
    }
