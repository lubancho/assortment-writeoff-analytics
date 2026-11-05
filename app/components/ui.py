"""Общие элементы интерфейса: подключение, фильтры, форматирование, оформление графиков.

Интерфейс только показывает данные — все расчёты в пакете asa (их проверяют тесты без Streamlit).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import psycopg
import streamlit as st

from asa import analysis
from asa import repository as repo
from asa.abc import AbcThresholds
from asa.config import DEMO_NOTE
from asa.db import connect
from asa.xyz import XyzSettings

PALETTE = {
    "accent": "#3E5C76",
    "accent2": "#7F9BB3",
    "accent3": "#A3B8C9",
    "crit": "#B3261E",
    "warn": "#B26A00",
    "ok": "#2E7D32",
    "info": "#5B6B7A",
    "grid": "#E1E6EB",
    "muted": "#8A97A3",
}
CLASS_COLORS = {
    "A": "#3E5C76",
    "B": "#7F9BB3",
    "C": "#C3D0DB",
    "X": "#2E7D32",
    "Y": "#B26A00",
    "Z": "#B3261E",
}
REASON_LABEL = {
    "expired": "Истёк срок",
    "damaged": "Брак, повреждение",
    "return": "Возврат",
    "other": "Прочее",
}

pio.templates["asa"] = go.layout.Template(
    layout=go.Layout(
        font={"family": "Inter, Segoe UI, sans-serif", "size": 13, "color": "#1F2933"},
        colorway=[
            PALETTE["accent"],
            PALETTE["accent2"],
            PALETTE["accent3"],
            PALETTE["warn"],
            PALETTE["ok"],
        ],
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis={"gridcolor": PALETTE["grid"], "zeroline": False},
        yaxis={"gridcolor": PALETTE["grid"], "zeroline": False},
        margin={"l": 10, "r": 10, "t": 40, "b": 10},
        legend={"orientation": "h", "y": -0.18},
        hoverlabel={"bgcolor": "white"},
        separators=", ",
    )
)
pio.templates.default = "plotly_white+asa"

_CSS = """
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 1rem; max-width: 1500px;}
[data-testid="stMetric"] {background: #FFFFFF; border: 1px solid #E1E6EB; border-radius: 8px;
  padding: 10px 14px; min-height: 108px;}
