from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from ecommerce_copilot.settings import PROJECT_ROOT

BASELINE_GMV_THRESHOLD = 10_000.0


def _query_all(connection: Any, sql: str) -> list[dict[str, Any]]:
    cursor = connection.execute(sql)
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def load_category_metrics(connection: Any) -> list[dict[str, Any]]:
    sql_path = PROJECT_ROOT / "sql" / "analysis" / "category_growth.sql"
    return _query_all(connection, sql_path.read_text(encoding="utf-8"))


def summarize_category_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("品类指标为空")

    total_gmv_2017 = sum(float(row["gmv_2017"]) for row in rows)
    total_gmv_2018 = sum(float(row["gmv_2018"]) for row in rows)
    total_units_2017 = sum(int(row["units_2017"]) for row in rows)
    total_units_2018 = sum(int(row["units_2018"]) for row in rows)
    total_growth = total_gmv_2018 - total_gmv_2017
    if total_gmv_2017 <= 0 or total_growth == 0 or total_units_2017 <= 0:
        raise ValueError("品类汇总无法计算增长")

    contributors = sorted(
        (row for row in rows if float(row["gmv_change"]) > 0),
        key=lambda row: float(row["gmv_change"]),
        reverse=True,
    )
    decliners = sorted(rows, key=lambda row: float(row["gmv_change"]))
    decliners = [row for row in decliners if float(row["gmv_change"]) < 0]
    share_gainers = sorted(
        rows, key=lambda row: float(row["gmv_share_change"]), reverse=True
    )
    share_decliners = sorted(rows, key=lambda row: float(row["gmv_share_change"]))
    growth_rate_leaders = sorted(
        (
            row
            for row in rows
            if float(row["gmv_2017"]) >= BASELINE_GMV_THRESHOLD
            and row["gmv_growth_rate"] is not None
        ),
        key=lambda row: float(row["gmv_growth_rate"]),
        reverse=True,
    )
    largest_2018 = sorted(rows, key=lambda row: float(row["gmv_2018"]), reverse=True)

    return {
        "total_gmv_2017": total_gmv_2017,
        "total_gmv_2018": total_gmv_2018,
        "total_gmv_change": total_growth,
        "gmv_growth_rate": total_gmv_2018 / total_gmv_2017 - 1,
        "total_units_2017": total_units_2017,
        "total_units_2018": total_units_2018,
        "unit_growth_rate": total_units_2018 / total_units_2017 - 1,
        "average_item_price_2017": total_gmv_2017 / total_units_2017,
        "average_item_price_2018": total_gmv_2018 / total_units_2018,
        "top_contributors": contributors[:10],
        "decliners": decliners[:5],
        "growth_rate_leaders": growth_rate_leaders[:5],
        "largest_2018": largest_2018[:12],
        "largest_share_gain": share_gainers[0],
        "largest_share_decline": share_decliners[0],
        "top_five_growth_contribution": sum(
            float(row["gmv_change"]) for row in contributors[:5]
        )
        / total_growth,
        "top_ten_share_2017": sum(float(row["gmv_share_2017"]) for row in largest_2018[:10]),
        "top_ten_share_2018": sum(float(row["gmv_share_2018"]) for row in largest_2018[:10]),
        "category_count": len(rows),
        "baseline_gmv_threshold": BASELINE_GMV_THRESHOLD,
    }


def verify_category_metrics(connection: Any, rows: list[dict[str, Any]]) -> None:
    direct = connection.execute(
        """
        SELECT
            ROUND(SUM(price) FILTER (
                WHERE order_purchase_timestamp >= TIMESTAMP '2017-01-01'
                  AND order_purchase_timestamp < TIMESTAMP '2017-09-01'
            ), 2) AS gmv_2017,
            ROUND(SUM(price) FILTER (
                WHERE order_purchase_timestamp >= TIMESTAMP '2018-01-01'
                  AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
            ), 2) AS gmv_2018,
            COUNT(*) FILTER (
                WHERE order_purchase_timestamp >= TIMESTAMP '2017-01-01'
                  AND order_purchase_timestamp < TIMESTAMP '2017-09-01'
            ) AS units_2017,
            COUNT(*) FILTER (
                WHERE order_purchase_timestamp >= TIMESTAMP '2018-01-01'
                  AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
            ) AS units_2018
        FROM analytics.order_items
        WHERE is_effective_order
          AND order_purchase_timestamp >= TIMESTAMP '2017-01-01'
          AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
        """
    ).fetchone()
    category_totals = (
        round(sum(float(row["gmv_2017"]) for row in rows), 2),
        round(sum(float(row["gmv_2018"]) for row in rows), 2),
        sum(int(row["units_2017"]) for row in rows),
        sum(int(row["units_2018"]) for row in rows),
    )
    direct_totals = (float(direct[0]), float(direct[1]), int(direct[2]), int(direct[3]))
    if category_totals != direct_totals:
        raise AssertionError("品类汇总与订单明细总计不一致")

    share_2017 = sum(float(row["gmv_share_2017"]) for row in rows)
    share_2018 = sum(float(row["gmv_share_2018"]) for row in rows)
    if abs(share_2017 - 1) > 0.0001 or abs(share_2018 - 1) > 0.0001:
        raise AssertionError("品类GMV份额合计不为100%")


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


