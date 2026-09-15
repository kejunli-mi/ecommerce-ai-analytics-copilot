import pytest

from ecommerce_copilot.analysis.category_growth import summarize_category_metrics


def _row(
    category: str,
    gmv_2017: float,
    gmv_2018: float,
    units_2017: int,
    units_2018: int,
) -> dict[str, object]:
    total_2017 = 100.0
    total_2018 = 200.0
    return {
        "product_category": category,
        "gmv_2017": gmv_2017,
        "gmv_2018": gmv_2018,
        "gmv_change": gmv_2018 - gmv_2017,
        "gmv_growth_rate": gmv_2018 / gmv_2017 - 1,
        "growth_contribution": (gmv_2018 - gmv_2017) / (total_2018 - total_2017),
        "gmv_share_2017": gmv_2017 / total_2017,
        "gmv_share_2018": gmv_2018 / total_2018,
        "gmv_share_change": gmv_2018 / total_2018 - gmv_2017 / total_2017,
        "units_2017": units_2017,
        "units_2018": units_2018,
        "unit_growth_rate": units_2018 / units_2017 - 1,
    }


def test_summary_ranks_growth_by_absolute_contribution() -> None:
    rows = [
        _row("large", 80, 170, 8, 17),
        _row("small", 20, 30, 2, 3),
    ]

    summary = summarize_category_metrics(rows)

    assert summary["total_gmv_change"] == pytest.approx(100)
    assert summary["top_contributors"][0]["product_category"] == "large"
    assert summary["top_five_growth_contribution"] == pytest.approx(1)
    assert summary["unit_growth_rate"] == pytest.approx(1)


def test_summary_rejects_empty_rows() -> None:
    with pytest.raises(ValueError, match="为空"):
        summarize_category_metrics([])
