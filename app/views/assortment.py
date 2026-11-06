"""Разбор → «Ассортимент»: понятные группы товаров; ABC/XYZ, матрица и спрос — в «Подробнее»."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
import plotly.express as px
import streamlit as st
from components import ui

from asa import abc
from asa import recommendations as rec
from asa import repository as repo
from asa.analysis import XYZ_WEEKS
from asa.xyz import full_weeks

ui.page_header(
    "Какие товары тянут продажи",
    "Товары разбиты на понятные группы; профессиональный анализ ABC/XYZ — в блоке «Подробнее». "
    "Класс — повод для анализа, а не основание выводить товар из ассортимента.",
)
d0, d1 = ui.current_period()
ui.scope_note(
    "Ассортимент анализируется по всей сети — фильтр точек здесь не применяется."
    if ui.current_stores()
    else "Ассортимент анализируется по всей сети."
)
tab_groups = st.container()
tab_pro = st.expander("Подробнее: профессиональный режим ABC / XYZ")

with tab_pro:  # noqa: SIM117 — настройки внутри вкладки, затем блок валидации вне её
    with st.container(border=True):
        st.markdown("**Настройки классификации**")
        c = st.columns(5)
        ss = st.session_state
        c[0].slider(
            "Граница A, % накопленного вклада", 50, 90, ss.get("cfg_abc_a", 80), key="abc_a"
        )
        c[1].slider(
            "Граница B, % накопленного вклада", 60, 99, ss.get("cfg_abc_b", 95), key="abc_b"
        )
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
recs = rec.build(df)
rules_by_product = recs.groupby("product_id")["rule"].apply(lambda r: sorted(set(r))).to_dict()
df = df.assign(rules=df["product_id"].map(lambda p: rules_by_product.get(p, [])))
GROUPS = {
    "Основные источники выручки": ("класс A: вместе дают около 80% выручки", lambda d: d["abc_revenue"] == "A"),
    "Стабильный спрос": ("класс X: недельные продажи колеблются меньше чем на 10%", lambda d: d["xyz_class"] == "X"),
    "Нестабильный спрос": ("классы Y и Z: продажи заметно меняются от недели к неделе",
                           lambda d: d["xyz_class"].isin(["Y", "Z"])),
    "Высокая доля списаний": ("правило R3: ≥ 20% выпуска и выше медианы категории на 15+ п. п.",
                              lambda d: d["rules"].map(lambda r: "R3" in r)),
    "Требуют проверки": ("есть хотя бы одна задача (правила R1–R5)", lambda d: d["rules"].map(bool)),
}  # fmt: skip
XYZ_WORD = {"X": "стабильный", "Y": "колеблется", "Z": "нестабильный"}


@st.cache_data(show_spinner=False, ttl=600)
def weekly(w0, w1):
    return repo.weekly_demand(ui.get_conn(), w0, w1)


def demand_chart(row) -> None:
    data_start = ui.cached_period()[0]
    weeks = full_weeks(max(data_start, d1 - timedelta(weeks=XYZ_WEEKS) + timedelta(days=1)), d1)
    if not weeks:
        return
    w = weekly(*weeks)
    w = ui.to_display(w[w["product_id"] == row["product_id"]])
    w["Неделя"] = w["availability"].map(
        lambda a: "учтена в оценке спроса" if a >= 0.8 else "не учтена: товара часто не было"
    )
    fig = px.bar(
        w,
        x="week_start",
        y="net_qty",
        color="Неделя",
        color_discrete_map={
            "учтена в оценке спроса": ui.PALETTE["accent"],
            "не учтена: товара часто не было": ui.PALETTE["warn"],
        },
    )
    fig.update_layout(
        title=f"Недельный спрос, шт: {row['name']} · {XYZ_WORD.get(row['xyz_class'], 'мало данных')}",
        height=300,
        xaxis_title=None,
        yaxis_title=None,
    )
    fig.update_xaxes(tickformat="%d.%m")
    st.plotly_chart(fig, width="stretch")
    for r in recs[recs["product_id"] == row["product_id"]].itertuples(index=False):
        ui.box(f"<b>{r.rule} · {r.problem}.</b> {r.value}. <b>Проверить:</b> {r.action}.", "warn")


with tab_groups:
    total_rev = sum(df["revenue"])
    gc = st.columns(len(GROUPS))
    for i, (name, (desc, test)) in enumerate(GROUPS.items()):
        part = df[test(df)]
        gc[i].metric(
            name,
            f"{len(part)} товаров",
            f"{ui.fmt_pct(sum(part['revenue']) / total_rev if total_rev else None)} выручки",
            delta_color="off",
            delta_arrow="off",
            help=desc,
        )
    st.caption(
        "Товар может входить в несколько групп. Группы строятся по действующей методике (класс A, классы "
        "X/Y/Z, правило R3, задачи R1–R5); новых порогов не вводилось."
    )
    grp = st.segmented_control(
        "Показать группу", ["Все товары", *GROUPS], default="Все товары", key="grp"
    )
    gv = df if grp in (None, "Все товары") else df[GROUPS[grp][1](df)]
    gv = gv.sort_values(["revenue", "product_id"], ascending=[False, True]).reset_index(drop=True)
    gshow = pd.DataFrame(
        {
            "Товар": gv["name"],
            "Категория": gv["category_name"],
            "Выручка, ₽": gv["revenue"],
            "Доля в выручке": gv["revenue_share"],
            "Маржа": gv["gross_margin"],
            "Спрос": gv["xyz_class"].map(
                lambda z: f"{XYZ_WORD[z]} ({z})" if z in XYZ_WORD else "мало данных"
            ),
            "Доля списаний": gv["write_off_share"],
            "Задачи": gv["rules"].map(lambda r: ", ".join(r) if r else "нет"),
        }
    )
    gf = {"Выручка, ₽": "rub", "Доля в выручке": "pct", "Маржа": "pct", "Доля списаний": "pct"}
    gev = st.dataframe(
        ui.styled(gshow, gf),
        hide_index=True,
        height=420,
        on_select="rerun",
        selection_mode="single-row",
        key="grp_table",
        column_config={
            **ui.num_cfg(gf),
            "Спрос": st.column_config.TextColumn(help=ui.HELP["cv"]),
            "Доля списаний": st.column_config.TextColumn(help=ui.HELP["ws"], alignment="right"),
        },
    )
    st.caption(f"{len(gv)} товаров. Выберите строку — появится недельный спрос и задачи по товару.")
    if gev and gev.selection.rows:
        demand_chart(gv.iloc[gev.selection.rows[0]])


with tab_pro:
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
            df.rename(
                columns={"abc_profit": "abc_class", "gp_share": "share", "gross_profit": "value"}
            )
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
    view = view.sort_values(["revenue", "product_id"], ascending=[False, True]).reset_index(
        drop=True
    )

    table = pd.DataFrame(
        {
            "Артикул": view["sku"],
            "Товар": view["name"],
            "Категория": view["category_name"],
            "Продано, шт": view["net_qty"],
            "Выручка, ₽": view["revenue"],
            "Валовая прибыль, ₽": view["gross_profit"],
            "Маржа": view["gross_margin"],
            "ABC выручка": view["abc_revenue"],
            "ABC прибыль": view["abc_profit"],
            "XYZ": view["xyz_class"].fillna("—"),
            "CV": view["cv"],
            "Недель": view["weeks_used"],
            "Пометка": (
                view["xyz_note"].fillna("") + " " + view["abc_profit_note"].fillna("")
            ).str.strip(),
        }
    )
    tf = {
        "Продано, шт": "int",
        "Выручка, ₽": "rub",
        "Валовая прибыль, ₽": "rub",
        "Маржа": "pct",
        "CV": "pct",
        "Недель": "int",
    }
    event = st.dataframe(
        ui.styled(table, tf),
        hide_index=True,
        height=420,
        on_select="rerun",
        selection_mode="single-row",
        key="assort_table",
        column_config={
            **ui.num_cfg(tf),
            "CV": st.column_config.TextColumn(help=ui.HELP["cv"], alignment="right"),
        },
    )
    st.caption(
        f"Показано {len(view)} из {len(df)} товаров. Выберите строку, чтобы увидеть динамику спроса."
    )

    if event and event.selection.rows:
        demand_chart(view.iloc[event.selection.rows[0]])
ui.footer()
