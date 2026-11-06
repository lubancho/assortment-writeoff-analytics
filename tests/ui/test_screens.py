"""Проверка экранов через Streamlit AppTest и согласованность интерфейса с SQL (ТЗ §29)."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.ui

APP = Path(__file__).resolve().parents[2] / "app"
VIEWS = [
    "overview",
    "assortment",
    "profitability",
    "stock",
    "recommendations",
    "reports",
    "sales",
    "methodology",
]


def run_view(view: str, period=None, stores=None) -> AppTest:
    script = f"""
import sys
sys.path.insert(0, {str(APP)!r})
import streamlit as st
from datetime import date
period = {period!r}
if period is not None:
    st.session_state.setdefault("period", tuple(date.fromisoformat(d) for d in period))
st.session_state.setdefault("stores", {stores!r} or [])
exec(open({str(APP / "views" / (view + ".py"))!r}, encoding="utf-8").read())
"""
    at = AppTest.from_string(script, default_timeout=180)
    at.run()
    return at


@pytest.fixture(scope="module", autouse=True)
def _db(loaded_db):
    return loaded_db


@pytest.mark.parametrize("view", VIEWS)
def test_view_renders_without_errors(view):
    at = run_view(view)
    assert not at.exception, [e.value for e in at.exception]
    assert any("синтетические" in m.value for m in at.markdown)


@pytest.mark.parametrize("view", VIEWS)
def test_view_renders_with_store_filter_and_long_period(view):
    at = run_view(view, period=("2026-08-03", "2026-10-31"), stores=[1, 3])
    assert not at.exception, [e.value for e in at.exception]


def test_overview_numbers_match_sql(loaded_db):
    """Число на карточке «Выручка» совпадает с суммой SQL-задачи 1 (согласованность SQL ↔ интерфейс)."""
    import sys

    sys.path.insert(0, str(APP))
    from components.ui import fmt_rub

    from asa import queries
    from asa.db import connect

    at = run_view("overview", period=("2026-10-04", "2026-10-31"))
    with connect(loaded_db) as conn:
        from datetime import date

        t1 = queries.run(conn, 1, date(2026, 10, 4), date(2026, 10, 31))
    revenue = sum(t1["revenue"])
    card = next(m for m in at.metric if m.label == "Выручка")
    assert card.value == fmt_rub(revenue)


def test_assortment_threshold_validation():
    at = run_view("assortment")
    at.session_state["abc_a"] = 90
    at.session_state["abc_b"] = 60
    at.run()
    assert any("должна быть меньше" in e.value for e in at.error)


def test_reports_switch_sql_task():
    at = run_view("reports")
    at.radio[0].set_value(8).run()
    assert not at.exception
    assert len(at.get("download_button")) >= 2


def test_overview_has_hierarchy_and_attention_block():
    at = run_view("overview")
    text = " ".join(m.value for m in at.markdown)
    assert "Главные проблемы" in text
    assert [m.label for m in at.metric] == [
        "Выручка",
        "Маржа",
        "Потери на списаниях",
        "Доля списаний",
    ]
    assert sum("class='ux-attn'" in m.value for m in at.markdown) <= 3
    assert len(at.get("plotly_chart")) <= 1


@pytest.mark.parametrize("view", ["overview", "assortment", "profitability", "stock"])
def test_tables_label_missing_values(view):
    """Пустые значения подписаны «нет данных», а не выводятся как None (ТЗ на редизайн, §9)."""
    at = run_view(view)
    for df in (d.value for d in at.dataframe):
        if hasattr(df, "isna") and len(df) > 5:  # таблицы данных (не служебные сводки)
            assert not df.isna().any().any(), list(df.columns[df.isna().any()])


def test_assortment_groups_tab_uses_existing_thresholds():
    at = run_view("assortment")
    labels = [m.label for m in at.metric]
    assert "Основные источники выручки" in labels and "Высокая доля списаний" in labels
