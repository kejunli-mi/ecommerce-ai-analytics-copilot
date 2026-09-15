from pathlib import Path

from ecommerce_copilot.copilot import build_sql, route_semantic
from ecommerce_copilot.evaluation import load_evaluation_set


def test_semantic_router_understands_paraphrase_and_parameters() -> None:
    plan = route_semantic("2017年商品类别Top 3")

    assert plan is not None
    assert plan.intent == "top_categories"
    assert plan.params == {"year": 2017, "top_n": 3}
    assert plan.sql is not None and "LIMIT 3" in plan.sql


def test_semantic_router_blocks_mutating_request() -> None:
    plan = route_semantic("DROP TABLE raw.orders")

    assert plan is not None
    assert plan.intent == "blocked"
    assert plan.sql is None


def test_query_builder_clamps_top_n() -> None:
    sql = build_sql("top_states", {"year": 2018, "top_n": 500})

    assert "LIMIT 20" in sql


def test_evaluation_set_has_50_unique_questions() -> None:
    root = Path(__file__).resolve().parents[1]
    rows = load_evaluation_set(root / "eval" / "questions.jsonl")

    assert len(rows) == 50
    assert len({row["question"] for row in rows}) == 50