def _category_label(value: str) -> str:
    return "unknown" if value == "unknown_category" else value.replace("_", " ")


def _plot_growth_contribution(rows: list[dict[str, Any]], output_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    _configure_chinese_font()
    positives = sorted(
        (row for row in rows if float(row["gmv_change"]) > 0),
        key=lambda row: float(row["gmv_change"]),
        reverse=True,
    )[:12]
    plot_rows = list(reversed(positives))
    labels = [_category_label(str(row["product_category"])) for row in plot_rows]
    changes = [float(row["gmv_change"]) / 1_000_000 for row in plot_rows]
    contributions = [float(row["growth_contribution"]) for row in plot_rows]

    fig, axis = plt.subplots(figsize=(11.5, 7.2))
    bars = axis.barh(labels, changes, color="#2563EB", height=0.66)
    axis.set_title("2018年1至8月GMV增量最大的品类", loc="left", fontsize=15, fontweight="bold")
    axis.set_xlabel("GMV增量（百万）")
    axis.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.1f}"))
    axis.grid(axis="x", color="#D1D5DB", linewidth=0.7, alpha=0.7)
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.tick_params(axis="y", length=0)
    for bar, contribution in zip(bars, contributions, strict=True):
        axis.text(
            bar.get_width() + 0.006,
            bar.get_y() + bar.get_height() / 2,
            f"占净增量 {contribution:.1%}",
            va="center",
            fontsize=9,
            color="#374151",
        )
    axis.set_xlim(0, max(changes) * 1.38)
    fig.text(
        0.13,
        0.015,
        "增长贡献 = 品类GMV增量 ÷ 全站GMV净增量；可能因其他品类下降而超过100%。",
        fontsize=9,
        color="#4B5563",
    )
    fig.tight_layout(rect=(0.03, 0.05, 0.98, 0.98))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _plot_category_mix(rows: list[dict[str, Any]], output_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    _configure_chinese_font()
    largest = sorted(rows, key=lambda row: float(row["gmv_2018"]), reverse=True)[:12]
    plot_rows = list(reversed(largest))
    labels = [_category_label(str(row["product_category"])) for row in plot_rows]
    share_2017 = [float(row["gmv_share_2017"]) for row in plot_rows]
    share_2018 = [float(row["gmv_share_2018"]) for row in plot_rows]
    positions = list(range(len(plot_rows)))
    height = 0.34

    fig, axis = plt.subplots(figsize=(11.5, 7.2))
    axis.barh(
        [position - height / 2 for position in positions],
        share_2017,
        height=height,
        color="#9CA3AF",
        label="2017年1至8月",
    )
    axis.barh(
        [position + height / 2 for position in positions],
        share_2018,
        height=height,
        color="#0F766E",
        label="2018年1至8月",
    )
    axis.set_yticks(positions, labels)
    axis.set_title("头部品类GMV份额变化", loc="left", fontsize=15, fontweight="bold")
    axis.set_xlabel("全站GMV份额")
    axis.xaxis.set_major_formatter(PercentFormatter(1.0))
    axis.grid(axis="x", color="#D1D5DB", linewidth=0.7, alpha=0.7)
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.tick_params(axis="y", length=0)
    axis.legend(frameon=False, loc="lower right")
    fig.text(
        0.13,
        0.015,
        "双方均使用同期1至8月数据；排序依据为2018年GMV。",
        fontsize=9,
        color="#4B5563",
    )
    fig.tight_layout(rect=(0.03, 0.05, 0.98, 0.98))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _pct(value: Any) -> str:
    return "n.a." if value is None else f"{float(value):.1%}"


def _write_report(rows: list[dict[str, Any]], summary: dict[str, Any], report_path: Path) -> None:
    top = summary["top_contributors"]
    decliners = summary["decliners"]
    rate_leaders = summary["growth_rate_leaders"]
    share_gain = summary["largest_share_gain"]
    share_decline = summary["largest_share_decline"]
    average_price_growth = (
        summary["average_item_price_2018"] / summary["average_item_price_2017"] - 1
    )
    top_names = "、".join(_category_label(str(row["product_category"])) for row in top[:3])
    lines = [
        "# 品类增长贡献分析",
        "",
        "## 结论摘要",
        "",
        (
            f"2018年1至8月GMV较2017年同期增加 "
            f"{summary['total_gmv_change']:,.2f}，增长 {summary['gmv_growth_rate']:.1%}。"
            f"增量最大的三个品类是 {top_names}。"
        ),
        "",
        (
            f"前五个增长贡献品类合计贡献全站净增量的 "
            f"{summary['top_five_growth_contribution']:.1%}。"
            "该指标衡量增量集中度，并不等于2018年GMV份额。"
        ),
        "",
        (
            f"商品件数同比增长 {summary['unit_growth_rate']:.1%}，平均件单价变化 "
            f"{average_price_growth:.1%}。从总量看，GMV增长主要来自售出件数扩大，"
            "件单价变化较小。"
        ),
        "",
        (
            f"GMV份额提升最多的品类是 "
            f"{_category_label(str(share_gain['product_category']))}，提升 "
            f"{float(share_gain['gmv_share_change']):.1%}；份额下降最多的是 "
            f"{_category_label(str(share_decline['product_category']))}，下降 "
            f"{abs(float(share_decline['gmv_share_change'])):.1%}。"
        ),
        "",
        "![品类增长贡献](figures/category_growth_contribution.png)",
        "",
        "![品类份额变化](figures/category_mix_shift.png)",
        "",
        "## GMV增长贡献前10名",
        "",
        "| 品类 | 2017年GMV | 2018年GMV | GMV增量 | 同比 | 增长贡献 | 2018年份额 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in top:
        lines.append(
            f"| {_category_label(str(row['product_category']))} | "
            f"{float(row['gmv_2017']):,.2f} | {float(row['gmv_2018']):,.2f} | "
            f"{float(row['gmv_change']):,.2f} | {_pct(row['gmv_growth_rate'])} | "
            f"{_pct(row['growth_contribution'])} | {_pct(row['gmv_share_2018'])} |"
        )

    lines.extend(
        [
            "",
            f"## 高增长品类（2017年同期GMV不低于 {BASELINE_GMV_THRESHOLD:,.0f}）",
            "",
            "| 品类 | 2017年GMV | 2018年GMV | GMV同比 | 件数同比 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for row in rate_leaders:
        lines.append(
            f"| {_category_label(str(row['product_category']))} | "
            f"{float(row['gmv_2017']):,.2f} | {float(row['gmv_2018']):,.2f} | "
            f"{_pct(row['gmv_growth_rate'])} | {_pct(row['unit_growth_rate'])} |"
        )

    lines.extend(
        [
            "",
            "## GMV下降品类",
            "",
            "| 品类 | 2017年GMV | 2018年GMV | GMV变化 | 同比 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    if decliners:
        for row in decliners:
            lines.append(
                f"| {_category_label(str(row['product_category']))} | "
                f"{float(row['gmv_2017']):,.2f} | {float(row['gmv_2018']):,.2f} | "
                f"{float(row['gmv_change']):,.2f} | {_pct(row['gmv_growth_rate'])} |"
            )
    else:
        lines.append("| 无 | - | - | - | - |")

    lines.extend(
        [
            "",
            "## 口径与解读边界",
            "",
            "- 比较期间固定为2017年与2018年的1至8月，避免不完整月份干扰。",
            "- GMV为有效订单商品金额，不含运费，不代表平台收入或利润。",
            "- 增长贡献按净增量计算；如果存在下降品类，正增长品类贡献之和可能超过100%。",
            "- 一笔订单可含多个品类，各品类订单数不能直接加总为全站订单数。",
            "- 增速排名排除2017年同期GMV低于10,000的低基数品类。",
            "- 本章确定增长来源，但不能单独证明促销、供给或用户需求是因果驱动。",
            "",
            "数据来源：[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)。",
            "",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def run_category_growth(
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
        rows = load_category_metrics(connection)
        verify_category_metrics(connection, rows)
    finally:
        connection.close()

    summary = summarize_category_metrics(rows)
    _write_csv(rows, generated_dir / "category_growth.csv")
    (generated_dir / "category_growth_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    _plot_growth_contribution(rows, figure_dir / "category_growth_contribution.png")
    _plot_category_mix(rows, figure_dir / "category_mix_shift.png")
    _write_report(rows, summary, report_path)
    return summary
