"""Точка входа веб-интерфейса: streamlit run app/main.py"""

import streamlit as st

st.set_page_config(
    page_title="Анализ продаж, ассортимента и списаний", page_icon="📦", layout="wide"
)

from components.ui import sidebar_filters  # noqa: E402 — set_page_config должен быть первым вызовом

# Три основных направления; методика и отчёты — внутри «Аналитики».
pages = {
    "Обзор": [
        st.Page("views/overview.py", title="Обзор", icon=":material/dashboard:", default=True),
    ],
    "Проблемы и рекомендации": [
        st.Page("views/recommendations.py", title="Что проверить", icon=":material/task_alt:"),
        st.Page("views/stock.py", title="Потери на списаниях", icon=":material/inventory_2:"),
        st.Page("views/profitability.py", title="Низкая маржа", icon=":material/payments:"),
    ],
    "Аналитика": [
        st.Page("views/sales.py", title="Продажи и точки", icon=":material/monitoring:"),
        st.Page("views/assortment.py", title="Анализ ассортимента", icon=":material/category:"),
        st.Page("views/reports.py", title="Подробные отчёты", icon=":material/description:"),
        st.Page("views/methodology.py", title="Методика и данные", icon=":material/menu_book:"),
    ],
}
nav = st.navigation(pages)
with st.sidebar:
    st.markdown("**Анализ продаж, ассортимента и списаний**  \nдемо-версия на синтетических данных")
sidebar_filters()
nav.run()
