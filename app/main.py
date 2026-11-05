"""Точка входа веб-интерфейса: streamlit run app/main.py"""

import streamlit as st

st.set_page_config(
    page_title="Анализ продаж, ассортимента и списаний", page_icon="📦", layout="wide"
)

from components.ui import sidebar_filters  # noqa: E402 — set_page_config должен быть первым вызовом

pages = [
    st.Page("views/overview.py", title="Главная", icon=":material/dashboard:", default=True),
    st.Page("views/assortment.py", title="Ассортимент", icon=":material/category:"),
    st.Page("views/profitability.py", title="Прибыльность", icon=":material/payments:"),
    st.Page("views/stock.py", title="Списания: где теряем деньги", icon=":material/inventory_2:"),
    st.Page("views/recommendations.py", title="Задачи на проверку", icon=":material/lightbulb:"),
    st.Page("views/reports.py", title="Методика и отчёты", icon=":material/description:"),
]
nav = st.navigation(pages)
with st.sidebar:
    st.markdown("**Анализ продаж, ассортимента и списаний**  \nдемо-версия на синтетических данных")
sidebar_filters()
nav.run()
