"""Экран «Задачи на проверку»: управленческие рекомендации по правилам ТЗ §25 в виде списка задач."""

from __future__ import annotations

import streamlit as st
from components import ui

from asa import recommendations as rec

ui.page_header(
    "Задачи на проверку",
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

st.caption(
    f"Показано {min(len(view), 60)} из {len(view)} (всего задач {len(recs)}). Сначала — высокая важность."
)
LVL = {"Высокая": "crit", "Средняя": "warn", "Низкая": "info"}
for r in view.head(60).itertuples(index=False):
    with st.container(border=True):
        st.markdown(
            f"<span class='ux-pill {LVL[r.severity]}'>Важность: {r.severity.lower()}</span> "
            f"**{r.product_name}** · {r.category_name} · правило {r.rule} · артикул {r.sku}",
            unsafe_allow_html=True,
        )
        c = st.columns(4)
        c[0].markdown(f"**Проблема**  \n{r.problem}")
        c[1].markdown(
            f"**Доказательство**  \n{r.value}  \n<small>{r.basis}</small>", unsafe_allow_html=True
        )
        c[2].markdown(
            f"**Что проверить**  \n{r.action}  \n<small>Возможная причина: {r.possible_cause}</small>",
            unsafe_allow_html=True,
        )
        c[3].markdown(f"**Ограничения**  \n{r.limitations}")
if len(view) > 60:
    st.info("Показаны первые 60 задач. Полный список — выгрузка на экране «Методика и отчёты».")
ui.footer()
