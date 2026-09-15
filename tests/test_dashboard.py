from pathlib import Path

import pytest


def test_streamlit_dashboard_starts_without_exception() -> None:
    streamlit = pytest.importorskip("streamlit.testing.v1")
    root = Path(__file__).resolve().parents[1]
    if not (root / "data" / "processed" / "ecommerce.duckdb").exists():
        pytest.skip("本地分析数据库尚未生成")

    app = streamlit.AppTest.from_file(root / "dashboard" / "app.py", default_timeout=15)
    app.run()

    assert not app.exception
    assert app.title[0].value == "电商经营数据分析 Copilot"
    assert len(app.tabs) == 5
