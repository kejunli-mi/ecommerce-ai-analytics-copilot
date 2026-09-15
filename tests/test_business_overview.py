from datetime import date

import pytest

from ecommerce_copilot.analysis.business_overview import summarize_monthly_metrics


def _rows() -> list[dict[str, object]]:
    rows = []
    for year in (2017, 2018):
        for month in range(1, 9):
            orders = 100 if year == 2017 else 150
            gmv = 10_000 if year == 2017 else 14_250
            rows.append(
                {
                    "purchase_month": date(year, month, 1),
                    "gmv": gmv,
                    "order_count": orders,
                    "gmv_mom_growth": None if not rows else 0.0,
                }
            )
    return rows


def test_summary_uses_like_for_like_months() -> None:
    summary = summarize_monthly_metrics(_rows())

    assert summary["ytd_gmv_growth"] == pytest.approx(0.425)
    assert summary["ytd_order_growth"] == pytest.approx(0.5)
    assert summary["ytd_aov_growth"] == pytest.approx(-0.05)


def test_summary_rejects_incomplete_comparison() -> None:
    with pytest.raises(ValueError, match="完整数据"):
        summarize_monthly_metrics(_rows()[:-1])
