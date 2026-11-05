"""Экран «Ассортимент»: ABC по выручке и прибыли, XYZ, матрица, динамика спроса."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
import plotly.express as px
import streamlit as st
from components import ui

from asa import abc
from asa import repository as repo
from asa.analysis import XYZ_WEEKS
from asa.xyz import full_weeks

ui.page_header(
    "Ассортимент",
    "ABC и XYZ считаются по сети в целом. Класс — повод для анализа, а не основание "
    "выводить товар из ассортимента.",
)
d0, d1 = ui.current_period()

with st.expander("Настройки классификации", expanded=False):
    c = st.columns(5)
    ss = st.session_state
    c[0].slider("Граница A, % накопленного вклада", 50, 90, ss.get("cfg_abc_a", 80), key="abc_a")
    c[1].slider("Граница B, % накопленного вклада", 60, 99, ss.get("cfg_abc_b", 95), key="abc_b")
    c[2].slider("X: коэффициент вариации до, %", 5, 30, ss.get("cfg_xyz_x", 10), key="xyz_x")
    c[3].slider("Y: коэффициент вариации до, %", 10, 60, ss.get("cfg_xyz_y", 25), key="xyz_y")
    c[4].checkbox(
        "Убрать линейный тренд (сезонность)",
        value=ss.get("cfg_xyz_detrend", False),
        key="xyz_detrend",
        help="Коэффициент вариации считается по отклонениям от линейного тренда",
    )
    # Копия настроек вне виджетов: Streamlit удаляет состояние виджетов при переходе на другой экран,
    # а пороги должны действовать на всех экранах (рекомендации, отчёты).
    for key in ("abc_a", "abc_b", "xyz_x", "xyz_y", "xyz_detrend"):
        ss[f"cfg_{key}"] = ss[key]
    st.caption(
        f"ABC — за выбранный период. XYZ — по недельным продажам за последние {XYZ_WEEKS} полных недель "
        "до конца периода; недели, когда товар был доступен меньше чем в 80% рабочих точко-дней, "
        "исключаются — низкие продажи в них не означают низкий спрос."
    )

p = ui.analysis_params()
if not (p["a"] < p["b"]) or not (p["x"] < p["y"]):
    st.error("Граница A должна быть меньше границы B, а порог X — меньше порога Y.")
    ui.footer()
    st.stop()

df = ui.product_analysis()

cols = st.columns([4, 4, 4])
with cols[0]:
    summ = abc.summary(
        df.rename(
            columns={"abc_revenue": "abc_class", "revenue_share": "share", "revenue": "value"}
        )
    )
    st.markdown("**ABC по выручке**")
    st.dataframe(
        ui.to_display(summ).assign(share=lambda x: x["share"] * 100),
        hide_index=True,
        width="stretch",
        column_config={
            "abc_class": "Класс",
            "products": "Товаров",
            "value": st.column_config.NumberColumn("Выручка, ₽", format="localized"),
            "share": st.column_config.NumberColumn("Доля, %", format="%.1f"),
        },
    )
with cols[1]:
    summ = abc.summary(
        df.rename(columns={"abc_profit": "abc_class", "gp_share": "share", "gross_profit": "value"})
    )
    st.markdown("**ABC по валовой прибыли**")
    st.dataframe(
        ui.to_display(summ).assign(share=lambda x: x["share"] * 100),
        hide_index=True,
        width="stretch",
        column_config={
            "abc_class": "Класс",
            "products": "Товаров",
            "value": st.column_config.NumberColumn("Прибыль, ₽", format="localized"),
            "share": st.column_config.NumberColumn("Доля, %", format="%.1f"),
        },
    )
with cols[2]:
    st.markdown("**Матрица ABC (выручка) × XYZ, товаров**")
    matrix = (
        pd.crosstab(df["abc_revenue"], df["xyz_class"].fillna("—"))
        .reindex(index=["A", "B", "C"])
        .fillna(0)
    )
    matrix.index.name = "ABC \\ XYZ"
    st.dataframe(matrix.astype(int), width="stretch")
    differs = int((df["abc_revenue"] != df["abc_profit"]).sum())
    st.caption(
        f"У {differs} товаров класс по выручке и по прибыли различается — поэтому классификации не смешиваются."
    )

f = st.columns(4)
cats = ui.cached_categories()
f_cat = f[0].multiselect("Категория", cats["name"], placeholder="Все")
f_abc = f[1].multiselect("ABC (выручка)", ["A", "B", "C"], placeholder="Любой")
f_xyz = f[2].multiselect("XYZ", ["X", "Y", "Z"], placeholder="Любой")
f_text = f[3].text_input("Товар", placeholder="название или артикул")
view = df
if f_cat:
    view = view[view["category_name"].isin(f_cat)]
if f_abc:
    view = view[view["abc_revenue"].isin(f_abc)]
if f_xyz:
    view = view[view["xyz_class"].isin(f_xyz)]
if f_text:
    t = f_text.strip().lower()
    view = view[
        view["name"].str.lower().str.contains(t, regex=False)
        | view["sku"].str.lower().str.contains(t)
    ]
view = view.sort_values(["revenue", "product_id"], ascending=[False, True]).reset_index(drop=True)

table = ui.to_display(
    pd.DataFrame(
        {
            "Артикул": view["sku"],
            "Товар": view["name"],
            "Категория": view["category_name"],
            "Продано, шт": view["net_qty"],
            "Выручка, ₽": view["revenue"],
            "Валовая прибыль, ₽": view["gross_profit"],
            "Маржа, %": ui.pct_col(view["gross_margin"]),
            "ABC выручка": view["abc_revenue"],
            "ABC прибыль": view["abc_profit"],
            "XYZ": view["xyz_class"].fillna("—"),
            "CV, %": ui.pct_col(view["cv"]),
            "Недель": view["weeks_used"],
            "Пометка": (
                view["xyz_note"].fillna("") + " " + view["abc_profit_note"].fillna("")
            ).str.strip(),
        }
    )
)
event = st.dataframe(
    table,
    hide_index=True,
    height=420,
    on_select="rerun",
    selection_mode="single-row",
    key="assort_table",
    column_config={
        "Выручка, ₽": st.column_config.NumberColumn(format="localized"),
        "Валовая прибыль, ₽": st.column_config.NumberColumn(format="localized"),
        "Продано, шт": st.column_config.NumberColumn(format="localized"),
        "Маржа, %": st.column_config.NumberColumn(format="%.1f"),
        "CV, %": st.column_config.NumberColumn(
            format="%.1f", help="Коэффициент вариации недельных продаж"
        ),
    },
)
st.caption(
    f"Показано {len(view)} из {len(df)} товаров. Выберите строку, чтобы увидеть динамику спроса."
)


@st.cache_data(show_spinner=False, ttl=600)
def weekly(w0, w1):
    return repo.weekly_demand(ui.get_conn(), w0, w1)


if event and event.selection.rows:
    row = view.iloc[event.selection.rows[0]]
    data_start = ui.cached_period()[0]
    weeks = full_weeks(max(data_start, d1 - timedelta(weeks=XYZ_WEEKS) + timedelta(days=1)), d1)
    if weeks:
        w = weekly(*weeks)
        w = ui.to_display(w[w["product_id"] == row["product_id"]])
        w["Неделя пригодна"] = w["availability"].map(
            lambda a: "да" if a >= 0.8 else "нет — товара часто не было"
        )
        fig = px.bar(
            w,
            x="week_start",
            y="net_qty",
            color="Неделя пригодна",
            color_discrete_map={
                "да": ui.PALETTE["accent"],
                "нет — товара часто не было": ui.PALETTE["warn"],
            },
        )
        fig.update_layout(
            title=f"Недельный спрос: {row['name']} · XYZ {row['xyz_class'] or '—'}",
            height=300,
            xaxis_title=None,
            yaxis_title="Продано, шт",
        )
        fig.update_xaxes(tickformat="%d.%m")
        st.plotly_chart(fig, width="stretch")
ui.footer()
