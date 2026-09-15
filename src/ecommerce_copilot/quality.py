from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ecommerce_copilot.catalog import DatasetSpec, discover


def profile_csv(spec: DatasetSpec, path: Path) -> dict[str, Any]:
    """Stream a CSV file and collect portfolio-friendly baseline quality metrics."""
    row_count = 0
    empty_counts: Counter[str] = Counter()
    duplicate_keys = 0
    seen_keys: set[tuple[str, ...]] = set()

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        has_primary_key = bool(spec.primary_key) and all(key in columns for key in spec.primary_key)

        for row in reader:
            row_count += 1
            for column in columns:
                if row.get(column, "").strip() == "":
                    empty_counts[column] += 1

            if has_primary_key:
                key = tuple(row.get(column, "") for column in spec.primary_key)
                if key in seen_keys:
                    duplicate_keys += 1
                else:
                    seen_keys.add(key)

    return {
        "table": spec.table,
        "filename": spec.filename,
        "required": spec.required,
        "exists": True,
        "size_bytes": path.stat().st_size,
        "row_count": row_count,
        "column_count": len(columns),
        "columns": columns,
        "primary_key": list(spec.primary_key),
        "duplicate_primary_keys": duplicate_keys if spec.primary_key else None,
        "empty_counts": {column: empty_counts[column] for column in columns},
    }


def inspect_data(data_dir: Path) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for spec, path in discover(data_dir).items():
        if path is None:
            profiles.append(
                {
                    "table": spec.table,
                    "filename": spec.filename,
                    "required": spec.required,
                    "exists": False,
                    "primary_key": list(spec.primary_key),
                }
            )
        else:
            profiles.append(profile_csv(spec, path))
    return profiles


def _markdown_report(profiles: list[dict[str, Any]], data_dir: Path) -> str:
    present = sum(profile["exists"] for profile in profiles)
    required_missing = [p["filename"] for p in profiles if p["required"] and not p["exists"]]
    lines = [
        "# 原始数据质量报告",
        "",
        f"- 数据目录：`{data_dir}`",
        f"- 已发现文件：{present}/{len(profiles)}",
        f"- 缺失必需文件：{len(required_missing)}",
        "",
        "| 表 | 文件状态 | 行数 | 字段数 | 重复主键 |",
        "|---|---:|---:|---:|---:|",
    ]
    for profile in profiles:
        if profile["exists"]:
            duplicate = profile["duplicate_primary_keys"]
            duplicate_display = "-" if duplicate is None else str(duplicate)
            lines.append(
                f"| `{profile['table']}` | 已发现 | {profile['row_count']:,} | "
                f"{profile['column_count']} | {duplicate_display} |"
            )
        else:
            status = "缺失（必需）" if profile["required"] else "缺失（可选）"
            lines.append(f"| `{profile['table']}` | {status} | - | - | - |")

    if required_missing:
        lines.extend(["", "## 缺失的必需文件", ""])
        lines.extend(f"- `{filename}`" for filename in required_missing)

    for profile in profiles:
        if not profile["exists"]:
            continue
        missing = {column: count for column, count in profile["empty_counts"].items() if count > 0}
        lines.extend(["", f"## {profile['table']}", ""])
        if missing:
            lines.extend(
                [
                    "| 缺失字段 | 缺失行数 | 缺失率 |",
                    "|---|---:|---:|",
                ]
            )
            row_count = profile["row_count"]
            for column, count in sorted(missing.items(), key=lambda item: item[1], reverse=True):
                rate = count / row_count if row_count else 0
                lines.append(f"| `{column}` | {count:,} | {rate:.2%} |")
        else:
            lines.append("未发现空字符串或空单元格。")

    lines.append("")
    return "\n".join(lines)


def write_quality_report(data_dir: Path, report_dir: Path) -> list[dict[str, Any]]:
    report_dir.mkdir(parents=True, exist_ok=True)
    profiles = inspect_data(data_dir)
    (report_dir / "data_quality.json").write_text(
        json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (report_dir / "data_quality.md").write_text(
        _markdown_report(profiles, data_dir), encoding="utf-8"
    )
    return profiles
