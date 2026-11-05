"""Экран «Методика и отчёты»: формулы и правила, SQL-задачи 1–10 с документацией, сводный отчёт."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st
from components import ui

from asa import queries
from asa import recommendations as rec
from asa import repository as repo
from asa.export import to_csv_bytes, to_xlsx_bytes

ui.page_header("Методика и отчёты", ui.period_caption())
d0, d1 = ui.current_period()
conn = ui.get_conn()

tab0, tab1, tab2 = st.tabs(["Формулы и правила", "SQL-отчёты", "Сводный отчёт по ассортименту"])

with tab0:
    m1, m2 = st.columns(2)
    m1.markdown(
        "**Формулы показателей**\n\n"
        + "\n".join(
            f"- **{name}.** {ui.HELP[key]}"
            for name, key in (
                ("Выручка", "rev"),
                ("Валовая прибыль", "gp"),
                ("Маржинальность", "mg"),
                ("Стоимость списаний", "wo"),
                ("Доля списаний", "ws"),
                ("Средний чек", "check"),
                ("Нет в продаже", "oos"),
                ("Распродано к закрытию", "soldout"),
                ("Оборачиваемость", "turnover"),
                ("Дни запаса", "dos"),
            )
        )
        + "\n\n**ABC.** Товары сортируются по вкладу от большего к меньшему; накопленная доля до товара "
        "меньше 80% — класс A, до 95% — B, остальные — C. Выручка и прибыль классифицируются отдельно.\n\n"
        f"**XYZ.** {ui.HELP['cv']} Окно — 12 полных недель; недели с доступностью ниже 80% не учитываются."
    )
    m2.markdown(
        """
**Правила задач**

- **R1 · Высокая выручка и низкая маржа.** Класс A по выручке и маржа ниже сетевой более чем на 5 п. п.
- **R2 · Стабильный спрос и частое отсутствие.** Спрос X или Y и товара не было в 3% и более рабочих точко-дней.
- **R3 · Высокие списания.** Доля списаний ≥ 20% и выше медианы категории на 15+ п. п. (на 30+ — высокая важность).
- **R4 · Низкий вклад и нестабильный спрос.** Класс C и спрос Z — повод для дополнительной оценки, не для вывода.
- **R5 · Прибыль падает при росте выручки.** Валовая прибыль упала более чем на 3% к предыдущему периоду.

**Ограничения модели**

- Данные синтетические; модель выпуска упрощена — доля списаний свежей продукции выше типичной.
- Маржа валовая: аренда, персонал и логистика не учитываются.
- ABC/XYZ и задачи считаются по сети в целом.
"""
    )

with tab1:
    num = st.selectbox(
        "Запрос", list(queries.TASKS), format_func=lambda n: f"{n}. {queries.TASKS[n].title}"
    )
    task = queries.TASKS[num]
    params = {}
    if num == 6:
        params["by_store"] = st.toggle("По каждой точке отдельно", value=False)
    if num == 7:
        params["threshold"] = st.slider("Порог доли списаний, %", 5, 80, 20) / 100
    if num == 8:
        params["metric"] = st.radio(
            "Показатель",
            ["revenue", "gross_profit"],
            horizontal=True,
            format_func={"revenue": "выручка", "gross_profit": "валовая прибыль"}.get,
        )
    if num == 10:
        params["top"] = st.slider("Сколько товаров", 5, 50, 10)
    df = queries.run(conn, num, d0, d1, **params)
    st.dataframe(ui.to_display(df), hide_index=True, width="stretch", height=380)
    st.caption(f"Строк: {len(df)}. Названия колонок — как в SQL-запросе.")
    with st.expander("Документация и текст запроса"):
        st.text(task.header())
        st.code(task.text(), language="sql")
    c = st.columns(2)
    name = f"sql_{num:02d}_{datetime.now():%Y%m%d_%H%M}"
    c[0].download_button(
        "Скачать XLSX",
        to_xlsx_bytes(
            {"Результат": df},
            {
                "Отчёт": f"{num}. {task.title}",
                "Период": f"{d0:%d.%m.%Y} — {d1:%d.%m.%Y}",
                "Параметры": ", ".join(f"{k}={v}" for k, v in params.items()) or "по умолчанию",
            },
        ),
        f"{name}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=df.empty,
    )
    c[1].download_button(
        "Скачать CSV", to_csv_bytes(df), f"{name}.csv", mime="text/csv", disabled=df.empty
    )

with tab2:
    st.markdown(
        "Один файл Excel с листами: показатели по товарам (ABC, XYZ, запасы, списания), "
        "показатели по точкам, рекомендации."
    )
    a = ui.product_analysis()
    recs = rec.build(a)
    products = pd.DataFrame(
        {
            "Артикул": a["sku"],
            "Товар": a["name"],
            "Категория": a["category_name"],
            "Продано, шт": a["net_qty"],
            "Выручка": a["revenue"],
            "Валовая прибыль": a["gross_profit"],
            "Маржинальность, доля": a["gross_margin"],
            "ABC по выручке": a["abc_revenue"],
            "ABC по прибыли": a["abc_profit"],
            "XYZ": a["xyz_class"],
            "Коэффициент вариации": a["cv"],
            "Пометка XYZ": a["xyz_note"],
            "Оборачиваемость, раз": a["turnover"],
            "Дни запаса": a["days_of_supply"],
            "Доля дней без товара": a["oos_share"],
            "Доля дней «распродано»": a["sold_out_share"],
            "Списания, ₽": a["write_off_cost"],
            "Доля списаний": a["write_off_share"],
        }
    )
    stores = queries.run(conn, 1, d0, d1).merge(
        queries.run(conn, 4, d0, d1)[["store_id", "gross_profit", "gross_margin", "margin_rank"]],
        on="store_id",
    )
    recs_out = recs.rename(
        columns={
            "rule": "Правило",
            "severity": "Важность",
            "sku": "Артикул",
            "product_name": "Товар",
            "category_name": "Категория",
            "problem": "Проблема",
            "basis": "Основание",
            "value": "Значение",
            "possible_cause": "Возможная причина",
            "action": "Действие",
            "limitations": "Ограничения",
        }
    )
    p = ui.analysis_params()
    desc = {
        "Отчёт": "Сводный отчёт по ассортименту",
        "Период": f"{d0:%d.%m.%Y} — {d1:%d.%m.%Y}",
        "Пороги ABC": f"A до {p['a']:.0%}, B до {p['b']:.0%} накопленного вклада",
        "Пороги XYZ": f"X до {p['x']:.0%}, Y до {p['y']:.0%} коэффициента вариации",
        "Сформирован": f"{datetime.now():%d.%m.%Y %H:%M}",
    }
    st.dataframe(ui.to_display(products.head(15)), hide_index=True, width="stretch")
    data = to_xlsx_bytes(
        {
            "Товары": products,
            "Точки": stores,
            "Рекомендации": recs_out.drop(columns=["product_id"]),
        },
        desc,
    )
    if st.download_button(
        "Скачать сводный отчёт (XLSX)",
        data,
        f"assortment_report_{datetime.now():%Y%m%d}.xlsx",
        type="primary",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ):
        repo.log_event(
            conn,
            "REPORT_EXPORTED",
            "пользователь",
            f"Сводный отчёт за {d0:%d.%m.%Y} — {d1:%d.%m.%Y}",
        )

    with st.expander("Журнал событий и проверки качества данных"):
        st.dataframe(repo.events(conn, 50), hide_index=True, width="stretch")
        st.dataframe(repo.dq_summary(conn), hide_index=True, width="stretch")
ui.footer()
