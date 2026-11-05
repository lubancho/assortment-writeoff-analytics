"""Экран «Рекомендации»: управленческие рекомендации по правилам ТЗ §25."""

from __future__ import annotations

import streamlit as st
from components import ui

from asa import recommendations as rec

ui.page_header(
    "Рекомендации",
    "Рекомендации говорят, что проверить, и не утверждают причину. "
    "Ни одна не предлагает вывести товар из ассортимента только по классу ABC/XYZ.",
)

recs = rec.build(ui.product_analysis())
k = st.columns(4)
for i, sev in enumerate(("Высокая", "Средняя", "Низкая")):
    k[i].metric(f"Важность: {sev.lower()}", ui.fmt_num((recs["severity"] == sev).sum()))
k[3].metric("Товаров с рекомендациями", ui.fmt_num(recs["product_id"].nunique()))

f = st.columns(3)
f_sev = f[0].multiselect("Важность", ["Высокая", "Средняя", "Низкая"], placeholder="Любая")
f_rule = f[1].multiselect(
    "Правило",
    list(rec.RULE_TITLES),
    format_func=lambda r: f"{r}. {rec.RULE_TITLES[r]}",
    placeholder="Любое",
)
f_cat = f[2].multiselect("Категория", ui.cached_categories()["name"], placeholder="Все")
view = recs
if f_sev:
    view = view[view["severity"].isin(f_sev)]
if f_rule:
    view = view[view["rule"].isin(f_rule)]
if f_cat:
    view = view[view["category_name"].isin(f_cat)]

st.caption(f"Показано {len(view)} из {len(recs)}.")
ICON = {"Высокая": "🔴", "Средняя": "🟠", "Низкая": "⚪"}
for r in view.head(60).itertuples(index=False):
    with st.expander(f"{ICON[r.severity]} {r.problem} — {r.product_name} ({r.category_name})"):
        c = st.columns([1, 1])
        c[0].markdown(f"**Основание в данных.** {r.basis}")
        c[0].markdown(f"**Значение показателя.** {r.value}")
        c[0].markdown(f"**Возможная причина.** {r.possible_cause}")
        c[1].markdown(f"**Рекомендуемое действие.** {r.action}")
        c[1].markdown(f"**Ограничения интерпретации.** {r.limitations}")
        c[1].caption(f"Правило {r.rule} · важность: {r.severity.lower()} · артикул {r.sku}")
if len(view) > 60:
    st.info("Показаны первые 60 рекомендаций. Полный список — на экране «Отчёты».")
ui.footer()