[data-testid="stMetricLabel"] p {font-size: 0.82rem; color: #5B6B7A;}
[data-testid="stMetricValue"] {font-size: 1.55rem;}
.asa-footer {color: #8A97A3; font-size: 0.78rem; border-top: 1px solid #E1E6EB; margin-top: 1.5rem;
  padding-top: 0.4rem;}
.asa-box {background: #FFFFFF; border: 1px solid #E1E6EB; border-left: 4px solid #3E5C76;
  border-radius: 6px; padding: 10px 14px; margin: 4px 0 10px 0;}
.asa-box.warn {border-left-color: #B26A00;}
.asa-box.crit {border-left-color: #B3261E;}
</style>
"""


# --- Подключение и кэш ----------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def _connection() -> psycopg.Connection:
    return connect()


def get_conn() -> psycopg.Connection:
    conn = _connection()
    if conn.closed or conn.broken:
        _connection.clear()
        conn = _connection()
    return conn


@st.cache_data(show_spinner=False, ttl=600)
def cached_period() -> tuple[date, date] | None:
    return repo.data_period(get_conn())


@st.cache_data(show_spinner=False, ttl=600)
def cached_stores() -> pd.DataFrame:
    return repo.stores(get_conn())


@st.cache_data(show_spinner=False, ttl=600)
def cached_categories() -> pd.DataFrame:
    return repo.categories(get_conn())


@st.cache_data(show_spinner="Считаю показатели…", ttl=600)
def cached_analysis(
    d0: date, d1: date, a: float, b: float, x: float, y: float, detrend: bool
) -> pd.DataFrame:
    settings = analysis.AnalysisSettings(
        abc=AbcThresholds(Decimal(str(a)), Decimal(str(b))),
        xyz=XyzSettings(x_max=x, y_max=y, detrend=detrend),
    )
    return analysis.product_analysis(get_conn(), d0, d1, settings)


def analysis_params() -> dict:
    """Пороги ABC/XYZ из настроек экрана «Ассортимент» (или значения по умолчанию)."""
    s = st.session_state
    return {
        "a": s.get("cfg_abc_a", 80) / 100,
        "b": s.get("cfg_abc_b", 95) / 100,
        "x": s.get("cfg_xyz_x", 10) / 100,
        "y": s.get("cfg_xyz_y", 25) / 100,
        "detrend": s.get("cfg_xyz_detrend", False),
    }


def product_analysis() -> pd.DataFrame:
    d0, d1 = current_period()
    return cached_analysis(d0, d1, **analysis_params())


# --- Каркас страницы --------------------------------------------------------------------------


def page_header(title: str, subtitle: str | None = None) -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def footer() -> None:
    st.markdown(
        f"<div class='asa-footer'>{DEMO_NOTE} Учебно-практический проект.</div>",
        unsafe_allow_html=True,
    )


def sidebar_filters() -> None:
    """Общие фильтры: период и точки. Значения хранятся в st.session_state и действуют на всех экранах."""
    period = cached_period()
    with st.sidebar:
        if period is None:
            return
        d0, d1 = period
        st.date_input(
            "Период анализа",
            (max(d0, d1 - timedelta(days=27)), d1),
            min_value=d0,
            max_value=d1,
            key="period",
            format="DD.MM.YYYY",
        )
        stores = cached_stores()
        st.multiselect(
            "Точки",
            stores["store_id"],
            key="stores",
            placeholder="Вся сеть",
            format_func=dict(zip(stores["store_id"], stores["name"], strict=True)).get,
            help="Фильтр точек действует на продажи, остатки и списания. ABC/XYZ и рекомендации "
            "считаются по сети в целом.",
        )
        st.caption(f"Данные: {d0:%d.%m.%Y} — {d1:%d.%m.%Y}")


def current_period() -> tuple[date, date]:
    period = cached_period()
    if period is None:
        st.warning("В базе нет данных. Выполните загрузку: `asa init-demo`.")
        footer()
        st.stop()
    value = st.session_state.get("period") or (
        max(period[0], period[1] - timedelta(days=27)),
        period[1],
    )
    if isinstance(value, tuple | list) and len(value) == 2:
        return value[0], value[1]
    st.info("Выберите конечную дату периода в боковой панели")
    st.stop()


def current_stores() -> list[int] | None:
    return list(st.session_state.get("stores") or []) or None


def period_caption() -> str:
    d0, d1 = current_period()
    stores = current_stores()
    where = "вся сеть" if not stores else f"точек: {len(stores)}"
    return f"Период {d0:%d.%m.%Y} — {d1:%d.%m.%Y} · {where}"


def box(text: str, kind: str = "") -> None:
    st.markdown(f"<div class='asa-box {kind}'>{text}</div>", unsafe_allow_html=True)


# --- Форматирование ----------------------------------------------------------------------------


def _num(x) -> float | None:
    if x is None:
        return None
    if isinstance(x, Decimal):
        return float(x)
    try:
        return None if pd.isna(x) else float(x)
    except TypeError:
        return None


def fmt_rub(x, digits: int = 0) -> str:
    v = _num(x)
    if v is None:
        return "н/д"
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:,.1f} млн ₽".replace(",", " ").replace(".", ",")
    return f"{v:,.{digits}f} ₽".replace(",", " ").replace(".", ",")


def fmt_pct(x, digits: int = 1, signed: bool = False) -> str:
    v = _num(x)
    if v is None:
        return "н/д"
    s = f"{v * 100:+.{digits}f}%" if signed else f"{v * 100:.{digits}f}%"
    return s.replace(".", ",")


def fmt_pp(x, digits: int = 1) -> str:
    v = _num(x)
    return "н/д" if v is None else f"{v * 100:+.{digits}f}".replace(".", ",") + " п. п."


def fmt_num(x, digits: int = 0) -> str:
    v = _num(x)
    return "н/д" if v is None else f"{v:,.{digits}f}".replace(",", " ").replace(".", ",")


def to_display(df: pd.DataFrame) -> pd.DataFrame:
    """Decimal → float для таблиц и графиков (только слой отображения)."""
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == object and out[c].map(lambda v: isinstance(v, Decimal)).any():
            out[c] = out[c].map(lambda v: float(v) if isinstance(v, Decimal) else v).astype(float)
    return out


def pct_col(s: pd.Series) -> pd.Series:
    """Доля → проценты для отображения в таблице."""
    return s.map(lambda v: float(v) * 100 if v is not None and not pd.isna(v) else None)
