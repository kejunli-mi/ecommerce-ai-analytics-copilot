from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _project_path(env_name: str, default: str) -> Path:
    value = Path(os.environ.get(env_name, default))
    return value if value.is_absolute() else PROJECT_ROOT / value


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: _project_path("ECOMMERCE_DATA_DIR", "data/raw"))
    db_path: Path = field(
        default_factory=lambda: _project_path(
            "ECOMMERCE_DB_PATH", "data/processed/ecommerce.duckdb"
        )
    )
    report_dir: Path = field(
        default_factory=lambda: _project_path("ECOMMERCE_REPORT_DIR", "reports/generated")
    )
