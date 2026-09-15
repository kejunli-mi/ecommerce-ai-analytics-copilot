from __future__ import annotations

from pathlib import Path

from ecommerce_copilot.catalog import discover, missing_required


def build_warehouse(data_dir: Path, db_path: Path, analytics_sql_path: Path) -> list[str]:
    """Load available Olist CSVs and create analysis-layer views."""
    missing = missing_required(data_dir)
    if missing:
        filenames = ", ".join(spec.filename for spec in missing)
        raise FileNotFoundError(f"缺少建库所需文件：{filenames}")

    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError('尚未安装 DuckDB，请运行：python -m pip install -e ".[dev]"') from exc

    db_path.parent.mkdir(parents=True, exist_ok=True)
    loaded: list[str] = []
    connection = duckdb.connect(str(db_path))
    try:
        connection.execute("CREATE SCHEMA IF NOT EXISTS raw")
        connection.execute("CREATE SCHEMA IF NOT EXISTS analytics")

        for spec, path in discover(data_dir).items():
            if path is None:
                continue
            connection.execute(
                f"""
                CREATE OR REPLACE TABLE raw.{spec.table} AS
                SELECT * FROM read_csv_auto(?, header = true, sample_size = -1)
                """,
                [str(path)],
            )
            loaded.append(spec.table)

        if "category_translation" not in loaded:
            connection.execute(
                """
                CREATE OR REPLACE TABLE raw.category_translation (
                    product_category_name VARCHAR,
                    product_category_name_english VARCHAR
                )
                """
            )

        connection.execute(analytics_sql_path.read_text(encoding="utf-8"))
    finally:
        connection.close()
    return loaded
