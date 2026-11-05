"""Экран «Прибыльность»: маржинальность по товарам, категориям, точкам и проблемные позиции."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from components import ui

from asa import metrics, queries
from asa import repository as repo

ui.page_header(
    "Прибыльность",
    "Маржинальность — валовая: выручка минус себестоимость проданного. "
    "Аренда, персонал и другие расходы не учитываются.",
)
d0, d1 = ui.current_period()
stores = ui.current_stores()


@st.cache_data(show_spinner=False, ttl=600)
def by(grain, d0, d1, stores):
    return metrics.enrich_sales(
        repo.sales_aggregates(ui.get_conn(), d0, d1, grain, store_ids=stores)
    )


@st.cache_data(show_spinner=False, ttl=600)
def store_margin(d0, d1):
    return queries.run(ui.get_conn(), 4, d0, d1)


net = by("network", d0, d1, stores).iloc[0]
net_margin = net.gross_margin
c1, c2 = st.columns(2)
with c1:
    cat = ui.to_display(by("category", d0, d1, stores)).sort_values("gross_margin")
    fig = px.bar(
        cat,
        x=cat["gross_margin"] * 100,
        y="category_name",
        orientation="h",
        color_discrete_sequence=[ui.PALETTE["accent"]],
        custom_data=["revenue", "gross_profit"],
    )
    fig.update_traces(
        hovertemplate="%{y}<br>Маржа %{x:.1f}%<br>Выручка %{customdata[0]:,.0f} ₽"
        "<br>Прибыль %{customdata[1]:,.0f} ₽<extra></extra>"
    )
    if net_margin is not None:
        fig.add_vline(
            x=float(net_margin) * 100,
            line_dash="dash",
            line_color=ui.PALETTE["muted"],
            annotation_text="сеть",
            annotation_position="top",
        )
    fig.update_layout(
        title="Маржинальность по категориям, %",
        height=320,
        xaxis_title=None,
        yaxis_title=None,
        xaxis_ticksuffix="%",
    )
    st.plotly_chart(fig, width="stretch")
with c2:
    sm = ui.to_display(store_margin(d0, d1)).sort_values("gross_margin")
    fig = px.bar(
        sm,
        x=sm["diff_from_network"] * 100,
        y="store_name",
        orientation="h",
        color=sm["diff_from_network"] < 0,
        color_discrete_map={True: ui.PALETTE["warn"], False: ui.PALETTE["accent"]},
    )
    fig.update_layout(
        title="Точки: отклонение маржинальности от сети, п. п.",
        height=320,
        showlegend=False,
        xaxis_title=None,
        yaxis_title=None,
    )
    st.plotly_chart(fig, width="stretch")
    st.caption("SQL-задача 4 · по всей сети, без фильтра точек")

st.subheader("Маржинальность по товарам")
prod = by("product", d0, d1, stores)
gap = st.slider("Проблемная позиция: маржа ниже сетевой более чем на, п. п.", 1, 20, 5)
prod["problem"] = [
    (
        "Убыток"
        if gp < 0
        else "Маржа ниже сети"
        if m is not None and net_margin is not None and m < net_margin - metrics.D(gap) / 100
        else ""
    )
    for gp, m in zip(prod["gross_profit"], prod["gross_margin"], strict=True)
]
p_disp = ui.to_display(prod)
fig = px.scatter(
    p_disp,
    x="revenue",
    y=p_disp["gross_margin"] * 100,
    color="category_name",
    hover_name="product_name",
    size=p_disp["gross_profit"].clip(lower=1),
    size_max=22,
    log_x=True,
    labels={
        "revenue": "Выручка, ₽ (логарифмическая шкала)",
        "y": "Маржа, %",
        "category_name": "Категория",
    },
)
if net_margin is not None:
    fig.add_hline(
        y=float(net_margin) * 100 - gap,
        line_dash="dash",
        line_color=ui.PALETTE["warn"],
        annotation_text=f"сеть − {gap} п. п.",
        annotation_position="bottom right",
    )
fig.update_layout(height=380, yaxis_ticksuffix="%")
st.plotly_chart(fig, width="stretch")

only_problems = st.toggle("Только проблемные позиции", value=True)
tbl = prod[prod["problem"] != ""] if only_problems else prod
tbl = tbl.sort_values(
    "gross_margin", key=lambda s: s.map(lambda v: float(v) if v is not None else 9)
)
st.dataframe(
    ui.to_display(
        pd.DataFrame(
            {
                "Артикул": tbl["sku"],
                "Товар": tbl["product_name"],
                "Категория": tbl["category_name"],
                "Выручка, ₽": tbl["revenue"],
                "Валовая прибыль, ₽": tbl["gross_profit"],
                "Маржа, %": ui.pct_col(tbl["gross_margin"]),
                "Отклонение от сети, п. п.": tbl["gross_margin"].map(
                    lambda m: (
                        float(m - net_margin) * 100
                        if m is not None and net_margin is not None
                        else None
                    )
                ),
                "Проблема": tbl["problem"],
            }
        )
    ),
    hide_index=True,
    width="stretch",
    height=360,
    column_config={
        "Выручка, ₽": st.column_config.NumberColumn(format="localized"),
        "Валовая прибыль, ₽": st.column_config.NumberColumn(format="localized"),
        "Маржа, %": st.column_config.NumberColumn(format="%.1f"),
        "Отклонение от сети, п. п.": st.column_config.NumberColumn(format="%+.1f"),
    },
)
st.caption(f"Позиций: {len(tbl)}. Маржинальность сети за период: {ui.fmt_pct(net_margin)}.")
ui.footer()
