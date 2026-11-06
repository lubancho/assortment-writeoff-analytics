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

# Единая дизайн-система с демо-версией (docs/09_ux_redesign.md): фиолетовый — акцент и выбранное,
# красный / жёлтый / зелёный — только статусы и оценка «лучше / хуже для бизнеса».
PALETTE = {
    "accent": "#6A52EE",
    "accent2": "#A594FF",
    "accent3": "#D3C9FF",
    "crit": "#D93A52",
    "warn": "#E9A800",
    "ok": "#1FAE5B",
    "info": "#5D5590",
    "grid": "#E3DDFB",
    "muted": "#6C6599",
    "pink": "#EC6A9C",
}
CLASS_COLORS = {
    "A": "#6A52EE",
    "B": "#A594FF",
    "C": "#D3C9FF",
    "X": "#2FB9A5",
    "Y": "#F2A43A",
    "Z": "#EC6A9C",
}
NA = "нет данных"
HELP = {
    "rev": "Выручка = продажи за вычетом возвратов и скидок, без отменённых чеков.",
    "gp": "Валовая прибыль = выручка − себестоимость проданного. Аренда, персонал и прочие расходы не учитываются.",
    "mg": "Валовая маржинальность = валовая прибыль / выручка (по продажам с известной себестоимостью).",
    "wo": "Стоимость списаний = списанное количество × себестоимость на дату списания.",
    "ws": "Доля списаний = списания / (себестоимость проданного + списания). Знаменатель — себестоимость всего выпуска.",
    "check": "Средний чек = выручка / число чеков.",
    "oos": "Доля рабочих точко-дней, когда товара не было в продаже.",
    "soldout": "Доля точко-дней, когда товар распродан к закрытию: спрос был выше выпуска.",
    "turnover": "Оборачиваемость = себестоимость продаж / средний запас за период.",
    "dos": "Дни запаса = остаток на конец периода / средняя дневная себестоимость продаж.",
    "cv": "Коэффициент вариации недельных продаж: чем больше, тем нестабильнее спрос. X < 10%, Y 10–25%, Z > 25%.",
}
REASON_LABEL = {
    "expired": "Истёк срок",
    "damaged": "Брак, повреждение",
    "return": "Возврат",
    "other": "Прочее",
}

