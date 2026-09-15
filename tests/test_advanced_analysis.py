from datetime import date

import pytest

from ecommerce_copilot.analysis.advanced import (
    summarize_customers,
    summarize_regions,
    summarize_sellers,
)


def test_region_summary_uses_absolute_growth_contribution() -> None:
    rows = [
        {
            "customer_state": "AA",
            "gmv_2017": 60,
            "gmv_2018": 140,
            "gmv_change": 80,
            "delivered_orders": 200,
            "late_delivery_rate": 0.10,
            "avg_review_score": 4.0,
        },
        {
            "customer_state": "BB",
            "gmv_2017": 40,
            "gmv_2018": 60,
            "gmv_change": 20,
            "delivered_orders": 150,
            "late_delivery_rate": 0.20,
            "avg_review_score": 3.0,
        },
    ]

    summary = summarize_regions(rows)

    assert summary["gmv_growth_rate"] == pytest.approx(1)
    assert summary["top_contributors"][0]["customer_state"] == "AA"
    assert summary["late_review_correlation"] == pytest.approx(-1)


def test_seller_summary_calculates_concentration() -> None:
    rows = [
        {
            "seller_id": "a",
            "gmv": 80,
            "gmv_share": 0.8,
            "order_count": 120,
            "late_delivery_rate": 0.1,
            "avg_review_score": 4.0,
        },
        {
            "seller_id": "b",
            "gmv": 20,
            "gmv_share": 0.2,
            "order_count": 100,
            "late_delivery_rate": 0.2,
            "avg_review_score": 3.0,
        },
    ]

    summary = summarize_sellers(rows)

    assert summary["top_10_share"] == pytest.approx(1)
    assert summary["hhi"] == pytest.approx(0.68)
    assert summary["highest_late_sellers"][0]["seller_id"] == "b"


def test_customer_summary_weights_only_mature_cohorts() -> None:
    segments = [
        {"customer_segment": "active_repeat", "users": 10, "gmv": 30},
        {"customer_segment": "dormant_one_time", "users": 90, "gmv": 70},
    ]
    cohort = date(2017, 1, 1)
    cohort_rows = [
        {"cohort_month": cohort, "month_number": 0, "cohort_size": 100, "retained_users": 100},
        {"cohort_month": cohort, "month_number": 1, "cohort_size": 100, "retained_users": 10},
        {"cohort_month": cohort, "month_number": 3, "cohort_size": 100, "retained_users": 5},
        {"cohort_month": cohort, "month_number": 6, "cohort_size": 100, "retained_users": 2},
    ]

    summary = summarize_customers(segments, cohort_rows)

    assert summary["repeat_rate"] == pytest.approx(0.1)
    assert summary["repeat_gmv_share"] == pytest.approx(0.3)
    assert summary["m1_retention"] == pytest.approx(0.1)
