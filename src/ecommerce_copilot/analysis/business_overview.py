from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any

from ecommerce_copilot.settings import PROJECT_ROOT

ANALYSIS_START = date(2017, 1, 1)
ANALYSIS_END_EXCLUSIVE = date(2018, 9, 1)


def _query_all(connection: Any, sql: str) -> list[dict[str, Any]]:
    cursor = connection.execute(sql)
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def load_monthly_metrics(connection: Any) -> list[dict[str, Any]]:
    sql_path = PROJECT_ROOT / "sql" / "analysis" / "monthly_metrics.sql"
    return _query_all(connection, sql_path.read_text(encoding="utf-8"))


def _growth(current: float, previous: float) -> float:
    if previous == 0:
        raise ValueError("增长率的上期值不能为0")
    return current / previous - 1


def summarize_monthly_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("月度指标为空")

    period_2017_ytd = [row for row in rows if row["purchase_month"] < date(2017, 9, 1)]
    period_2018_ytd = [
        row for row in rows if date(2018, 1, 1) <= row["purchase_month"] < ANALYSIS_END_EXCLUSIVE
    ]
    if len(period_2017_ytd) != 8 or len(period_2018_ytd) != 8:
        raise ValueError("同比汇总要求2017年和2018年各有1至8月的完整数据")

    def totals(period: list[dict[str, Any]]) -> dict[str, float]:
        gmv = sum(float(row["gmv"]) for row in period)
        orders = sum(int(row["order_count"]) for row in period)
        return {"gmv": gmv, "orders": orders, "aov": gmv / orders}

    ytd_2017 = totals(period_2017_ytd)
    ytd_2018 = totals(period_2018_ytd)
    peak = max(rows, key=lambda row: float(row["gmv"]))
    comparable_mom = [row for row in rows if row["gmv_mom_growth"] is not None]
    largest_increase = max(comparable_mom, key=lambda row: float(row["gmv_mom_growth"]))
    largest_decline = min(comparable_mom, key=lambda row: float(row["gmv_mom_growth"]))
    large_changes = [row for row in comparable_mom if abs(float(row["gmv_mom_growth"])) >= 0.20]

    return {
        "analysis_start": ANALYSIS_START,
        "analysis_end": date(2018, 8, 31),
        "period_gmv": sum(float(row["gmv"]) for row in rows),
        "period_orders": sum(int(row["order_count"]) for row in rows),
        "ytd_2017": ytd_2017,
        "ytd_2018": ytd_2018,
        "ytd_gmv_growth": _growth(ytd_2018["gmv"], ytd_2017["gmv"]),
        "ytd_order_growth": _growth(ytd_2018["orders"], ytd_2017["orders"]),
        "ytd_aov_growth": _growth(ytd_2018["aov"], ytd_2017["aov"]),
        "peak_month": peak["purchase_month"],
        "peak_gmv": float(peak["gmv"]),
        "peak_orders": int(peak["order_count"]),
        "largest_mom_increase_month": largest_increase["purchase_month"],
        "largest_mom_increase": float(largest_increase["gmv_mom_growth"]),
        "largest_mom_decline_month": largest_decline["purchase_month"],
        "largest_mom_decline": float(largest_decline["gmv_mom_growth"]),
        "large_mom_changes": large_changes,
    }


def verify_monthly_metrics(connection: Any, rows: list[dict[str, Any]]) -> None:
    direct = connection.execute(
        """
        SELECT
            ROUND(SUM(gmv), 2) AS gmv,
            COUNT(*) AS orders
        FROM analytics.orders
        WHERE is_effective_order
          AND order_purchase_timestamp >= TIMESTAMP '2017-01-01'
          AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
        """
    ).fetchone()
    monthly_gmv = round(sum(float(row["gmv"]) for row in rows), 2)
    monthly_orders = sum(int(row["order_count"]) for row in rows)
    if (monthly_gmv, monthly_orders) != (float(direct[0]), int(direct[1])):
        raise AssertionError("月度汇总与订单宽表总计不一致")

    for row in rows:
        expected_aov = float(row["gmv"]) / int(row["order_count"])
        if abs(expected_aov - float(row["average_order_value"])) > 0.011:
            raise AssertionError(f"{row['purchase_month']} 的客单价计算不一致")


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _configure_chinese_font() -> None:
    from matplotlib import font_manager, rcParams

    candidates = (
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/System/Library/Fonts/STHeiti Light.ttc"),
    )
    for path in candidates:
        if path.exists():
            font_manager.fontManager.addfont(str(path))
            rcParams["font.family"] = font_manager.FontProperties(fname=str(path)).get_name()
            break
    rcParams["axes.unicode_minus"] = False


