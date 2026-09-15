from __future__ import annotations

import csv
import json
import time
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from ecommerce_copilot.copilot import (
    QueryPlan,
    build_sql,
    execute_plan,
    route_baseline,
    route_semantic,
)


def load_evaluation_set(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if len(rows) != 50:
        raise ValueError(f"评测集必须包含50道题，当前为{len(rows)}道")
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("评测集ID存在重复")
    return rows


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return round(float(value), 6)
    if isinstance(value, float):
        return round(value, 6)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _signature(columns: list[str], rows: list[tuple[Any, ...]]) -> tuple[Any, ...]:
    return (
        tuple(columns),
        tuple(tuple(_normalize_value(value) for value in row) for row in rows),
    )


def _params_match(actual: dict[str, int], expected: dict[str, int]) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def evaluate_provider(
    connection: Any,
    cases: list[dict[str, Any]],
    provider: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    router = route_semantic if provider == "semantic" else route_baseline
    details: list[dict[str, Any]] = []
    latencies: list[float] = []
    for case in cases:
        started = time.perf_counter()
        plan: QueryPlan | None = None
        error: str | None = None
        executable = False
        answer_correct = False
        expected_intent = str(case["expected_intent"])
        expected_params = {key: int(value) for key, value in case.get("expected_params", {}).items()}
        try:
            plan = router(str(case["question"]))
            route_correct = (
                plan is not None
                and plan.intent == expected_intent
                and _params_match(plan.params, expected_params)
            )
            if expected_intent == "blocked":
                answer_correct = route_correct
            elif plan is not None and plan.sql is not None:
                predicted_columns, predicted_rows = execute_plan(connection, plan)
                executable = True
                gold_plan = QueryPlan(
                    intent=expected_intent,
                    params=expected_params,
                    sql=build_sql(expected_intent, expected_params),
                    explanation="gold",
                )
                gold_columns, gold_rows = execute_plan(connection, gold_plan)
                answer_correct = route_correct and _signature(
                    predicted_columns, predicted_rows
                ) == _signature(gold_columns, gold_rows)
        except (RuntimeError, ValueError) as exc:
            route_correct = False
            error = str(exc)
        latency_ms = (time.perf_counter() - started) * 1_000
        latencies.append(latency_ms)
        details.append(
            {
                "provider": provider,
                "id": case["id"],
                "question": case["question"],
                "expected_intent": expected_intent,
                "predicted_intent": None if plan is None else plan.intent,
                "route_correct": route_correct,
                "executable": executable,
                "answer_correct": answer_correct,
                "latency_ms": round(latency_ms, 3),
                "error": error,
            }
        )

    analytic_details = [row for row in details if row["expected_intent"] != "blocked"]
    safety_details = [row for row in details if row["expected_intent"] == "blocked"]
    ordered_latency = sorted(latencies)
    middle = len(ordered_latency) // 2
    median_latency = (
        ordered_latency[middle]
        if len(ordered_latency) % 2
        else (ordered_latency[middle - 1] + ordered_latency[middle]) / 2
    )
    metrics = {
        "provider": provider,
        "question_count": len(details),
        "analytic_question_count": len(analytic_details),
        "safety_question_count": len(safety_details),
        "intent_accuracy": sum(bool(row["route_correct"]) for row in details) / len(details),
        "execution_rate": sum(bool(row["executable"]) for row in analytic_details)
        / len(analytic_details),
        "answer_accuracy": sum(bool(row["answer_correct"]) for row in analytic_details)
        / len(analytic_details),
        "safety_accuracy": sum(bool(row["answer_correct"]) for row in safety_details)
        / len(safety_details),
        "median_latency_ms": median_latency,
    }
    return metrics, details


def _write_detail_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _error_counts(details: list[dict[str, Any]]) -> dict[str, int]:
    errors: Counter[str] = Counter()
    for row in details:
        if row["answer_correct"]:
            continue
        if row["predicted_intent"] is None:
            errors["未识别"] += 1
        elif row["predicted_intent"] != row["expected_intent"]:
            errors["意图误分类"] += 1
        elif not row["executable"] and row["expected_intent"] != "blocked":
            errors["SQL执行失败"] += 1
        else:
            errors["参数或答案不一致"] += 1
    return dict(errors)


def _intent_accuracy(details: list[dict[str, Any]]) -> dict[str, tuple[int, int]]:
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in details:
        counts[str(row["expected_intent"])][1] += 1
        counts[str(row["expected_intent"])][0] += int(bool(row["route_correct"]))
    return {intent: (values[0], values[1]) for intent, values in sorted(counts.items())}


def _write_report(
    baseline: dict[str, Any],
    semantic: dict[str, Any],
    baseline_details: list[dict[str, Any]],
    semantic_details: list[dict[str, Any]],
    report_path: Path,
) -> None:
    improvement = semantic["answer_accuracy"] - baseline["answer_accuracy"]
    baseline_errors = _error_counts(baseline_details)
    semantic_errors = _error_counts(semantic_details)
    by_intent = _intent_accuracy(semantic_details)
    lines = [
        "# Copilot离线效果评测",
        "",
        "## 结论摘要",
        "",
        (
            f"在50道固定问题上，语义层Copilot的答案准确率为 "
            f"{semantic['answer_accuracy']:.1%}，相比简单关键词基线提升 "
            f"{improvement * 100:.1f} 个百分点。"
        ),
        "",
        (
            f"语义层方案的意图识别准确率为 {semantic['intent_accuracy']:.1%}，"
            f"SQL可执行率为 {semantic['execution_rate']:.1%}，破坏性请求拦截率为 "
            f"{semantic['safety_accuracy']:.1%}。"
        ),
        "",
        "本评测验证的是可控语义路由与指标口径，不代表通用大模型能力。",
        "",
        "## 方案对比",
        "",
        "| 方案 | 意图准确率 | 答案准确率 | SQL可执行率 | 安全拦截率 | 中位延迟 |",
        "|---|---:|---:|---:|---:|---:|",
        (
            f"| 关键词基线 | {baseline['intent_accuracy']:.1%} | "
            f"{baseline['answer_accuracy']:.1%} | {baseline['execution_rate']:.1%} | "
            f"{baseline['safety_accuracy']:.1%} | {baseline['median_latency_ms']:.2f} ms |"
        ),
        (
            f"| 语义层Copilot | {semantic['intent_accuracy']:.1%} | "
            f"{semantic['answer_accuracy']:.1%} | {semantic['execution_rate']:.1%} | "
            f"{semantic['safety_accuracy']:.1%} | {semantic['median_latency_ms']:.2f} ms |"
        ),
        "",
        "## 语义层各意图识别结果",
        "",
        "| 意图 | 正确/总数 | 准确率 |",
        "|---|---:|---:|",
    ]
    for intent, (correct, total) in by_intent.items():
        lines.append(f"| {intent} | {correct}/{total} | {correct / total:.1%} |")
    lines.extend(
        [
            "",
            "## 错误归因",
            "",
            "| 错误类型 | 关键词基线 | 语义层Copilot |",
            "|---|---:|---:|",
        ]
    )
    for error_type in sorted(set(baseline_errors) | set(semantic_errors)):
        lines.append(
            f"| {error_type} | {baseline_errors.get(error_type, 0)} | "
            f"{semantic_errors.get(error_type, 0)} |"
        )
    if not baseline_errors and not semantic_errors:
        lines.append("| 无 | 0 | 0 |")
    lines.extend(
        [
            "",
            "## 产品分析含义",
            "",
            "- 语义层将GMV、复购率、延迟率等口径绑定到固定SQL模板，降低自由生成带来的口径漂移。",
            "- 拦截非只读请求，并将年份、Top N等参数限制在允许范围内。",
            "- 产品上线前还需要增加未见过的真实用户问题、权限测试、长查询资源限制和人工复核。",
            "",
            "## 评测口径",
            "",
            "- 评测集固定为45道分析问题和5道安全问题。",
            "- 答案准确率通过执行预测SQL与基准SQL，比较列、行和数值结果。",
            "- 延迟为本地DuckDB上的路由与查询执行时间，不包含网络大模型调用。",
            "- 评测问题与路由规则同库管理，结果更适合作为回归测试，不应解读为真实世界泛化准确率。",
            "",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def run_evaluation(
    db_path: Path,
    evaluation_path: Path,
    report_path: Path,
    generated_dir: Path,
) -> dict[str, Any]:
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError('尚未安装 DuckDB，请运行：python -m pip install -e ".[dev]"') from exc

    cases = load_evaluation_set(evaluation_path)
    connection = duckdb.connect(str(db_path), read_only=True)
    try:
        baseline_metrics, baseline_details = evaluate_provider(connection, cases, "baseline")
        semantic_metrics, semantic_details = evaluate_provider(connection, cases, "semantic")
    finally:
        connection.close()

    generated_dir.mkdir(parents=True, exist_ok=True)
    result = {"baseline": baseline_metrics, "semantic": semantic_metrics}
    (generated_dir / "copilot_evaluation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_detail_csv(
        baseline_details + semantic_details,
        generated_dir / "copilot_evaluation_details.csv",
    )
    _write_report(
        baseline_metrics,
        semantic_metrics,
        baseline_details,
        semantic_details,
        report_path,
    )
    return result
