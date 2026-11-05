"""Экран «Остатки и списания»: оборачиваемость, доступность, списания по причинам, точкам, категориям."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from components import ui

from asa import metrics
from asa import repository as repo

ui.page_header("Остатки и списания", ui.period_caption())
d0, d1 = ui.current_period()
stores = ui.current_stores()


@st.cache_data(show_spinner=False, ttl=600)
def wo(grain, d0, d1, stores):
    return repo.write_off_aggregates(ui.get_conn(), d0, d1, grain, store_ids=stores)


@st.cache_data(show_spinner=False, ttl=600)
def stock(grain, d0, d1, stores):
    return repo.stock_aggregates(ui.get_conn(), d0, d1, grain, store_ids=stores)


@st.cache_data(show_spinner=False, ttl=600)
def sales(grain, d0, d1, stores):
    return metrics.enrich_sales(
        repo.sales_aggregates(ui.get_conn(), d0, d1, grain, store_ids=stores)
    )


w_net, s_net, st_net = (
    wo("network", d0, d1, stores).iloc[0],
    sales("network", d0, d1, stores).iloc[0],
    stock("network", d0, d1, stores).iloc[0],
)
k = st.columns(5)
k[0].metric(
    "Стоимость списаний",
    ui.fmt_rub(w_net.write_off_cost),
    f"{ui.fmt_num(w_net.write_off_qty)} шт",
    delta_color="off",
    delta_arrow="off",
)
k[1].metric(
    "Доля списаний",
    ui.fmt_pct(metrics.write_off_share(w_net.write_off_cost, s_net.cogs)),
    help="Списания / (себестоимость продаж + списания) — доля себестоимости выпуска, ушедшая в списание",
)
k[2].metric(
    "Оборачиваемость",
    ui.fmt_num(metrics.turnover(s_net.cogs, st_net.available_value_sum, st_net.days), 1) + " раз",
    help="Себестоимость продаж за период / средний дневной запас, доступный к продаже",
)
k[3].metric(
    "Дни запаса на конец",
    ui.fmt_num(metrics.days_of_supply(st_net.closing_value_end, s_net.cogs, st_net.days), 1),
    help="Остаток на конец периода / средняя дневная себестоимость продаж. Свежая продукция "
    "остатка на следующий день не имеет",
)
k[4].metric(
    "Нет в продаже",
    ui.fmt_pct(metrics.out_of_stock_share(st_net.unavailable_days, st_net.open_days)),
    f"распродано к закрытию: {ui.fmt_pct(metrics.sold_out_share(st_net.sold_out_days, st_net.open_days))}",
    delta_color="off",
    delta_arrow="off",
    help="Доля рабочих точко-дней, когда товара не было в продаже. «Распродано» — к закрытию "
    "ничего не осталось; для свежей продукции это может быть и точным планированием",
)

c1, c2 = st.columns(2)
with c1:
    by_reason = ui.to_display(wo("reason", d0, d1, stores))
    by_reason["Причина"] = by_reason["reason"].map(ui.REASON_LABEL)
    fig = px.bar(
        by_reason.sort_values("write_off_cost"),
        x="write_off_cost",
        y="Причина",
        orientation="h",
        color_discrete_sequence=[ui.PALETTE["accent"]],
        text_auto=",.0f",
    )
    fig.update_layout(title="Причины списаний, ₽", height=280, xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig, width="stretch")
with c2:
    day = ui.to_display(wo("day", d0, d1, stores))
    fig = go.Figure()
    fig.add_scatter(
        x=day["write_off_date"],
        y=day["write_off_cost"],
        name="Списания за день",
        line={"color": ui.PALETTE["warn"], "width": 2},
    )
    fig.update_layout(title="Динамика списаний, ₽", height=280, yaxis_tickformat=",.0f")
    fig.update_xaxes(tickformat="%d.%m", hoverformat="%d.%m.%Y")
    st.plotly_chart(fig, width="stretch")

c3, c4 = st.columns(2)
for col, grain, title, label in (
    (c3, "category", "Списания по категориям", "category_name"),
    (c4, "store", "Списания по точкам", "store_name"),
):
    w = wo(grain, d0, d1, stores)
    s = sales(grain, d0, d1, stores)
    key = "category_id" if grain == "category" else "store_id"
    m = w.merge(s[[key, "cogs"]], on=key, how="left")
    m["share"] = [
        metrics.write_off_share(a, b) for a, b in zip(m["write_off_cost"], m["cogs"], strict=True)
    ]
    m = ui.to_display(m).sort_values("share")
    fig = px.bar(
        m,
        x=m["share"] * 100,
        y=label,
        orientation="h",
        color_discrete_sequence=[ui.PALETTE["accent2"]],
        custom_data=["write_off_cost"],
    )
    fig.update_traces(
        hovertemplate="%{y}<br>Доля %{x:.1f}%<br>Списано %{customdata[0]:,.0f} ₽<extra></extra>"
    )
    fig.update_layout(
        title=f"{title}: доля в себестоимости выпуска, %",
        height=360 if grain == "store" else 280,
        xaxis_title=None,
        yaxis_title=None,
        xaxis_ticksuffix="%",
    )
    col.plotly_chart(fig, width="stretch")

st.subheader("Товары с отклонениями")
st.caption(
    "Сравнение доли списаний — с медианой своей категории: у свежей продукции списания выше по природе. "
    "Показатели — по сети в целом."
)
a = ui.product_analysis()
share = a["write_off_share"].map(
    lambda v: float(v) if v is not None and not pd.isna(v) else float("nan")
)
med = share.groupby(a["category_name"]).median()
a = a.assign(cat_median=a["category_name"].map(med), dev=share - a["category_name"].map(med))
mode = st.radio(
    "Показать", ["Высокие списания", "Частое отсутствие товара", "Все товары"], horizontal=True
)
if mode == "Высокие списания":
    view = a[a["dev"] >= 0.15].sort_values("dev", ascending=False)
elif mode == "Частое отсутствие товара":
    view = a[a["oos_share"].map(lambda v: v is not None and float(v) >= 0.03)].sort_values(
        "oos_share", ascending=False
    )
else:
    view = a.sort_values("write_off_cost", ascending=False)
st.dataframe(
    ui.to_display(
        pd.DataFrame(
            {
                "Товар": view["name"],
                "Категория": view["category_name"],
                "Списано, ₽": view["write_off_cost"],
                "Доля списаний, %": ui.pct_col(view["write_off_share"]),
                "Медиана категории, %": view["cat_median"] * 100,
                "Оборачиваемость, раз": view["turnover"],
                "Дни запаса": view["days_of_supply"],
                "Нет в продаже, %": ui.pct_col(view["oos_share"]),
                "Распродано, %": ui.pct_col(view["sold_out_share"]),
                "XYZ": view["xyz_class"].fillna("—"),
            }
        )
    ),
    hide_index=True,
    width="stretch",
    height=360,
    column_config={
        "Списано, ₽": st.column_config.NumberColumn(format="localized"),
        "Доля списаний, %": st.column_config.NumberColumn(format="%.1f"),
        "Медиана категории, %": st.column_config.NumberColumn(format="%.1f"),
        "Оборачиваемость, раз": st.column_config.NumberColumn(format="%.1f"),
        "Дни запаса": st.column_config.NumberColumn(format="%.1f"),
        "Нет в продаже, %": st.column_config.NumberColumn(format="%.1f"),
        "Распродано, %": st.column_config.NumberColumn(format="%.1f"),
    },
)
st.caption(
    f"Позиций: {len(view)}. Связь списаний с объёмом производства — гипотеза, её нужно проверить на месте."
)
ui.footer()
