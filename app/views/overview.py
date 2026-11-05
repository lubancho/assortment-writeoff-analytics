"""Экран «Обзор бизнеса»: ключевые показатели, динамика, сравнение точек."""

from __future__ import annotations

from datetime import timedelta

import plotly.graph_objects as go
import streamlit as st
from components import ui

from asa import metrics, queries
from asa import repository as repo

ui.page_header("Обзор бизнеса", ui.period_caption())
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
cur, prev = (
    sales(d0, d1, stores).iloc[0],
    sales(d0 - timedelta(days=length), d0 - timedelta(days=1), stores).iloc[0],
)
wo, wo_prev = (
    write_offs(d0, d1, stores).iloc[0],
    write_offs(d0 - timedelta(days=length), d0 - timedelta(days=1), stores).iloc[0],
)
NOTE = "к предыдущему периоду той же длины"


def delta(a, b):
    r = metrics.safe_ratio(metrics.D(a) - metrics.D(b), abs(metrics.D(b))) if b else None
    return None if r is None else ui.fmt_pct(r, signed=True)


k = st.columns(6)
k[0].metric(
    "Выручка", ui.fmt_rub(cur.revenue), delta(cur.revenue, prev.revenue), delta_description=NOTE
)
k[1].metric(
    "Валовая прибыль",
    ui.fmt_rub(cur.gross_profit),
    delta(cur.gross_profit, prev.gross_profit),
    delta_description=NOTE,
)
k[2].metric(
    "Маржинальность",
    ui.fmt_pct(cur.gross_margin),
    ui.fmt_pp(cur.gross_margin - prev.gross_margin)
    if cur.gross_margin and prev.gross_margin
    else None,
    delta_description=NOTE,
    help="Валовая прибыль / выручка (по строкам с известной себестоимостью)",
)
k[3].metric(
    "Стоимость списаний",
    ui.fmt_rub(wo.write_off_cost),
    delta(wo.write_off_cost, wo_prev.write_off_cost),
    delta_color="inverse",
    delta_description=NOTE,
    help="Списания по себестоимости на дату списания",
)
k[4].metric(
    "Активные SKU",
    ui.fmt_num(active_skus(d0, d1, stores)),
    "из 150",
    delta_color="off",
    delta_arrow="off",
    help="Товары с чистыми продажами больше нуля за период",
)
k[5].metric(
    "Средний чек",
    ui.fmt_rub(cur.avg_check),
    delta(cur.avg_check, prev.avg_check),
    delta_description=NOTE,
    help="Выручка / число чеков. Чек — заказ, в котором есть неотменённая продажа",
)

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
    fig.update_layout(title="Динамика выручки сети, ₽", height=340, yaxis_tickformat=",.0f")
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
        title="Вклад категорий, %",
        height=340,
        barmode="group",
        xaxis_ticksuffix="%",
        yaxis={"autorange": "reversed"},
    )
    st.plotly_chart(fig, width="stretch")

st.subheader("Сравнение торговых точек")
by_store = sales(d0, d1, None, "store")
wo_store = write_offs(d0, d1, None, "store")
tbl = by_store.merge(wo_store[["store_id", "write_off_cost"]], on="store_id", how="left")
tbl["write_off_share"] = [
    metrics.write_off_share(w, c) for w, c in zip(tbl["write_off_cost"], tbl["cogs"], strict=True)
]
show = ui.to_display(tbl)
st.dataframe(
    show.assign(
        gross_margin=ui.pct_col(tbl["gross_margin"]),
        write_off_share=ui.pct_col(tbl["write_off_share"]),
        revenue_share=show["revenue"] / show["revenue"].sum() * 100,
    )[
        [
            "store_name",
            "revenue",
            "revenue_share",
            "gross_profit",
            "gross_margin",
            "orders",
            "avg_check",
            "write_off_cost",
            "write_off_share",
        ]
    ].sort_values("revenue", ascending=False),
    hide_index=True,
    width="stretch",
    column_config={
        "store_name": "Точка",
        "revenue": st.column_config.NumberColumn("Выручка, ₽", format="localized"),
        "revenue_share": st.column_config.ProgressColumn(
            "Доля в выручке",
            format="%.1f%%",
            min_value=0,
            max_value=float(show["revenue"].max() / show["revenue"].sum() * 100),
        ),
        "gross_profit": st.column_config.NumberColumn("Валовая прибыль, ₽", format="localized"),
        "gross_margin": st.column_config.NumberColumn("Маржа, %", format="%.1f"),
        "orders": st.column_config.NumberColumn("Чеков", format="localized"),
        "avg_check": st.column_config.NumberColumn("Средний чек, ₽", format="%.0f"),
        "write_off_cost": st.column_config.NumberColumn("Списания, ₽", format="localized"),
        "write_off_share": st.column_config.NumberColumn(
            "Доля списаний, %", format="%.1f", help="Списания / (себестоимость продаж + списания)"
        ),
    },
)
ui.footer()
