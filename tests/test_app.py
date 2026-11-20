"""Smoke test for the local Streamlit app (skipped when streamlit is not installed)."""

from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
APP = str(Path(__file__).resolve().parents[1] / "app/streamlit_app.py")


def _app(db_path):
    at = st_testing.AppTest.from_file(APP, default_timeout=60)
    at.session_state["db_path"] = str(db_path)
    return at


def test_every_page_renders_on_an_empty_database(tmp_path):
    at = _app(tmp_path / "empty.sqlite").run()
    assert not at.exception
    for page in ["What I think and why", "Explore a route", "Every decision", "Run pipeline"]:
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception, page
