from __future__ import annotations

import argparse
import json
from pathlib import Path

from ecommerce_copilot.analysis.advanced import run_advanced_analyses
from ecommerce_copilot.analysis.business_overview import run_business_overview
from ecommerce_copilot.analysis.category_growth import run_category_growth
from ecommerce_copilot.copilot import ask
from ecommerce_copilot.dashboard_export import export_dashboard_data
from ecommerce_copilot.evaluation import run_evaluation
from ecommerce_copilot.final_report import write_final_report
from ecommerce_copilot.quality import write_quality_report
from ecommerce_copilot.settings import PROJECT_ROOT, Settings
from ecommerce_copilot.validation import write_validation_report
from ecommerce_copilot.warehouse import build_warehouse


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="电商经营数据分析 Copilot 数据工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="检查原始 CSV 并生成质量报告")
    inspect_parser.add_argument("--data-dir", type=Path)
    inspect_parser.add_argument("--report-dir", type=Path)

    build_parser = subparsers.add_parser("build", help="导入 DuckDB 并创建分析视图")
    build_parser.add_argument("--data-dir", type=Path)
    build_parser.add_argument("--db-path", type=Path)

    validate_parser = subparsers.add_parser("validate", help="校验分析层粒度、外键和指标")
    validate_parser.add_argument("--db-path", type=Path)
    validate_parser.add_argument("--report-dir", type=Path)

    overview_parser = subparsers.add_parser(
        "analyze-overview", help="生成月度经营指标、图表和分析报告"
    )
    overview_parser.add_argument("--db-path", type=Path)

    category_parser = subparsers.add_parser(
        "analyze-category", help="生成品类增长贡献、份额变化图表和分析报告"
    )
    category_parser.add_argument("--db-path", type=Path)

    deep_dive_parser = subparsers.add_parser(
        "analyze-deep-dives", help="生成地区、商家和用户三个专题分析"
    )
    deep_dive_parser.add_argument("--db-path", type=Path)

    ask_parser = subparsers.add_parser("ask", help="使用可控语义层回答自然语言取数问题")
    ask_parser.add_argument("question")
    ask_parser.add_argument("--db-path", type=Path)

    evaluate_parser = subparsers.add_parser(
        "evaluate-copilot", help="运行50道问题的Copilot离线评测"
    )
    evaluate_parser.add_argument("--db-path", type=Path)

    dashboard_parser = subparsers.add_parser(
        "export-dashboard", help="导出零额外依赖的交互看板数据"
    )
    dashboard_parser.add_argument("--db-path", type=Path)

    run_all_parser = subparsers.add_parser(
        "run-all", help="生成所有分析、评测、看板数据和项目总报告"
    )
    run_all_parser.add_argument("--db-path", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings()

    if args.command == "inspect":
        data_dir = args.data_dir or settings.data_dir
        report_dir = args.report_dir or settings.report_dir
        profiles = write_quality_report(data_dir, report_dir)
        missing = [p["filename"] for p in profiles if p["required"] and not p["exists"]]
        print(f"质量报告已写入：{report_dir / 'data_quality.md'}")
        if missing:
            print(f"当前缺少 {len(missing)} 个必需文件，请将 Olist CSV 放入：{data_dir}")
            return 2
        print("必需数据文件完整，可以执行 build。")
        return 0

    if args.command == "build":
        data_dir = args.data_dir or settings.data_dir
        db_path = args.db_path or settings.db_path
        sql_path = PROJECT_ROOT / "sql" / "analytics" / "create_views.sql"
        try:
            loaded = build_warehouse(data_dir, db_path, sql_path)
        except (FileNotFoundError, RuntimeError) as exc:
            print(exc)
            return 2
        print(f"已导入 {len(loaded)} 张表：{', '.join(loaded)}")
        print(f"分析数据库已生成：{db_path}")
        return 0

    if args.command == "validate":
        db_path = args.db_path or settings.db_path
        report_dir = args.report_dir or settings.report_dir
        try:
            result = write_validation_report(db_path, report_dir)
        except (OSError, RuntimeError) as exc:
            print(exc)
            return 2
        print(f"数据库校验报告已写入：{report_dir / 'warehouse_validation.md'}")
        foreign_key_issues = sum(result["foreign_keys"].values())
        grain = result["grain"]
        grain_ok = (
            grain["raw_orders"] == grain["analytics_orders"]
            and grain["raw_order_items"] == grain["analytics_order_items"]
        )
        if foreign_key_issues or not grain_ok:
            print("发现影响分析可信度的粒度或外键问题，请先审阅报告。")
            return 1
        print("分析层粒度和外键检查通过。")
        return 0

    if args.command == "analyze-overview":
        db_path = args.db_path or settings.db_path
        report_path = PROJECT_ROOT / "reports" / "02_business_overview.md"
        figure_dir = PROJECT_ROOT / "reports" / "figures"
        try:
            summary = run_business_overview(
                db_path=db_path,
                report_path=report_path,
                generated_dir=settings.report_dir,
                figure_dir=figure_dir,
            )
        except (OSError, RuntimeError, AssertionError, ValueError) as exc:
            print(exc)
            return 2
        print(f"经营分析报告已生成：{report_path}")
        print(
            f"2018年1至8月GMV同比 {summary['ytd_gmv_growth']:.1%}，"
            f"订单量同比 {summary['ytd_order_growth']:.1%}，"
            f"客单价同比 {summary['ytd_aov_growth']:.1%}。"
        )
        return 0

    if args.command == "analyze-category":
        db_path = args.db_path or settings.db_path
        report_path = PROJECT_ROOT / "reports" / "03_category_growth.md"
        figure_dir = PROJECT_ROOT / "reports" / "figures"
        try:
            summary = run_category_growth(
                db_path=db_path,
                report_path=report_path,
                generated_dir=settings.report_dir,
                figure_dir=figure_dir,
            )
        except (OSError, RuntimeError, AssertionError, ValueError) as exc:
            print(exc)
            return 2
        print(f"品类增长分析报告已生成：{report_path}")
        print(
            f"2018年1至8月GMV同比 {summary['gmv_growth_rate']:.1%}，"
            f"前五个增长品类贡献净增量的 "
            f"{summary['top_five_growth_contribution']:.1%}。"
        )
        return 0

    if args.command == "analyze-deep-dives":
        db_path = args.db_path or settings.db_path
        try:
            summaries = run_advanced_analyses(
                db_path=db_path,
                report_dir=PROJECT_ROOT / "reports",
                generated_dir=settings.report_dir,
                figure_dir=PROJECT_ROOT / "reports" / "figures",
            )
        except (OSError, RuntimeError, AssertionError, ValueError) as exc:
            print(exc)
            return 2
        print("地区、商家和用户专题分析已生成。")
        print(
            f"用户复购率 {summaries['customer']['repeat_rate']:.1%}，"
            f"Top 10商家GMV份额 {summaries['seller']['top_10_share']:.1%}。"
        )
        return 0

    if args.command == "ask":
        db_path = args.db_path or settings.db_path
        try:
            import duckdb

            connection = duckdb.connect(str(db_path), read_only=True)
            try:
                result = ask(connection, args.question)
            finally:
                connection.close()
        except (OSError, RuntimeError, ValueError) as exc:
            print(exc)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result["status"] == "ok" else 1

    if args.command == "evaluate-copilot":
        db_path = args.db_path or settings.db_path
        try:
            result = run_evaluation(
                db_path=db_path,
                evaluation_path=PROJECT_ROOT / "eval" / "questions.jsonl",
                report_path=PROJECT_ROOT / "reports" / "07_copilot_evaluation.md",
                generated_dir=settings.report_dir,
            )
        except (OSError, RuntimeError, AssertionError, ValueError) as exc:
            print(exc)
            return 2
        print("Copilot离线评测已生成：" + str(PROJECT_ROOT / "reports" / "07_copilot_evaluation.md"))
        print(
            f"语义层答案准确率 {result['semantic']['answer_accuracy']:.1%}，"
            f"关键词基线 {result['baseline']['answer_accuracy']:.1%}。"
        )
        return 0

    if args.command == "export-dashboard":
        db_path = args.db_path or settings.db_path
        output_path = PROJECT_ROOT / "dashboard" / "data.json"
        try:
            export_dashboard_data(db_path, output_path)
        except (OSError, RuntimeError, ValueError) as exc:
            print(exc)
            return 2
        print(f"看板数据已生成：{output_path}")
        return 0

    if args.command == "run-all":
        db_path = args.db_path or settings.db_path
        report_dir = PROJECT_ROOT / "reports"
        figure_dir = report_dir / "figures"
        try:
            overview = run_business_overview(
                db_path=db_path,
                report_path=report_dir / "02_business_overview.md",
                generated_dir=settings.report_dir,
                figure_dir=figure_dir,
            )
            category = run_category_growth(
                db_path=db_path,
                report_path=report_dir / "03_category_growth.md",
                generated_dir=settings.report_dir,
                figure_dir=figure_dir,
            )
            advanced = run_advanced_analyses(
                db_path=db_path,
                report_dir=report_dir,
                generated_dir=settings.report_dir,
                figure_dir=figure_dir,
            )
            evaluation = run_evaluation(
                db_path=db_path,
                evaluation_path=PROJECT_ROOT / "eval" / "questions.jsonl",
                report_path=report_dir / "07_copilot_evaluation.md",
                generated_dir=settings.report_dir,
            )
            export_dashboard_data(db_path, PROJECT_ROOT / "dashboard" / "data.json")
            write_final_report(
                overview,
                category,
                advanced,
                evaluation,
                report_dir / "00_portfolio_case_study.md",
            )
        except (OSError, RuntimeError, AssertionError, ValueError) as exc:
            print(exc)
            return 2
        print("全部分析、Copilot评测、看板数据和项目总报告已生成。")
        print(f"项目总报告：{report_dir / '00_portfolio_case_study.md'}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