pio.templates["asa"] = go.layout.Template(
    layout=go.Layout(
        font={"family": "Manrope, Segoe UI, sans-serif", "size": 13, "color": "#1E1745"},
        colorway=[
            PALETTE["accent"],
            PALETTE["accent2"],
            "#EC6A9C",
            "#F2A43A",
            "#2FB9A5",
            "#4F8CF0",
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
.block-container {padding-top: 4rem; padding-bottom: 1rem; max-width: 1500px;}
h1 {letter-spacing: -0.02em;}
[data-testid="stSidebar"] {background: #4536A8;}
[data-testid="stSidebarNav"] span, [data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p, [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] strong {color: #FFFFFF !important;}
[data-testid="stSidebarNav"] a[aria-current="page"] {background: rgba(255,255,255,.18);}
[data-testid="stMetric"] {background: #FFFFFF; border: 1px solid #E3DDFB; border-radius: 16px;
  padding: 12px 16px; min-height: 112px; box-shadow: 0 8px 24px rgba(70,50,170,.07);}
[data-testid="stMetricLabel"] p {font-size: 0.8rem; color: #544C86; font-weight: 700;}
[data-testid="stMetricValue"] {font-size: 1.6rem; font-weight: 800;}
.ux-lvl {display:flex; gap:10px; align-items:center; margin:1.4rem 0 .4rem;}
.ux-lvl b {font-size:1.15rem;}
.ux-lv {font-size:.68rem; font-weight:800; letter-spacing:.1em; text-transform:uppercase; color:#6A52EE;
  background:#EFEBFF; padding:2px 9px; border-radius:999px;}
.ux-attn {background:#FFFFFF; border:1px solid #E3DDFB; border-left:5px solid var(--ac,#8B75FF);
  border-radius:12px; padding:10px 14px; margin:0 0 4px;}
.ux-attn .t {font-weight:800;} .ux-attn .w {font-size:.88rem; color:#2E2660;}
.ux-pill {display:inline-block; padding:1px 9px; border-radius:999px; font-size:.72rem; font-weight:800;
  margin-right:6px;}
.ux-pill.crit {background:#D93A52; color:#fff;} .ux-pill.warn {background:#FCD34D; color:#4A3500;}
.ux-pill.info {background:#EFEBFF; color:#6A52EE;} .ux-pill.ok {background:#4ADE80; color:#073B1D;}
.ux-scope {background:#FFF4D4; border:1px solid #F0CF6A; border-radius:10px; padding:6px 12px;
  font-size:.86rem; margin:4px 0 10px;}
.asa-footer {color: #6C6599; font-size: 0.78rem; border-top: 1px solid #E3DDFB; margin-top: 1.5rem;
  padding-top: 0.4rem;}
.asa-box {background: #FFFFFF; border: 1px solid #E3DDFB; border-left: 4px solid #6A52EE;
  border-radius: 10px; padding: 10px 14px; margin: 4px 0 10px 0;}
.asa-box.warn {border-left-color: #E9A800; background:#FFFBEA;}
.asa-box.crit {border-left-color: #D93A52; background:#FDF0F2;}
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
    """Пороги ABC/XYZ из настроек страницы «Ассортимент» (или значения по умолчанию)."""
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


def filter_bar() -> None:
    """Общие фильтры в верхней строке страницы: период и точки (в боковой панели только разделы).

    Значения хранятся в st.session_state и действуют на всех экранах.
    """
    period = cached_period()
    if period is None:
        return
    d0, d1 = period
    c1, c2, c3 = st.columns([2, 3, 2], vertical_alignment="bottom")
    c1.date_input(
        "Период анализа",
        (max(d0, d1 - timedelta(days=27)), d1),
        min_value=d0,
        max_value=d1,
        key="period",
        format="DD.MM.YYYY",
    )
    stores = cached_stores()
    c2.multiselect(
        "Точки",
        stores["store_id"],
        key="stores",
        placeholder="Вся сеть",
        format_func=dict(zip(stores["store_id"], stores["name"], strict=True)).get,
        help="Фильтр точек действует на продажи, остатки и списания. ABC/XYZ и рекомендации "
        "считаются по сети в целом.",
    )
    c3.caption(f"Данные: {d0:%d.%m.%Y} — {d1:%d.%m.%Y}")


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
    st.info("Выберите конечную дату в фильтре периода вверху страницы")
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


LEVELS = {"crit": "Высокая важность", "warn": "Требует внимания", "info": "Информация"}
_AC = {"crit": "#D93A52", "warn": "#E9A800", "info": "#8B75FF"}


def level(tag: str, title: str, hint: str | None = None) -> None:
    """Заголовок уровня иерархии: «Состояние», «Внимание», «Подробно», «Методика»."""
    st.markdown(
        f"<div class='ux-lvl'><span class='ux-lv'>{tag}</span><b>{title}</b></div>",
        unsafe_allow_html=True,
    )
    if hint:
        st.caption(hint)


def scope_note(text: str) -> None:
    """Плашка об области действия показателя (например, «рассчитано по всей сети»)."""
    st.markdown(f"<div class='ux-scope'>ⓘ {text}</div>", unsafe_allow_html=True)


def attention(items: list[dict], key: str) -> None:
    """Блок «Что требует внимания»: уровень, вывод, объяснение, число и переход к деталям.

    items: {lvl: crit|warn|info, title, why, value, page?, state?: dict}
    """
    if not items:
        st.success("Существенных отклонений не найдено.")
        return
    for i, it in enumerate(items):
        c1, c2 = st.columns([8.6, 1.4], vertical_alignment="center")
        c1.markdown(
            f"<div class='ux-attn' style='--ac:{_AC[it['lvl']]}'>"
            f"<span class='ux-pill {it['lvl']}'>{LEVELS[it['lvl']]}</span>"
            f"<span class='t'>{it['title']}</span> · <b>{it['value']}</b>"
            f"<div class='w'>{it['why']}</div></div>",
            unsafe_allow_html=True,
        )
        if it.get("page") and c2.button("Открыть →", key=f"{key}_{i}", width="stretch"):
            for k, v in (it.get("state") or {}).items():
                st.session_state[k] = v
            st.switch_page(it["page"])


def styled(df: pd.DataFrame, formats: dict[str, str]) -> pd.DataFrame:
    """Таблица в русском формате; пустые значения — «нет данных», а не None и не ноль.

    formats: колонка → rub | pct | spct | pp | int | num1. Отформатированные колонки становятся
    текстом (Streamlit не умеет подписывать пустые числовые ячейки); выравнивание — num_cfg().
    """
    fn = {
        "rub": lambda v: fmt_rub(v, full=True),
        "pct": fmt_pct,
        "spct": lambda v: fmt_pct(v, signed=True),
        "pp": fmt_pp,
        "int": lambda v: fmt_num(v, 0),
        "num1": lambda v: fmt_num(v, 1),
    }
    view = df.copy()
    for c, k in formats.items():
        if c in view.columns and k in fn:
            view[c] = view[c].map(fn[k])
    for c in view.columns:
        if view[c].dtype == object:
            view[c] = view[c].map(
                lambda v: NA if v is None or (isinstance(v, float) and pd.isna(v)) else v
            )
    return view


def num_cfg(formats: dict[str, str]) -> dict:
    """Выравнивание чисел по правому краю для колонок, отформатированных styled()."""
    return {c: st.column_config.TextColumn(alignment="right") for c in formats}


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


def fmt_rub(x, digits: int = 0, full: bool = False) -> str:
    v = _num(x)
    if v is None:
        return NA
    if abs(v) >= 1_000_000 and not full:
        return f"{v / 1_000_000:,.1f} млн ₽".replace(",", " ").replace(".", ",")
    return f"{v:,.{digits}f} ₽".replace(",", " ").replace(".", ",")


def fmt_pct(x, digits: int = 1, signed: bool = False) -> str:
    v = _num(x)
    if v is None:
        return NA
    s = f"{v * 100:+.{digits}f}%" if signed else f"{v * 100:.{digits}f}%"
    return s.replace(".", ",")


def fmt_pp(x, digits: int = 1) -> str:
    v = _num(x)
    return NA if v is None else f"{v * 100:+.{digits}f}".replace(".", ",") + " п. п."


def fmt_num(x, digits: int = 0) -> str:
    v = _num(x)
    return NA if v is None else f"{v:,.{digits}f}".replace(",", " ").replace(".", ",")


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
