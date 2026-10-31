"""Optional UI smoke test; all writes use a temporary database."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
pytest.importorskip("pandas")
from streamlit.testing.v1 import AppTest

from mosaic.audit_bridge import publish
from tests.legacy.test_conversion import convert_text


def test_explicit_database_opens_new_facts_and_all_amounts_are_visible(tmp_path, monkeypatch):
    result = convert_text(tmp_path)
    database = tmp_path / "new_review.sqlite3"
    publish(result["run_dir"], database)
    monkeypatch.setenv("MOSAIC_REVIEW_DB", str(database))
    app = AppTest.from_file(str(Path(__file__).parents[1] / "audit/app.py")).run(timeout=20)
    assert not app.exception
    assert any(str(database) in caption.value for caption in app.caption)
    frame = app.dataframe[0].value
    assert "24.2 mg" in frame.iloc[0]["amount"] and "0.2 mmol" in frame.iloc[0]["amount"]