def _plot_monthly_trends(rows: list[dict[str, Any]], output_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    _configure_chinese_font()
    months = [row["purchase_month"] for row in rows]
    series = (
        ("月度GMV（百万）", [float(row["gmv"]) for row in rows], "#2563EB", 1_000_000),
        ("有效订单量（千单）", [int(row["order_count"]) for row in rows], "#0F766E", 1_000),
        ("客单价", [float(row["average_order_value"]) for row in rows], "#D97706", 1),
    )
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    fig.suptitle("电商经营月度趋势", fontsize=16, fontweight="bold", x=0.08, ha="left")

    for index, (axis, (title, values, color, scale)) in enumerate(zip(axes, series, strict=True)):
        plotted = [value / scale for value in values]
        axis.plot(months, plotted, color=color, linewidth=2.2, marker="o", markersize=4)
        if index < 2:
            axis.fill_between(months, plotted, color=color, alpha=0.08)
            axis.set_ylim(bottom=0)
        else:
            lower_bound = min(plotted) - 8
            upper_bound = max(plotted) + 8
            axis.set_ylim(lower_bound, upper_bound)
            axis.fill_between(months, plotted, lower_bound, color=color, alpha=0.08)
        axis.set_title(title, loc="left", fontsize=11, fontweight="bold")
        axis.grid(axis="y", color="#D1D5DB", linewidth=0.7, alpha=0.7)
        axis.spines[["top", "right", "left"]].set_visible(False)
        axis.tick_params(axis="y", length=0)
        axis.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.1f}"))
        axis.axvline(date(2018, 1, 1), color="#9CA3AF", linestyle="--", linewidth=0.8)

    peak_index = max(range(len(rows)), key=lambda position: float(rows[position]["gmv"]))
    axes[0].annotate(
        f"峰值 {float(rows[peak_index]['gmv']) / 1_000_000:.2f}百万",
        xy=(months[peak_index], float(rows[peak_index]["gmv"]) / 1_000_000),
        xytext=(8, 12),
        textcoords="offset points",
        fontsize=9,
        color="#1D4ED8",
    )

    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    axes[-1].tick_params(axis="x", rotation=35)
    fig.text(
        0.08,
        0.015,
        "数据范围：2017-01至2018-08完整月份；GMV为有效订单商品金额，不含运费。",
        fontsize=9,
        color="#4B5563",
    )
    fig.tight_layout(rect=(0.04, 0.04, 0.98, 0.96))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _plot_yoy_growth(
    rows: list[dict[str, Any]], summary: dict[str, Any], output_path: Path
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    _configure_chinese_font()
    rows_2018 = [row for row in rows if row["purchase_month"].year == 2018]
    labels = [row["purchase_month"].strftime("%m月") for row in rows_2018]
    gmv_yoy = [float(row["gmv_yoy_growth"]) for row in rows_2018]
    order_yoy = [float(row["order_yoy_growth"]) for row in rows_2018]
    aov_yoy = [float(row["aov_yoy_growth"]) for row in rows_2018]

    fig = plt.figure(figsize=(13, 7))
    grid = fig.add_gridspec(
        2,
        2,
        width_ratios=[2.3, 1],
        height_ratios=[2, 1],
        hspace=0.34,
        wspace=0.16,
    )
    monthly_axis = fig.add_subplot(grid[0, 0])
    aov_axis = fig.add_subplot(grid[1, 0])
    cumulative_axis = fig.add_subplot(grid[:, 1])
    fig.suptitle("2018年1至8月同比增长", fontsize=16, fontweight="bold", x=0.06, ha="left")

    monthly_axis.plot(labels, gmv_yoy, marker="o", linewidth=2.2, color="#2563EB", label="GMV")
    monthly_axis.plot(labels, order_yoy, marker="o", linewidth=2.2, color="#0F766E", label="订单量")
    monthly_axis.axhline(0, color="#6B7280", linewidth=0.8)
    monthly_axis.yaxis.set_major_formatter(PercentFormatter(1.0))
    monthly_axis.grid(axis="y", color="#D1D5DB", linewidth=0.7, alpha=0.7)
    monthly_axis.spines[["top", "right", "left"]].set_visible(False)
    monthly_axis.tick_params(axis="y", length=0)
    monthly_axis.legend(frameon=False, ncol=2, loc="upper right")
    monthly_axis.set_title("GMV与订单量逐月同比", loc="left", fontsize=11, fontweight="bold")

    aov_axis.plot(labels, aov_yoy, marker="o", linewidth=2.2, color="#D97706", label="客单价")
    aov_axis.axhline(0, color="#6B7280", linewidth=0.8)
    aov_axis.yaxis.set_major_formatter(PercentFormatter(1.0))
    aov_axis.grid(axis="y", color="#D1D5DB", linewidth=0.7, alpha=0.7)
    aov_axis.spines[["top", "right", "left"]].set_visible(False)
    aov_axis.tick_params(axis="y", length=0)
    aov_axis.set_title("客单价逐月同比", loc="left", fontsize=11, fontweight="bold")

    comparison_labels = ["GMV", "订单量", "客单价"]
    comparison_values = [
        summary["ytd_gmv_growth"],
        summary["ytd_order_growth"],
        summary["ytd_aov_growth"],
    ]
    colors = ["#2563EB", "#0F766E", "#D97706"]
    bars = cumulative_axis.bar(comparison_labels, comparison_values, color=colors, width=0.62)
    cumulative_axis.axhline(0, color="#6B7280", linewidth=0.8)
    cumulative_axis.yaxis.set_major_formatter(PercentFormatter(1.0))
    cumulative_axis.grid(axis="y", color="#D1D5DB", linewidth=0.7, alpha=0.7)
    cumulative_axis.spines[["top", "right", "left"]].set_visible(False)
    cumulative_axis.tick_params(axis="y", length=0)
    cumulative_axis.set_title("1至8月累计同比", loc="left", fontsize=11, fontweight="bold")
    cumulative_axis.bar_label(
        bars, labels=[f"{value:.1%}" for value in comparison_values], padding=4
    )

    fig.text(
        0.06,
        0.015,
        "2017年同期基数较低，尤其是1月；逐月同比需要结合基数解读。",
        fontsize=9,
        color="#4B5563",
    )
    fig.subplots_adjust(left=0.07, right=0.98, bottom=0.13, top=0.86)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _pct(value: float | None) -> str:
    return "n.a." if value is None else f"{value:.1%}"


def _write_report(rows: list[dict[str, Any]], summary: dict[str, Any], report_path: Path) -> None:
    ytd_2017 = summary["ytd_2017"]
    ytd_2018 = summary["ytd_2018"]
    rows_2018 = [row for row in rows if row["purchase_month"].year == 2018]
    first_2018 = rows_2018[0]
    last_2018 = rows_2018[-1]
    minimum_aov_yoy = min(float(row["aov_yoy_growth"]) for row in rows_2018)
    maximum_aov_yoy = max(float(row["aov_yoy_growth"]) for row in rows_2018)
    lines = [
        "# 月度经营分析",
        "",
        "## 结论摘要",
        "",
        (
            f"2018年1至8月GMV为 {ytd_2018['gmv']:,.2f}，较2017年同期增长 "
            f"{summary['ytd_gmv_growth']:.1%}。有效订单量增长 "
            f"{summary['ytd_order_growth']:.1%}，客单价变化 "
            f"{summary['ytd_aov_growth']:.1%}。增长主要来自订单规模扩大。"
        ),
        "",
        (
            f"逐月GMV同比从2018年1月的 {float(first_2018['gmv_yoy_growth']):.1%} "
            f"回落至8月的 {float(last_2018['gmv_yoy_growth']):.1%}，8月订单量仍同比增长 "
            f"{float(last_2018['order_yoy_growth']):.1%}。增速回落主要需要结合2017年低基数解释，"
            "不能等同于经营规模下降。"
        ),
        "",
        (
            f"2018年各月客单价同比介于 {minimum_aov_yoy:.1%} 至 {maximum_aov_yoy:.1%}，"
            f"1至8月累计仅增长 {summary['ytd_aov_growth']:.1%}。单看客单价，尚无持续提价的证据；"
            "商品结构是否变化需要下一步按品类拆解。"
        ),
        "",
        (
            f"完整分析期的GMV峰值出现在 {summary['peak_month']:%Y-%m}，达到 "
            f"{summary['peak_gmv']:,.2f}，对应 {summary['peak_orders']:,} 笔有效订单。"
        ),
        "",
        (
            f"最大环比增长出现在 {summary['largest_mom_increase_month']:%Y-%m}，GMV增长 "
            f"{summary['largest_mom_increase']:.1%}；最大环比下降出现在 "
            f"{summary['largest_mom_decline_month']:%Y-%m}，GMV下降 "
            f"{abs(summary['largest_mom_decline']):.1%}。大幅变化需要结合前月基数和季节性解释。"
        ),
        "",
        "![月度经营趋势](figures/business_overview_trends.png)",
        "",
        "![同比增长](figures/business_overview_yoy.png)",
        "",
        "## 同期累计比较",
        "",
        "| 期间 | GMV | 有效订单 | 客单价 |",
        "|---|---:|---:|---:|",
        f"| 2017年1至8月 | {ytd_2017['gmv']:,.2f} | {ytd_2017['orders']:,.0f} | {ytd_2017['aov']:.2f} |",
        f"| 2018年1至8月 | {ytd_2018['gmv']:,.2f} | {ytd_2018['orders']:,.0f} | {ytd_2018['aov']:.2f} |",
        (
            f"| 同比 | {summary['ytd_gmv_growth']:.1%} | "
            f"{summary['ytd_order_growth']:.1%} | {summary['ytd_aov_growth']:.1%} |"
        ),
        "",
        "## 月度指标",
        "",
        "| 月份 | GMV | 有效订单 | 客单价 | GMV环比 | GMV同比 | 订单同比 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['purchase_month']:%Y-%m} | {float(row['gmv']):,.2f} | "
            f"{int(row['order_count']):,} | {float(row['average_order_value']):.2f} | "
            f"{_pct(row['gmv_mom_growth'])} | {_pct(row['gmv_yoy_growth'])} | "
            f"{_pct(row['order_yoy_growth'])} |"
        )
    lines.extend(
        [
            "",
            "## 解读边界",
            "",
            "- 趋势分析仅使用2017年1月至2018年8月的完整月份。",
            "- GMV为有效订单商品金额，不含运费，不代表平台收入或利润。",
            "- 2018年初同比增幅受到2017年同期低基数影响，不能直接外推长期增速。",
            "- 2017年11月的峰值与购物旺季时间一致，但仅凭订单数据不能证明促销活动是原因。",
            "- 下一步需要按品类、地区和商家拆解增长贡献，验证增长来源是否集中。",
            "",
            "数据来源：[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)。",
            "",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def run_business_overview(
    db_path: Path,
    report_path: Path,
    generated_dir: Path,
    figure_dir: Path,
) -> dict[str, Any]:
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError('尚未安装 DuckDB，请运行：python -m pip install -e ".[dev]"') from exc

    connection = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = load_monthly_metrics(connection)
        verify_monthly_metrics(connection, rows)
    finally:
        connection.close()

    summary = summarize_monthly_metrics(rows)
    _write_csv(rows, generated_dir / "monthly_metrics.csv")
    (generated_dir / "business_overview_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    _plot_monthly_trends(rows, figure_dir / "business_overview_trends.png")
    _plot_yoy_growth(rows, summary, figure_dir / "business_overview_yoy.png")
    _write_report(rows, summary, report_path)
    return summary
