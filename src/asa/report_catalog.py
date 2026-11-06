"""Каталог подробных отчётов: понятные названия и бизнес-вопросы для SQL-задач 1–10.

Только описание для интерфейса — расчёты остаются в sql/ и queries.py. Используется экраном
«Подробные отчёты» в Streamlit и демо-версией (scripts/build_static_demo.py).

highlight — как показать «основные результаты» (3 строки): колонка с названием, колонка со значением,
формат значения (rub | pct | pp | spct | int | text) и порядок сортировки (desc | asc | none).
columns — русские названия колонок результата.
"""

from __future__ import annotations

REPORTS: dict[int, dict] = {
    1: {
        "title": "Выручка по точкам",
        "question": "Какие точки приносят больше всего выручки и какой у них средний чек?",
        "highlight": ("store_name", "revenue", "rub", "desc"),
        "lead": "Больше всего выручки",
    },
    2: {
        "title": "Выручка по категориям",
        "question": "Какие категории продаются лучше всего и какую долю выручки дают?",
        "highlight": ("category_name", "revenue_share", "pct", "desc"),
        "lead": "Наибольшая доля выручки",
    },
    3: {
        "title": "Прибыль по каждому товару",
        "question": "Сколько валовой прибыли приносит каждый товар и с какой маржой?",
        "highlight": ("product_name", "gross_profit", "rub", "desc"),
        "lead": "Больше всего прибыли",
    },
    4: {
        "title": "Маржа по точкам",
        "question": "В каких точках маржа ниже средней по сети и насколько?",
        "highlight": ("store_name", "diff_from_network", "pp", "asc"),
        "lead": "Сильнее всего ниже сети",
    },
    5: {
        "title": "Продажи по дням",
        "question": "Как менялась выручка день за днём и какой была средняя за неделю?",
        "highlight": ("sale_date", "revenue", "rub", "desc"),
        "lead": "Самые сильные дни",
    },
    6: {
        "title": "Товары без продаж",
        "question": "Какие товары не продавались и почему: их не покупали или их не было в наличии?",
        "highlight": ("product_name", "interpretation", "text", "none"),
        "lead": "Примеры",
    },
    7: {
        "title": "Товары с высокими списаниями",
        "question": "Какие товары чаще всего уходят в списание (20% выпуска и больше)?",
        "highlight": ("product_name", "write_off_share", "pct", "desc"),
        "lead": "Самая высокая доля списаний",
    },
    8: {
        "title": "Вклад товаров в выручку (ABC)",
        "question": "Какие товары дают основную часть выручки, а какие — небольшую?",
        "highlight": ("product_name", "share", "pct", "desc"),
        "lead": "Самый большой вклад",
    },
    9: {
        "title": "Сравнение с прошлым периодом",
        "question": "Как изменились выручка и прибыль категорий по сравнению с прошлым периодом?",
        "highlight": ("category_name", "gp_change_pct", "spct", "asc"),
        "lead": "Сильнее всего упала прибыль",
    },
    10: {
        "title": "Лучшие товары по прибыли",
        "question": "Какие 10 товаров приносят больше всего валовой прибыли?",
        "highlight": ("product_name", "gross_profit", "rub", "desc"),
        "lead": "Первые места",
    },
}

COLUMNS: dict[str, str] = {
    "store_id": "ID точки",
    "store_name": "Точка",
    "city": "Город",
    "revenue": "Выручка, ₽",
    "orders": "Чеков",
    "avg_check": "Средний чек, ₽",
    "revenue_share": "Доля выручки",
    "category_id": "ID категории",
    "category_name": "Категория",
    "net_qty": "Продано, шт",
    "product_id": "ID товара",
    "sku": "Артикул",
    "product_name": "Товар",
    "revenue_costed": "Выручка с известной себестоимостью, ₽",
    "cogs": "Себестоимость, ₽",
    "gross_profit": "Валовая прибыль, ₽",
    "gross_margin": "Маржинальность",
    "margin_rank": "Место по марже",
    "diff_from_network": "Отклонение от сети",
    "sale_date": "Дата",
    "revenue_ma7": "Среднее за 7 дней, ₽",
    "available_days": "Дней в продаже",
    "days": "Дней в периоде",
    "interpretation": "Вывод",
    "is_fresh": "Свежая продукция",
    "write_off_qty": "Списано, шт",
    "write_off_cost": "Списано, ₽",
    "write_off_share": "Доля списаний",
    "value": "Вклад, ₽",
    "share": "Доля",
    "cum_before": "Накоплено до товара",
    "cum_share": "Накопленная доля",
    "abc_class": "Класс ABC",
    "rev_cur": "Выручка сейчас, ₽",
    "rev_prev": "Выручка ранее, ₽",
    "rev_change": "Изменение выручки, ₽",
    "rev_change_pct": "Изменение выручки",
    "gp_cur": "Прибыль сейчас, ₽",
    "gp_prev": "Прибыль ранее, ₽",
    "gp_change": "Изменение прибыли, ₽",
    "gp_change_pct": "Изменение прибыли",
    "network_rank": "Место в сети",
    "category_rank": "Место в категории",
    "category_share": "Доля в категории",
}

METHOD_LABELS = {
    "Цель": "Зачем",
    "Таблицы": "Откуда данные",
    "Соединение": "Как соединяются",
    "Детализация": "Одна строка — это",
    "Результат": "Что получается",
    "Проверка": "Как проверено",
}


def method_text(header: str) -> list[tuple[str, str]]:
    """Шапка SQL-файла → пункты методики понятным языком (без первой строки «Задача N…»)."""
    items: list[tuple[str, str]] = []
    for line in header.splitlines():
        key, sep, rest = line.partition(":")
        if sep and key.strip() in METHOD_LABELS:
            text = rest.strip().removeprefix("одна строка = ")
            items.append((METHOD_LABELS[key.strip()], text))
        elif items and line.strip():
            label, text = items[-1]
            items[-1] = (label, f"{text} {line.strip()}")
    return items
