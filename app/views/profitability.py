"""Разбор → «Маржа товаров»: где маржа ниже сети — факт, база сравнения, отклонение, факторы, что проверить."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from components import ui

from asa import metrics, queries
from asa import recommendations as rec
from asa import repository as repo

ui.page_header(
    "Где низкая маржа",
    "Категории, точки и товары с валовой маржинальностью ниже сети. Возможные факторы — гипотезы для "
    "проверки, а не установленные причины. Аренда, персонал и другие расходы не учитываются.",
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
FACTORS = "Структура продаж (больше дешёвых позиций), скидки, рост себестоимости — не установлено"


def below_table(df: pd.DataFrame, name_col: str, label: str, next_step: str) -> None:
    d = df[
        [m is not None and net_margin is not None and m < net_margin for m in df["gross_margin"]]
    ]
    d = d.sort_values("gross_margin", key=lambda s: s.map(float))
    if d.empty:
        st.success(f"{label}: ниже сети нет.")
        return
    show = pd.DataFrame(
        {
            label: d[name_col],
            "Маржа": d["gross_margin"],
            "Сеть": [net_margin] * len(d),
            "Отклонение": [m - net_margin for m in d["gross_margin"]],
            "Прибыль, ₽": d["gross_profit"],
            "Возможные факторы": FACTORS,
            "Что проверить": next_step,
        }
    )
    fm = {"Маржа": "pct", "Сеть": "pct", "Отклонение": "pp", "Прибыль, ₽": "rub"}
    st.dataframe(
        ui.styled(show, fm), hide_index=True, width="stretch", column_config=ui.num_cfg(fm)
    )


ui.level(
    "Внимание",
    "Категории и точки ниже сети",
    f"База сравнения — маржинальность {ui.fmt_pct(net_margin)}.",
)
b1, b2 = st.columns(2)
with b1:
    below_table(by("category", d0, d1, stores), "category_name", "Категория",
                "Отфильтровать товары категории ниже и проверить позиции с низкой маржой")  # fmt: skip
with b2:
    below_table(by("store", d0, d1, None), "store_name", "Точка",
                "Выбрать точку в фильтре и сравнить скидки и структуру продаж с сетью")  # fmt: skip
    if stores:
        st.caption("Точки сравниваются по всей сети — фильтр точек к этой таблице не применяется.")

with st.expander("Подробнее: маржа категорий и точек на графиках"):
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

ui.level(
    "Товары",
    "Товары с низкой маржой",
    "Убыток или маржа ниже сети больше чем на заданный порог (по умолчанию 5 п. п. — как в правиле R1).",
)
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
with st.expander("Профессиональный режим: все товары на карте «выручка × маржа»"):
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
hint = {
    r.product_id: (r.possible_cause, r.action)
    for r in rec.build(ui.product_analysis()).itertuples(index=False)
    if r.rule in ("R1", "R5")
}
pshow = pd.DataFrame(
    {
        "Товар": tbl["product_name"],
        "Категория": tbl["category_name"],
        "Выручка, ₽": tbl["revenue"],
        "Маржа": tbl["gross_margin"],
        "Сеть": [net_margin] * len(tbl),
        "Отклонение": [
            None if m is None or net_margin is None else m - net_margin for m in tbl["gross_margin"]
        ],
        "Проблема": tbl["problem"].replace("", "—"),
        "Возможные факторы": tbl["product_id"].map(
            lambda p: hint.get(
                p, ("Рост себестоимости, скидки или промо, цена ниже рынка — не установлено",)
            )[0]
        ),
        "Что проверить": tbl["product_id"].map(
            lambda p: hint.get(
                p, (None, "Себестоимость (техкарта, закупка), действующую цену и скидки")
            )[1]
        ),
    }
)
pf = {"Выручка, ₽": "rub", "Маржа": "pct", "Сеть": "pct", "Отклонение": "pp"}
st.dataframe(
    ui.styled(pshow, pf), hide_index=True, width="stretch", height=360, column_config=ui.num_cfg(pf)
)
st.caption(f"Позиций: {len(tbl)}. Маржинальность сети за период: {ui.fmt_pct(net_margin)}.")
ui.footer()
