"""Реестр SQL-задач 1–10 (ТЗ §27). Тексты запросов — в папке sql/ с документацией в шапке файла."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import psycopg

from asa.db import fetch_df

SQL_DIR = Path(__file__).parent / "sql"


@dataclass(frozen=True)
class SqlTask:
    number: int
    title: str
    file: str
    defaults: dict = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return SQL_DIR / self.file

    def text(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def header(self) -> str:
        """Документация запроса — строки комментариев в начале файла."""
        lines = []
        for line in self.text().splitlines():
            if not line.startswith("--"):
                break
            lines.append(line[2:].strip())
        return "\n".join(lines)


TASKS: dict[int, SqlTask] = {
    1: SqlTask(1, "Выручка по торговым точкам", "01_revenue_by_store.sql"),
    2: SqlTask(2, "Выручка по категориям", "02_revenue_by_category.sql"),
    3: SqlTask(3, "Валовая прибыль по SKU", "03_gross_profit_by_sku.sql"),
    4: SqlTask(4, "Маржинальность по точкам", "04_margin_by_store.sql"),
    5: SqlTask(5, "Динамика продаж по дням", "05_daily_sales.sql"),
    6: SqlTask(
        6, "Товары без продаж за период", "06_products_without_sales.sql", {"by_store": False}
    ),
    7: SqlTask(
        7,
        "Товары с высоким уровнем списаний",
        "07_high_write_offs.sql",
        {"threshold": Decimal("0.20")},
    ),
    8: SqlTask(
        8,
        "ABC-классификация",
        "08_abc.sql",
        {"metric": "revenue", "a": Decimal("0.80"), "b": Decimal("0.95")},
    ),
    9: SqlTask(9, "Сравнение текущего и предыдущего периодов", "09_period_comparison.sql"),
    10: SqlTask(10, "Топ товаров по прибыли", "10_top_products_by_profit.sql", {"top": 10}),
}


def run(conn: psycopg.Connection, number: int, d0: date, d1: date, **params) -> pd.DataFrame:
    task = TASKS[number]
    return fetch_df(conn, task.text(), {"d0": d0, "d1": d1, **task.defaults, **params})
