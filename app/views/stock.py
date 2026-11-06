"""Экран «Списания: где теряем деньги»: потери, доля списаний, проблемные товары, причины, точки."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from components import ui

from asa import metrics
from asa import recommendations as rec
from asa import repository as repo

ui.page_header("Списания: где и сколько денег теряется", ui.period_caption())
ui.box(
    "<b>Как считается доля списаний.</b> <code>доля списаний = стоимость списаний / (себестоимость "
    "проданного + стоимость списаний)</code>. Знаменатель — себестоимость всего выпуска: и проданного, "
    "и списанного. Списания оцениваются по себестоимости на дату списания."
)
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
    "Потери на списаниях",
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

ui.level(
    "Внимание",
    "Товары с наибольшими потерями",
    "Доля списаний сравнивается с медианой своей категории: у свежей продукции списания выше по природе.",
)
if stores:
    ui.scope_note("Товарные показатели — по всей сети: фильтр точек к этой таблице не применяется.")
a = ui.product_analysis()
share = a["write_off_share"].map(
    lambda v: float(v) if v is not None and not pd.isna(v) else float("nan")
)
med = share.groupby(a["category_name"]).median()
a = a.assign(cat_median=a["category_name"].map(med), dev=share - a["category_name"].map(med))
rules = rec.build(a).groupby("product_id")["rule"].apply(set).to_dict()
a = a.assign(rules=a["product_id"].map(lambda p: rules.get(p, set())))
mode = st.radio(
    "Показать",
    ["Все товары по потерям", "Высокие списания (правило R3)", "Часто нет в продаже (правило R2)"],
    horizontal=True,
)
if mode.startswith("Высокие"):
    view = a[a["rules"].map(lambda r: "R3" in r)].sort_values("dev", ascending=False)
elif mode.startswith("Часто"):
    view = a[a["rules"].map(lambda r: "R2" in r)].sort_values("oos_share", ascending=False)
else:
    view = a.sort_values("write_off_cost", ascending=False)
wshow = pd.DataFrame(
    {
        "Товар": view["name"],
        "Категория": view["category_name"],
        "Списано, ₽": view["write_off_cost"],
        "Доля списаний": view["write_off_share"],
        "Медиана категории": view["cat_median"],
        "Отклонение": view["dev"],
        "Нет в продаже": view["oos_share"],
        "Распродано": view["sold_out_share"],
        "Задачи": view["rules"].map(lambda r: ", ".join(sorted(r)) if r else "нет"),
    }
)
wf = {
    "Списано, ₽": "rub",
    "Доля списаний": "pct",
    "Медиана категории": "pct",
    "Отклонение": "pp",
    "Нет в продаже": "pct",
    "Распродано": "pct",
}
st.dataframe(
    ui.styled(wshow, wf),
    hide_index=True,
    width="stretch",
    height=360,
    column_config={
        **ui.num_cfg(wf),
        "Доля списаний": st.column_config.TextColumn(help=ui.HELP["ws"], alignment="right"),
        "Нет в продаже": st.column_config.TextColumn(help=ui.HELP["oos"], alignment="right"),
        "Распродано": st.column_config.TextColumn(help=ui.HELP["soldout"], alignment="right"),
    },
)
st.caption(
    f"Позиций: {len(view)}. Связь списаний с объёмом производства — гипотеза, её нужно проверить на месте."
)

with st.expander("Подробнее: причины, динамика, категории и точки"):
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
        fig.update_layout(
            title="Причины списаний, ₽", height=280, xaxis_title=None, yaxis_title=None
        )
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
            metrics.write_off_share(a, b)
            for a, b in zip(m["write_off_cost"], m["cogs"], strict=True)
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

ui.footer()
