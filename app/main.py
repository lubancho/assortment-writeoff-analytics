"""Точка входа веб-интерфейса: streamlit run app/main.py"""

import streamlit as st

st.set_page_config(
    page_title="Анализ продаж, ассортимента и списаний", page_icon="📦", layout="wide"
)

from components.ui import filter_bar  # noqa: E402 — set_page_config должен быть первым вызовом

# Одна страница — один вопрос. Боковая панель: «Главное», «Что сделать», «Разбор» и «Справка»;
# методика и отчёты — только в «Справке».
pages = {
    "Главное": [
        st.Page("views/overview.py", title="Обзор", icon=":material/home:", default=True),
    ],
    "Что сделать": [
        st.Page("views/recommendations.py", title="Задачи на проверку", icon=":material/task_alt:"),
    ],
    "Разбор": [
        st.Page("views/sales.py", title="Продажи по точкам", icon=":material/bar_chart:"),
        st.Page("views/assortment.py", title="Ассортимент", icon=":material/grid_view:"),
        st.Page("views/stock.py", title="Списания", icon=":material/delete:"),
        st.Page("views/profitability.py", title="Маржа товаров", icon=":material/payments:"),
    ],
    "Справка": [
        st.Page("views/reports.py", title="Отчёты", icon=":material/description:"),
        st.Page("views/methodology.py", title="Методика", icon=":material/menu_book:"),
    ],
}
nav = st.navigation(pages)
# Боковая панель — только разделы; общие фильтры — в верхней строке.
filter_bar()
nav.run()
