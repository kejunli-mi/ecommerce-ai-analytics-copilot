from __future__ import annotations

import csv
import json
import math
from datetime import date
from pathlib import Path
from typing import Any

from ecommerce_copilot.settings import PROJECT_ROOT

ANALYSIS_END_MONTH = date(2018, 8, 1)


def _query_all(connection: Any, sql_name: str) -> list[dict[str, Any]]:
    sql_path = PROJECT_ROOT / "sql" / "analysis" / sql_name
    cursor = connection.execute(sql_path.read_text(encoding="utf-8"))
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        raise ValueError(f"无法写入空数据：{path.name}")
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


def _correlation(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    xs = [pair[0] for pair in pairs]
    ys = [pair[1] for pair in pairs]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    denominator = math.sqrt(
        sum((x - mean_x) ** 2 for x in xs) * sum((y - mean_y) ** 2 for y in ys)
    )
    return None if denominator == 0 else numerator / denominator


def summarize_regions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("地区指标为空")
    total_2017 = sum(float(row["gmv_2017"]) for row in rows)
    total_2018 = sum(float(row["gmv_2018"]) for row in rows)
    change = total_2018 - total_2017
    contributors = sorted(rows, key=lambda row: float(row["gmv_change"]), reverse=True)
    service_rows = [
        row
        for row in rows
        if int(row["delivered_orders"]) >= 100
        and row["late_delivery_rate"] is not None
        and row["avg_review_score"] is not None
    ]
    if not service_rows:
        raise ValueError("没有满足样本量门槛的地区履约数据")
    return {
        "state_count": len(rows),
        "total_gmv_2017": total_2017,
        "total_gmv_2018": total_2018,
        "gmv_growth_rate": total_2018 / total_2017 - 1,
        "top_contributors": contributors[:10],
        "top_five_growth_contribution": sum(
            float(row["gmv_change"]) for row in contributors[:5]
        )
        / change,
        "highest_late_states": sorted(
            service_rows, key=lambda row: float(row["late_delivery_rate"]), reverse=True
        )[:5],
        "lowest_review_states": sorted(
            service_rows, key=lambda row: float(row["avg_review_score"])
        )[:5],
        "late_review_correlation": _correlation(
            [
                (float(row["late_delivery_rate"]), float(row["avg_review_score"]))
                for row in service_rows
            ]
        ),
        "service_state_count": len(service_rows),
    }


def summarize_sellers(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("商家指标为空")
    total_gmv = sum(float(row["gmv"]) for row in rows)
    shares = [float(row["gmv_share"]) for row in rows]
    qualified = [
        row
        for row in rows
        if int(row["order_count"]) >= 100
        and row["late_delivery_rate"] is not None
        and row["avg_review_score"] is not None
    ]
    return {
        "seller_count": len(rows),
        "total_gmv": total_gmv,
        "top_sellers": rows[:15],
        "top_10_share": sum(shares[:10]),
        "top_20_share": sum(shares[:20]),
        "top_100_share": sum(shares[:100]),
        "hhi": sum(share**2 for share in shares),
        "qualified_seller_count": len(qualified),
        "highest_late_sellers": sorted(
            qualified, key=lambda row: float(row["late_delivery_rate"]), reverse=True
        )[:5],
        "lowest_review_sellers": sorted(
            qualified, key=lambda row: float(row["avg_review_score"])
        )[:5],
        "late_review_correlation": _correlation(
            [
                (float(row["late_delivery_rate"]), float(row["avg_review_score"]))
                for row in qualified
            ]
        ),
    }


def _weighted_retention(cohort_rows: list[dict[str, Any]], month_number: int) -> float:
    cohort_sizes = {
        row["cohort_month"]: int(row["cohort_size"])
        for row in cohort_rows
        if int(row["month_number"]) == 0
    }
    eligible = {
        cohort: size
        for cohort, size in cohort_sizes.items()
        if (ANALYSIS_END_MONTH.year - cohort.year) * 12
        + ANALYSIS_END_MONTH.month
        - cohort.month
        >= month_number
    }
    retained = {
        row["cohort_month"]: int(row["retained_users"])
        for row in cohort_rows
        if int(row["month_number"]) == month_number
    }
    denominator = sum(eligible.values())
    if denominator == 0:
        raise ValueError(f"没有可用于M{month_number}留存的成熟队列")
    return sum(retained.get(cohort, 0) for cohort in eligible) / denominator


def summarize_customers(
    segment_rows: list[dict[str, Any]], cohort_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    if not segment_rows or not cohort_rows:
        raise ValueError("用户分层或队列指标为空")
    by_segment = {str(row["customer_segment"]): row for row in segment_rows}
    repeat_rows = [
        by_segment[name]
        for name in ("active_repeat", "at_risk_repeat")
        if name in by_segment
    ]
    total_users = sum(int(row["users"]) for row in segment_rows)
    total_gmv = sum(float(row["gmv"]) for row in segment_rows)
    repeat_users = sum(int(row["users"]) for row in repeat_rows)
    repeat_gmv = sum(float(row["gmv"]) for row in repeat_rows)
    return {
        "total_users": total_users,
        "total_gmv": total_gmv,
        "repeat_users": repeat_users,
        "repeat_rate": repeat_users / total_users,
        "repeat_gmv_share": repeat_gmv / total_gmv,
        "segment_rows": segment_rows,
        "m1_retention": _weighted_retention(cohort_rows, 1),
        "m3_retention": _weighted_retention(cohort_rows, 3),
        "m6_retention": _weighted_retention(cohort_rows, 6),
        "cohort_count": len(
            {row["cohort_month"] for row in cohort_rows if int(row["month_number"]) == 0}
        ),
    }


def verify_region_rows(connection: Any, rows: list[dict[str, Any]]) -> None:
    direct = connection.execute(
        """
        SELECT
            ROUND(SUM(gmv) FILTER (
                WHERE order_purchase_timestamp >= TIMESTAMP '2017-01-01'
                  AND order_purchase_timestamp < TIMESTAMP '2017-09-01'
            ), 2),
            ROUND(SUM(gmv) FILTER (
                WHERE order_purchase_timestamp >= TIMESTAMP '2018-01-01'
                  AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
            ), 2),
            COUNT(*) FILTER (
                WHERE order_purchase_timestamp >= TIMESTAMP '2017-01-01'
                  AND order_purchase_timestamp < TIMESTAMP '2017-09-01'
            ),
            COUNT(*) FILTER (
                WHERE order_purchase_timestamp >= TIMESTAMP '2018-01-01'
                  AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
            )
        FROM analytics.orders
        WHERE is_effective_order
          AND order_purchase_timestamp >= TIMESTAMP '2017-01-01'
          AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
        """
    ).fetchone()
    actual = (
        round(sum(float(row["gmv_2017"]) for row in rows), 2),
        round(sum(float(row["gmv_2018"]) for row in rows), 2),
        sum(int(row["orders_2017"]) for row in rows),
        sum(int(row["orders_2018"]) for row in rows),
    )
    expected = (float(direct[0]), float(direct[1]), int(direct[2]), int(direct[3]))
    if actual != expected:
        raise AssertionError("地区汇总与订单宽表总计不一致")


def verify_seller_rows(connection: Any, rows: list[dict[str, Any]]) -> None:
    direct = connection.execute(
        """
        SELECT ROUND(SUM(price), 2)
        FROM analytics.order_items
        WHERE is_effective_order
          AND order_purchase_timestamp >= TIMESTAMP '2017-01-01'
          AND order_purchase_timestamp < TIMESTAMP '2018-09-01'
        """
    ).fetchone()[0]
    actual = round(sum(float(row["gmv"]) for row in rows), 2)
    if actual != float(direct):
        raise AssertionError("商家GMV汇总与订单明细总计不一致")
    if abs(sum(float(row["gmv_share"]) for row in rows) - 1) > 0.001:
        raise AssertionError("商家GMV份额合计不为100%")


def _plot_regions(rows: list[dict[str, Any]], output_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    _configure_chinese_font()
    contributors = sorted(rows, key=lambda row: float(row["gmv_change"]), reverse=True)[:10]
    bar_rows = list(reversed(contributors))
    service_rows = [
        row
        for row in rows
        if int(row["delivered_orders"]) >= 100
        and row["late_delivery_rate"] is not None
        and row["avg_review_score"] is not None
    ]
    fig, axes = plt.subplots(1, 2, figsize=(14, 6.8), gridspec_kw={"width_ratios": [1, 1.15]})
    bars = axes[0].barh(
        [str(row["customer_state"]) for row in bar_rows],
        [float(row["gmv_change"]) / 1_000_000 for row in bar_rows],
        color="#2563EB",
    )
    axes[0].set_title("GMV增量贡献最大的州", loc="left", fontweight="bold")
    axes[0].set_xlabel("GMV增量（百万）")
    axes[0].grid(axis="x", color="#D1D5DB", linewidth=0.7)
    axes[0].spines[["top", "right", "left"]].set_visible(False)
    axes[0].tick_params(axis="y", length=0)
    axes[0].bar_label(
        bars,
        labels=[f"{float(row['growth_contribution']):.1%}" for row in bar_rows],
        padding=3,
        fontsize=8,
    )

    x = [float(row["late_delivery_rate"]) for row in service_rows]
    y = [float(row["avg_review_score"]) for row in service_rows]
    sizes = [max(35, math.sqrt(int(row["delivered_orders"])) * 6) for row in service_rows]
    axes[1].scatter(x, y, s=sizes, color="#0F766E", alpha=0.68, edgecolor="white")
    label_states = {
        str(row["customer_state"])
        for row in sorted(
            service_rows, key=lambda row: float(row["late_delivery_rate"]), reverse=True
        )[:8]
    } | {"SP", "RJ", "MG"}
    for row in service_rows:
        if str(row["customer_state"]) in label_states:
            axes[1].annotate(
                str(row["customer_state"]),
                (float(row["late_delivery_rate"]), float(row["avg_review_score"])),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=8,
            )
    axes[1].set_title("各州延迟率与平均评分", loc="left", fontweight="bold")
    axes[1].set_xlabel("延迟配送率")
    axes[1].set_ylabel("平均评分")
    axes[1].xaxis.set_major_formatter(PercentFormatter(1.0))
    axes[1].grid(color="#D1D5DB", linewidth=0.7, alpha=0.7)
    axes[1].spines[["top", "right"]].set_visible(False)
    fig.suptitle("地区增长与履约体验", x=0.055, ha="left", fontsize=16, fontweight="bold")
    fig.text(
        0.055,
        0.015,
        "增长使用2017/2018年1至8月同期；履约散点仅展示至少100笔已送达订单的州，气泡大小代表订单量。",
        fontsize=9,
        color="#4B5563",
    )
    fig.tight_layout(rect=(0.03, 0.05, 0.99, 0.94))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _plot_sellers(rows: list[dict[str, Any]], output_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    _configure_chinese_font()
    top = rows[:15]
    bar_rows = list(reversed(top))
    fig, axes = plt.subplots(1, 2, figsize=(14, 6.8), gridspec_kw={"width_ratios": [1.05, 1]})
    axes[0].barh(
        [str(row["seller_id"])[:8] for row in bar_rows],
        [float(row["gmv"]) / 1_000 for row in bar_rows],
        color="#2563EB",
    )
    axes[0].set_title("头部商家GMV", loc="left", fontweight="bold")
    axes[0].set_xlabel("GMV（千）")
    axes[0].grid(axis="x", color="#D1D5DB", linewidth=0.7)
    axes[0].spines[["top", "right", "left"]].set_visible(False)
    axes[0].tick_params(axis="y", length=0)

    ranks = [int(row["gmv_rank"]) for row in rows]
    cumulative = [float(row["cumulative_gmv_share"]) for row in rows]
    axes[1].plot(ranks, cumulative, color="#0F766E", linewidth=2.2)
    axes[1].set_xscale("log")
    axes[1].set_ylim(0, 1.02)
    axes[1].yaxis.set_major_formatter(PercentFormatter(1.0))
    axes[1].set_xlabel("商家数（对数坐标）")
    axes[1].set_ylabel("累计GMV份额")
    axes[1].set_title("商家GMV集中度", loc="left", fontweight="bold")
    axes[1].grid(color="#D1D5DB", linewidth=0.7, alpha=0.7)
    axes[1].spines[["top", "right"]].set_visible(False)
    for rank in (10, 100, 500):
        if rank <= len(rows):
            share = float(rows[rank - 1]["cumulative_gmv_share"])
            axes[1].scatter([rank], [share], color="#D97706", zorder=3)
            axes[1].annotate(
                f"Top {rank}: {share:.1%}",
                (rank, share),
                xytext=(5, -14),
                textcoords="offset points",
                fontsize=8,
            )
    fig.suptitle("商家规模与集中度", x=0.055, ha="left", fontsize=16, fontweight="bold")
    fig.text(
        0.055,
        0.015,
        "分析期：2017-01至2018-08；商家标签显示seller_id前8位。",
        fontsize=9,
        color="#4B5563",
    )
    fig.tight_layout(rect=(0.03, 0.05, 0.99, 0.94))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _plot_customers(
    segment_rows: list[dict[str, Any]], cohort_rows: list[dict[str, Any]], output_path: Path
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.ticker import PercentFormatter

    _configure_chinese_font()
    segment_labels = {
        "active_repeat": "活跃复购",
        "at_risk_repeat": "沉睡复购",
        "recent_one_time": "近期首购",
        "dormant_one_time": "沉睡一次性",
    }
    cohorts = sorted(
        {row["cohort_month"] for row in cohort_rows if int(row["month_number"]) == 0}
    )
    matrix = np.full((len(cohorts), 6), np.nan)
    lookup = {
        (row["cohort_month"], int(row["month_number"])): float(row["retention_rate"])
        for row in cohort_rows
    }
    for row_index, cohort in enumerate(cohorts):
        observable_age = (
            (ANALYSIS_END_MONTH.year - cohort.year) * 12
            + ANALYSIS_END_MONTH.month
            - cohort.month
        )
        for month_number in range(1, 7):
            if month_number <= observable_age:
                matrix[row_index, month_number - 1] = lookup.get((cohort, month_number), 0.0)

    fig, axes = plt.subplots(1, 2, figsize=(14, 7.5), gridspec_kw={"width_ratios": [1.4, 1]})
    image = axes[0].imshow(matrix, aspect="auto", cmap="Blues", vmin=0, vmax=0.012)
    axes[0].set_xticks(range(6), [f"M{i}" for i in range(1, 7)])
    axes[0].set_yticks(range(len(cohorts)), [cohort.strftime("%Y-%m") for cohort in cohorts])
    axes[0].set_title("首购队列后续购买率", loc="left", fontweight="bold")
    for i in range(len(cohorts)):
        for j in range(6):
            if not math.isnan(matrix[i, j]):
                axes[0].text(
                    j,
                    i,
                    f"{matrix[i, j]:.1%}",
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="white" if matrix[i, j] >= 0.007 else "#1F2937",
                )
    colorbar = fig.colorbar(image, ax=axes[0], fraction=0.03, pad=0.02)
    colorbar.ax.yaxis.set_major_formatter(PercentFormatter(1.0))

    ordered_segments = sorted(segment_rows, key=lambda row: float(row["user_share"]), reverse=True)
    positions = list(range(len(ordered_segments)))
    width = 0.36
    axes[1].bar(
        [position - width / 2 for position in positions],
        [float(row["user_share"]) for row in ordered_segments],
        width=width,
        color="#2563EB",
        label="用户占比",
    )
    axes[1].bar(
        [position + width / 2 for position in positions],
        [float(row["gmv_share"]) for row in ordered_segments],
        width=width,
        color="#0F766E",
        label="GMV占比",
    )
    axes[1].set_xticks(
        positions,
        [segment_labels[str(row["customer_segment"])] for row in ordered_segments],
        rotation=25,
        ha="right",
    )
    axes[1].yaxis.set_major_formatter(PercentFormatter(1.0))
    axes[1].set_ylim(0, 1)
    axes[1].grid(axis="y", color="#D1D5DB", linewidth=0.7)
    axes[1].spines[["top", "right", "left"]].set_visible(False)
    axes[1].tick_params(axis="y", length=0)
    axes[1].legend(frameon=False, loc="upper right")
    axes[1].set_title("用户分层结构", loc="left", fontweight="bold")
    fig.suptitle("用户复购与队列留存", x=0.055, ha="left", fontsize=16, fontweight="bold")
    fig.text(
        0.055,
        0.015,
        "M1表示首购后第1个月再次购买；空白表示观察窗口尚未到达，非0%。",
        fontsize=9,
        color="#4B5563",
    )
    fig.tight_layout(rect=(0.03, 0.05, 0.99, 0.94))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _pct(value: Any) -> str:
    return "n.a." if value is None else f"{float(value):.1%}"


def _write_region_report(
    rows: list[dict[str, Any]], summary: dict[str, Any], report_path: Path
) -> None:
    top = summary["top_contributors"]
    late = summary["highest_late_states"]
    correlation = summary["late_review_correlation"]
    lines = [
        "# 地区增长与履约分析",
        "",
        "## 结论摘要",
        "",
        (
            f"2018年1至8月同比增长中，{top[0]['customer_state']}州贡献净增量的 "
            f"{float(top[0]['growth_contribution']):.1%}，前五个州合计贡献 "
            f"{summary['top_five_growth_contribution']:.1%}。地区增长较为集中。"
        ),
        "",
        (
            f"在至少100笔已送达订单的州中，{late[0]['customer_state']}的延迟率最高，"
            f"为 {float(late[0]['late_delivery_rate']):.1%}，平均评分 "
            f"{float(late[0]['avg_review_score']):.2f}。"
        ),
        "",
        (
            f"各州延迟率与平均评分的相关系数为 {correlation:.2f}。"
            "负相关表明延迟较高的州通常评分较低，但不能单独证明因果。"
        ),
        "",
        "![地区增长与履约](figures/region_growth_service.png)",
        "",
        "## 地区增长贡献前10名",
        "",
        "| 州 | 2017年GMV | 2018年GMV | GMV增量 | 增长贡献 | 订单同比 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in top:
        lines.append(
            f"| {row['customer_state']} | {float(row['gmv_2017']):,.2f} | "
            f"{float(row['gmv_2018']):,.2f} | {float(row['gmv_change']):,.2f} | "
            f"{_pct(row['growth_contribution'])} | {_pct(row['order_growth_rate'])} |"
        )
    lines.extend(
        [
            "",
            "## 履约风险较高的州",
            "",
            "| 州 | 已送达订单 | 延迟率 | 平均配送天数 | 平均评分 | 低评率 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in late:
        lines.append(
            f"| {row['customer_state']} | {int(row['delivered_orders']):,} | "
            f"{_pct(row['late_delivery_rate'])} | {float(row['avg_delivery_days']):.1f} | "
            f"{float(row['avg_review_score']):.2f} | {_pct(row['low_review_rate'])} |"
        )
    lines.extend(
        [
            "",
            "## 建议",
            "",
            "- 优先将履约改进资源放在订单规模大且延迟率高的州，而不是只看延迟率排名。",
            "- 将州级问题继续拆到商家和品类，区分是物流距离、卖家发货还是商品结构驱动。",
            "",
            "## 口径与边界",
            "",
            "- 增长使用2017年与2018年1至8月同期；履约使用2017-01至2018-08完整分析期。",
            "- 延迟率仅在有预计和实际送达日期的已送达订单中计算。",
            "- 相关性不代表因果；地区间商品、商家和距离结构不同。",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")


def _write_seller_report(
    rows: list[dict[str, Any]], summary: dict[str, Any], report_path: Path
) -> None:
    top = summary["top_sellers"][:10]
    risks = summary["highest_late_sellers"]
    correlation = summary["late_review_correlation"]
    lines = [
        "# 商家规模与履约分析",
        "",
        "## 结论摘要",
        "",
        (
            f"分析期内共有 {summary['seller_count']:,} 家活跃商家。Top 10商家贡献 "
            f"{summary['top_10_share']:.1%} 的GMV，Top 100贡献 {summary['top_100_share']:.1%}。"
        ),
        "",
        (
            f"商家GMV的HHI为 {summary['hhi']:.4f}，头部依赖风险较低，但长尾商家管理成本较高。"
        ),
        "",
        (
            f"在至少100笔订单的商家中，延迟率与平均评分的相关系数为 "
            f"{correlation:.2f}，可作为履约治理的优先级线索。"
        ),
        "",
        "![商家规模与集中度](figures/seller_concentration.png)",
        "",
        "## GMV前10名商家",
        "",
        "| 商家ID | 州 | GMV | 订单 | GMV份额 | 延迟率 | 平均评分 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in top:
        lines.append(
            f"| {row['seller_id']} | {row['seller_state']} | {float(row['gmv']):,.2f} | "
            f"{int(row['order_count']):,} | {_pct(row['gmv_share'])} | "
            f"{_pct(row['late_delivery_rate'])} | {float(row['avg_review_score']):.2f} |"
        )
    lines.extend(
        [
            "",
            "## 规模商家中的履约风险",
            "",
            "| 商家ID | 订单 | GMV | 延迟率 | 平均评分 | 低评率 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in risks:
        lines.append(
            f"| {row['seller_id']} | {int(row['order_count']):,} | {float(row['gmv']):,.2f} | "
            f"{_pct(row['late_delivery_rate'])} | {float(row['avg_review_score']):.2f} | "
            f"{_pct(row['low_review_rate'])} |"
        )
    lines.extend(
        [
            "",
            "## 建议",
            "",
            "- 对高GMV、高延迟、低评分商家设置联合预警，优先治理对用户体验影响最大的部分。",
            "- 平台不存在单一头部商家过度依赖，运营机制应更关注长尾商家的准入、分层和履约质量。",
            "",
            "## 口径与边界",
            "",
            "- 同一订单可包含多个商家，商家订单数不能直接加总为全站订单数。",
            "- 商家履约指标在seller_id + order_id去重后计算，避免多商品明细放大订单。",
            "- HHI基于商家GMV份额平方和，只反映本数据集中的销售集中度。",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")


def _write_customer_report(
    segment_rows: list[dict[str, Any]], summary: dict[str, Any], report_path: Path
) -> None:
    labels = {
        "active_repeat": "活跃复购",
        "at_risk_repeat": "沉睡复购",
        "recent_one_time": "近期首购",
        "dormant_one_time": "沉睡一次性",
    }
    lines = [
        "# 用户复购、队列留存与分层",
        "",
        "## 结论摘要",
        "",
        (
            f"截止2018年8月，共有 {summary['total_users']:,} 位有效购买用户，"
            f"其中 {summary['repeat_users']:,} 人完成至少两笔有效订单，复购率为 "
            f"{summary['repeat_rate']:.1%}。复购用户贡献 {summary['repeat_gmv_share']:.1%} 的GMV。"
        ),
        "",
        (
            f"按成熟队列加权，M1、M3和M6留存分别为 {summary['m1_retention']:.2%}、"
            f"{summary['m3_retention']:.2%} 和 {summary['m6_retention']:.2%}。用户结构以一次性购买为主。"
        ),
        "",
        "![用户复购与队列留存](figures/customer_retention_segments.png)",
        "",
        "## 用户分层",
        "",
        "| 用户分层 | 用户数 | 用户占比 | GMV | GMV占比 | 人均GMV | 平均距上次购买 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in segment_rows:
        lines.append(
            f"| {labels[str(row['customer_segment'])]} | {int(row['users']):,} | "
            f"{_pct(row['user_share'])} | {float(row['gmv']):,.2f} | "
            f"{_pct(row['gmv_share'])} | {float(row['avg_customer_gmv']):.2f} | "
            f"{float(row['avg_recency_days']):.0f}天 |"
        )
    lines.extend(
        [
            "",
            "## 建议",
            "",
            "- 将复购提升作为用户经营主题，优先测试首购后30天内的跨品类召回和二购激励。",
            "- 对活跃复购用户保持服务体验；对沉睡复购用户进行召回，两类用户不应使用同一触达策略。",
            "- 建议增加曝光、点击、优惠券和触达数据，再评估召回转化与投入产出。",
            "",
            "## 口径与边界",
            "",
            "- 跨订单用户识别使用customer_unique_id，不使用订单级customer_id。",
            "- 队列留存表示在首购后指定月份再次购买的用户比例，不是连续订阅留存。",
            "- 队列的空白月表示尚未到达观察窗口，不能按0%处理。",
            "- 用户分层是可解释的规则分层，不是预测模型。",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")


def run_advanced_analyses(
    db_path: Path,
    report_dir: Path,
    generated_dir: Path,
    figure_dir: Path,
) -> dict[str, Any]:
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError('尚未安装 DuckDB，请运行：python -m pip install -e ".[dev]"') from exc

    connection = duckdb.connect(str(db_path), read_only=True)
    try:
        region_rows = _query_all(connection, "region_performance.sql")
        seller_rows = _query_all(connection, "seller_performance.sql")
        segment_rows = _query_all(connection, "customer_segments.sql")
        cohort_rows = _query_all(connection, "customer_cohort.sql")
        verify_region_rows(connection, region_rows)
        verify_seller_rows(connection, seller_rows)
    finally:
        connection.close()

    region_summary = summarize_regions(region_rows)
    seller_summary = summarize_sellers(seller_rows)
    customer_summary = summarize_customers(segment_rows, cohort_rows)

    generated_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(region_rows, generated_dir / "region_performance.csv")
    _write_csv(seller_rows, generated_dir / "seller_performance.csv")
    _write_csv(segment_rows, generated_dir / "customer_segments.csv")
    _write_csv(cohort_rows, generated_dir / "customer_cohort.csv")
    summaries = {
        "region": region_summary,
        "seller": seller_summary,
        "customer": customer_summary,
    }
    (generated_dir / "advanced_analysis_summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    _plot_regions(region_rows, figure_dir / "region_growth_service.png")
    _plot_sellers(seller_rows, figure_dir / "seller_concentration.png")
    _plot_customers(segment_rows, cohort_rows, figure_dir / "customer_retention_segments.png")
    _write_region_report(region_rows, region_summary, report_dir / "04_region_fulfillment.md")
    _write_seller_report(seller_rows, seller_summary, report_dir / "05_seller_performance.md")
    _write_customer_report(segment_rows, customer_summary, report_dir / "06_customer_retention.md")
    return summaries
