"""Экран «Задачи на проверку»: управленческие рекомендации по правилам ТЗ §25 в виде списка задач."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from components import ui

from asa import recommendations as rec

ui.page_header(
    "Что проверить",
    "Каждая задача — что проверить, почему и с какими ограничениями. Задачи не утверждают причину "
    "и не предлагают выводить товар из ассортимента только по классу ABC/XYZ.",
)
ui.scope_note(
    "Задачи формируются по всей сети за выбранный период: фильтр точек здесь не применяется."
    if ui.current_stores()
    else "Задачи формируются по всей сети за выбранный период."
)

recs = rec.build(ui.product_analysis())
k = st.columns(4)
for i, sev in enumerate(("Высокая", "Средняя", "Низкая")):
    k[i].metric(
        f"Важность: {sev.lower()}",
        ui.fmt_num((recs["severity"] == sev).sum()),
        {
            "Высокая": "проверить в первую очередь",
            "Средняя": "в плановом порядке",
            "Низкая": "к сведению",
        }[sev],
        delta_color="off",
        delta_arrow="off",
    )
k[3].metric("Товаров с задачами", ui.fmt_num(recs["product_id"].nunique()))

# Переход с главной передаёт готовый фильтр.
for key, preset in (("rc_sev", "rc_preset_sev"), ("rc_rule", "rc_preset_rule")):
    if preset in st.session_state:
        st.session_state[key] = st.session_state.pop(preset)
f = st.columns(3)
f_sev = f[0].multiselect(
    "Важность", ["Высокая", "Средняя", "Низкая"], placeholder="Любая", key="rc_sev"
)
f_rule = f[1].multiselect(
    "Правило",
    list(rec.RULE_TITLES),
    format_func=lambda r: f"{r}. {rec.RULE_TITLES[r]}",
    placeholder="Любое",
    key="rc_rule",
)
f_cat = f[2].multiselect("Категория", ui.cached_categories()["name"], placeholder="Все")
view = recs
if f_sev:
    view = view[view["severity"].isin(f_sev)]
if f_rule:
    view = view[view["rule"].isin(f_rule)]
if f_cat:
    view = view[view["category_name"].isin(f_cat)]

view = view.reset_index(drop=True)
table = pd.DataFrame(
    {
        "Важность": view["severity"],
        "Товар": view["product_name"],
        "Категория": view["category_name"],
        "Проблема": view["problem"],
        "Доказательство": view["value"],
        "Что проверить": view["action"],
    }
)
event = st.dataframe(
    table,
    hide_index=True,
    width="stretch",
    height=430,
    on_select="rerun",
    selection_mode="single-row",
    key="rc_table",
    column_config={
        "Важность": st.column_config.TextColumn(width="small"),
        "Проблема": st.column_config.TextColumn(width="medium"),
        "Доказательство": st.column_config.TextColumn(width="medium"),
        "Что проверить": st.column_config.TextColumn(width="large"),
    },
)
st.caption(
    f"Задач: {len(view)} из {len(recs)}. Выберите строку — ниже появятся основание, возможная причина и ограничения."
)
if event and event.selection.rows:
    r = view.iloc[event.selection.rows[0]]
    ui.box(
        f"<b>{r['product_name']}</b> · {r['category_name']} · правило {r['rule']} · важность: {r['severity'].lower()}<br>"
        f"<b>Основание:</b> {r['basis']}<br><b>Доказательство:</b> {r['value']}<br>"
        f"<b>Возможная причина (не установлена):</b> {r['possible_cause']}<br>"
        f"<b>Что проверить:</b> {r['action']}<br><b>Ограничения:</b> {r['limitations']}",
        "warn" if r["severity"] != "Низкая" else "",
    )
ui.footer()
