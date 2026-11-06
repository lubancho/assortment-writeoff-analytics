"""Разбор → «Продажи по точкам»: сравнение точек; динамика выручки и категории — в «Подробнее»."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components import ui

from asa import metrics, queries
from asa import repository as repo

ui.crumbs(("Сводка", "views/overview.py"), ("Выручка по точкам", None))
ui.page_header("Выручка по точкам", ui.period_caption() + " · отклонения — к среднему по сети")
d0, d1 = ui.current_period()
stores = ui.current_stores()


@st.cache_data(show_spinner=False, ttl=600)
def sales(d0, d1, stores, grain="network"):
    return metrics.enrich_sales(
        repo.sales_aggregates(ui.get_conn(), d0, d1, grain, store_ids=stores)
    )


@st.cache_data(show_spinner=False, ttl=600)
def write_offs(d0, d1, stores, grain="network"):
    return repo.write_off_aggregates(ui.get_conn(), d0, d1, grain, store_ids=stores)


@st.cache_data(show_spinner=False, ttl=600)
def active_skus(d0, d1, stores):
    df = repo.sales_aggregates(ui.get_conn(), d0, d1, "product", store_ids=stores)
    return int((df["net_qty"] > 0).sum())


@st.cache_data(show_spinner=False, ttl=600)
def daily(d0, d1):
    return queries.run(ui.get_conn(), 5, d0, d1)


length = (d1 - d0).days + 1
p0, p1 = d0 - timedelta(days=length), d0 - timedelta(days=1)
period = ui.cached_period()
has_prev = period is not None and p0 >= period[0]
cur = sales(d0, d1, stores).iloc[0]
prev = sales(p0, p1, stores).iloc[0] if has_prev else None
wo = write_offs(d0, d1, stores).iloc[0]
wo_prev = write_offs(p0, p1, stores).iloc[0] if has_prev else None
ws = metrics.write_off_share(wo.write_off_cost, cur.cogs)
ws_prev = metrics.write_off_share(wo_prev.write_off_cost, prev.cogs) if has_prev else None
NOTE = "к предыдущему периоду той же длины"


def delta(a, b):
    if b is None:
        return None
    r = metrics.safe_ratio(metrics.D(a) - metrics.D(b), abs(metrics.D(b))) if b else None
    return None if r is None else ui.fmt_pct(r, signed=True)


by_store = sales(d0, d1, None, "store")
wo_store = write_offs(d0, d1, None, "store")
tbl = by_store.merge(wo_store[["store_id", "write_off_cost"]], on="store_id", how="left")
tbl["write_off_share"] = [
    metrics.write_off_share(w, c) for w, c in zip(tbl["write_off_cost"], tbl["cogs"], strict=True)
]
net = sales(d0, d1, None).iloc[0]
net_ws = metrics.write_off_share(write_offs(d0, d1, None).iloc[0].write_off_cost, net.cogs)
tbl["d_margin"] = [None if m is None else m - net.gross_margin for m in tbl["gross_margin"]]
tbl["d_ws"] = [None if w is None else w - net_ws for w in tbl["write_off_share"]]
st.markdown("**Точки: продажи, маржа и списания** — отклонения к сети в процентных пунктах")
show = pd.DataFrame(
    {
        "Точка": tbl["store_name"],
        "Выручка, ₽": tbl["revenue"],
        "Маржа": tbl["gross_margin"],
        "Маржа к сети": tbl["d_margin"],
        "Доля списаний": tbl["write_off_share"],
        "Списания к сети": tbl["d_ws"],
    }
).sort_values(
    "Списания к сети",
    ascending=False,
    key=lambda s: s.map(lambda v: float(v) if v is not None else -9),
)
fmts = {
    "Выручка, ₽": "rub",
    "Маржа": "pct",
    "Маржа к сети": "pp",
    "Доля списаний": "pct",
    "Списания к сети": "pp",
}
st.dataframe(
    ui.styled(show, fmts),
    hide_index=True,
    width="stretch",
    column_config={
        **ui.num_cfg(fmts),
        "Маржа к сети": st.column_config.TextColumn(
            help="Плюс — маржа выше сети (лучше)", alignment="right"
        ),
        "Списания к сети": st.column_config.TextColumn(
            help="Плюс — доля списаний выше сети (хуже)", alignment="right"
        ),
    },
)
# --- Уровень 3: одна точка — категории, маржа и списания --------------------------------------
names = dict(zip(tbl["store_id"], tbl["store_name"], strict=True)) if len(tbl) else {}
if names:
    si = st.selectbox("Открыть точку", list(names), format_func=names.get, key="sl_store")
    cs = sales(d0, d1, [si], "category")
    cw = write_offs(d0, d1, [si], "category")
    c = cs.merge(cw[["category_id", "write_off_cost"]], on="category_id", how="left")
    st.dataframe(
        ui.styled(
            pd.DataFrame(
                {
                    "Категория": c["category_name"],
                    "Выручка, ₽": c["revenue"],
                    "Маржа": c["gross_margin"],
                    "Доля списаний": [
                        metrics.write_off_share(w, g)
                        for w, g in zip(c["write_off_cost"], c["cogs"], strict=True)
                    ],
                }
            ).sort_values("Выручка, ₽", ascending=False),
            {"Выручка, ₽": "rub", "Маржа": "pct", "Доля списаний": "pct"},
        ),
        hide_index=True,
        width="stretch",
        column_config=ui.num_cfg({"Выручка, ₽": "rub", "Маржа": "pct", "Доля списаний": "pct"}),
    )
    b1, b2, _ = st.columns([1.3, 1.6, 4])
    if b1.button("Списания точки ›", type="primary"):
        st.session_state["stores"] = [si]
        st.switch_page("views/stock.py")
    if b2.button("Маржа товаров точки ›"):
        st.session_state["stores"] = [si]
        st.switch_page("views/profitability.py")
ui.link("views/assortment.py", "Какие товары дают выручку ›")
with st.expander("Подробнее: выручка по дням и вклад категорий"):
    g1, g2 = st.columns([7, 5])
    with g1:
        dd = ui.to_display(daily(d0, d1))
        fig = go.Figure()
        fig.add_bar(
            x=dd["sale_date"],
            y=dd["revenue"],
            name="Выручка за день",
            marker_color=ui.PALETTE["accent2"],
        )
        fig.add_scatter(
            x=dd["sale_date"],
            y=dd["revenue_ma7"],
            name="Скользящая средняя за 7 дней",
            line={"color": ui.PALETTE["accent"], "width": 2.5},
        )
        fig.update_layout(title="Выручка сети по дням, ₽", height=340, yaxis_tickformat=",.0f")
        fig.update_xaxes(tickformat="%d.%m", hoverformat="%d.%m.%Y")
        st.plotly_chart(fig, width="stretch")
        if stores:
            st.caption("График динамики — по всей сети (SQL-задача 5).")
    with g2:
        cat = ui.to_display(sales(d0, d1, stores, "category"))
        cat["share"] = cat["revenue"] / cat["revenue"].sum() * 100
        cat["gp_share"] = cat["gross_profit"] / cat["gross_profit"].sum() * 100
        fig = go.Figure()
        fig.add_bar(
            y=cat["category_name"],
            x=cat["share"],
            name="Доля в выручке",
            orientation="h",
            marker_color=ui.PALETTE["accent2"],
        )
        fig.add_bar(
            y=cat["category_name"],
            x=cat["gp_share"],
            name="Доля в валовой прибыли",
            orientation="h",
            marker_color=ui.PALETTE["accent"],
        )
        fig.update_layout(
            title="Какие категории приносят выручку и прибыль, %",
            height=340,
            barmode="group",
            xaxis_ticksuffix="%",
            yaxis={"autorange": "reversed"},
        )
        st.plotly_chart(fig, width="stretch")
ui.footer()
