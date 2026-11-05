"""Запросы к PostgreSQL для Python-аналитики. SQL-задачи ТЗ §27 — в asa/queries.py и папке sql/.

Суммы считает база (NUMERIC — точно), отношения и логика — Python (ADR-02).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import psycopg

from asa.db import fetch_df, fetch_one

# --- Справочники и даты -----------------------------------------------------------------------


def data_period(conn: psycopg.Connection) -> tuple[date, date] | None:
    row = fetch_one(conn, "SELECT min(sale_date) AS d0, max(sale_date) AS d1 FROM core.sale_line")
    if not row or row["d0"] is None:
        return None
    return row["d0"], row["d1"]


def stores(conn: psycopg.Connection) -> pd.DataFrame:
    return fetch_df(
        conn, "SELECT store_id, code, name, city, is_active FROM core.store ORDER BY store_id"
    )


def categories(conn: psycopg.Connection) -> pd.DataFrame:
    return fetch_df(conn, "SELECT category_id, name FROM core.category ORDER BY category_id")


def products(conn: psycopg.Connection) -> pd.DataFrame:
    return fetch_df(
        conn,
        "SELECT p.product_id, p.sku, p.name, p.category_id, c.name AS category_name, p.is_active "
        "FROM core.product p JOIN core.category c USING (category_id) ORDER BY p.product_id",
    )


# --- Метрики продаж ---------------------------------------------------------------------------

_DIMENSIONS = {
    "network": ([], []),
    "day": (["f.sale_date"], ["sale_date"]),
    "store": (["f.store_id", "s.name"], ["store_id", "store_name"]),
    "category": (["f.category_id", "c.name"], ["category_id", "category_name"]),
    "product": (
        ["f.product_id", "p.sku", "p.name", "c.name"],
        ["product_id", "sku", "product_name", "category_name"],
    ),
    "offer": (
        ["f.store_id", "s.name", "f.product_id", "p.name", "c.name"],
        ["store_id", "store_name", "product_id", "product_name", "category_name"],
    ),
}


def sales_aggregates(
    conn: psycopg.Connection,
    date_from: date,
    date_to: date,
    grain: str = "network",
    store_ids: list[int] | None = None,
    category_ids: list[int] | None = None,
    product_ids: list[int] | None = None,
) -> pd.DataFrame:
    """Суммы для метрик М-01…М-05 по выбранному срезу.

    revenue          — вся чистая выручка (М-01)
    revenue_costed   — выручка строк, для которых известна себестоимость на дату продажи
    cogs             — себестоимость реализованной продукции по тем же строкам
    net_qty          — чистое количество (продажи − возвраты, без отмен)
    lines_no_cost    — число строк без себестоимости (исключены из валовой прибыли)
    """
    if grain not in _DIMENSIONS:
        raise ValueError(f"Неизвестный срез: {grain}")
    exprs, names = _DIMENSIONS[grain]
    select_dims = "".join(f"{e} AS {n}, " for e, n in zip(exprs, names, strict=True))
    group_by = f"GROUP BY {', '.join(exprs)} ORDER BY {', '.join(exprs)}" if exprs else ""
    sql = f"""
        SELECT {select_dims}
               COALESCE(sum(f.net_revenue), 0)                                         AS revenue,
               COALESCE(sum(f.net_revenue) FILTER (WHERE f.unit_cost IS NOT NULL), 0)  AS revenue_costed,
               COALESCE(sum(f.net_cogs), 0)                                            AS cogs,
               COALESCE(sum(f.net_quantity), 0)                                        AS net_qty,
               count(*) FILTER (WHERE f.unit_cost IS NULL AND NOT f.is_cancelled)      AS lines_no_cost,
               count(DISTINCT f.order_id) FILTER (WHERE NOT f.is_cancelled)            AS orders
        FROM core.v_sale_fact f
        JOIN core.store s    ON s.store_id = f.store_id
        JOIN core.product p  ON p.product_id = f.product_id
        JOIN core.category c ON c.category_id = f.category_id
        WHERE f.sale_date BETWEEN %(d0)s AND %(d1)s
          AND (%(stores)s::int[] IS NULL OR f.store_id = ANY(%(stores)s::int[]))
          AND (%(cats)s::int[] IS NULL OR f.category_id = ANY(%(cats)s::int[]))
          AND (%(prods)s::int[] IS NULL OR f.product_id = ANY(%(prods)s::int[]))
        {group_by}
    """
    params = {
        "d0": date_from,
        "d1": date_to,
        "stores": store_ids or None,
        "cats": category_ids or None,
        "prods": product_ids or None,
    }
    return fetch_df(conn, sql, params)


# --- Остатки, списания, недельный спрос -------------------------------------------------------

_STOCK_DIMS = {
    "network": ([], []),
    "store": (["v.store_id"], ["store_id"]),
    "category": (["v.category_id"], ["category_id"]),
    "product": (["v.product_id"], ["product_id"]),
}


def stock_aggregates(
    conn: psycopg.Connection,
    date_from: date,
    date_to: date,
    grain: str = "product",
    store_ids: list[int] | None = None,
) -> pd.DataFrame:
    """Запасы и доступность за период.

    available_value_sum — сумма по дням стоимости запаса, доступного к продаже (на начало дня + выпуск);
    days                — число дней периода с данными;
    closing_qty_end / closing_value_end — остаток на конец последнего дня;
    open_days / unavailable_days / sold_out_days — «точко-дни» работы, отсутствия товара и распродажи.
    """
    exprs, names = _STOCK_DIMS[grain]
    dims = "".join(f"{e} AS {n}, " for e, n in zip(exprs, names, strict=True))
    group = f"GROUP BY {', '.join(exprs)}" if exprs else ""
    return fetch_df(
        conn,
        f"""
        SELECT {dims}
               COALESCE(sum(v.available_value), 0)                                   AS available_value_sum,
               count(DISTINCT v.stock_date)                                          AS days,
               COALESCE(sum(v.closing_qty) FILTER (WHERE v.stock_date = %(d1)s), 0)   AS closing_qty_end,
               COALESCE(sum(v.closing_value) FILTER (WHERE v.stock_date = %(d1)s), 0) AS closing_value_end,
               count(*) FILTER (WHERE v.is_open)                                     AS open_days,
               count(*) FILTER (WHERE v.is_open AND NOT v.is_available)              AS unavailable_days,
               count(*) FILTER (WHERE v.is_sold_out)                                 AS sold_out_days
        FROM mart.v_stock_fact v
        WHERE v.stock_date BETWEEN %(d0)s AND %(d1)s
          AND (%(stores)s::int[] IS NULL OR v.store_id = ANY(%(stores)s::int[]))
        {group}
        """,
        {"d0": date_from, "d1": date_to, "stores": store_ids or None},
    )


_WO_DIMS = {
    "network": ([], []),
    "store": (["w.store_id", "s.name"], ["store_id", "store_name"]),
    "category": (["w.category_id", "c.name"], ["category_id", "category_name"]),
    "product": (["w.product_id"], ["product_id"]),
    "reason": (["w.reason"], ["reason"]),
    "day": (["w.write_off_date"], ["write_off_date"]),
}


def write_off_aggregates(
    conn: psycopg.Connection,
    date_from: date,
    date_to: date,
    grain: str = "product",
    store_ids: list[int] | None = None,
    category_ids: list[int] | None = None,
) -> pd.DataFrame:
    """Количество и стоимость списаний (по себестоимости на дату списания)."""
    exprs, names = _WO_DIMS[grain]
    dims = "".join(f"{e} AS {n}, " for e, n in zip(exprs, names, strict=True))
    group = f"GROUP BY {', '.join(exprs)} ORDER BY {', '.join(exprs)}" if exprs else ""
    return fetch_df(
        conn,
        f"""
        SELECT {dims}
               COALESCE(sum(w.quantity), 0)    AS write_off_qty,
               COALESCE(sum(w.cost_amount), 0) AS write_off_cost,
               count(*)                        AS write_off_rows
        FROM mart.v_write_off_fact w
        JOIN core.store s ON s.store_id = w.store_id
        JOIN core.category c ON c.category_id = w.category_id
        WHERE w.write_off_date BETWEEN %(d0)s AND %(d1)s
          AND (%(stores)s::int[] IS NULL OR w.store_id = ANY(%(stores)s::int[]))
          AND (%(cats)s::int[] IS NULL OR w.category_id = ANY(%(cats)s::int[]))
        {group}
        """,
        {"d0": date_from, "d1": date_to, "stores": store_ids or None, "cats": category_ids or None},
    )


def weekly_demand(conn: psycopg.Connection, week_from: date, week_to: date) -> pd.DataFrame:
    """Чистые продажи товара по неделям в целом по сети и доступность товара в неделе.

    availability = доля «точко-дней», когда точка работала и товар был в продаже.
    """
    return fetch_df(
        conn,
        """
        WITH st AS (
            SELECT s.product_id, date_trunc('week', s.stock_date)::date AS week_start,
                   count(*) FILTER (WHERE c.is_open)                    AS open_days,
                   count(*) FILTER (WHERE c.is_open AND s.is_available) AS available_days
            FROM core.stock_daily s
            JOIN core.store_calendar c ON c.store_id = s.store_id AND c.calendar_date = s.stock_date
            WHERE s.stock_date BETWEEN %(w0)s AND %(w1)s
            GROUP BY 1, 2
        ), sl AS (
            SELECT product_id, date_trunc('week', sale_date)::date AS week_start, sum(net_quantity) AS net_qty
            FROM core.sale_line
            WHERE sale_date BETWEEN %(w0)s AND %(w1)s
            GROUP BY 1, 2
        )
        SELECT st.product_id, st.week_start, COALESCE(sl.net_qty, 0) AS net_qty,
               st.available_days::float / NULLIF(st.open_days, 0) AS availability
        FROM st LEFT JOIN sl USING (product_id, week_start)
        ORDER BY st.product_id, st.week_start
        """,
        {"w0": week_from, "w1": week_to},
    )


def first_sale_dates(conn: psycopg.Connection) -> dict[int, date]:
    rows = fetch_df(
        conn, "SELECT product_id, min(sale_date) AS d FROM core.sale_line GROUP BY product_id"
    )
    return dict(zip(rows["product_id"], rows["d"], strict=True))


def stock_daily_sample(
    conn: psycopg.Connection, store_id: int, product_id: int, d0: date, d1: date
) -> pd.DataFrame:
    return fetch_df(
        conn,
        "SELECT stock_date, opening_qty, produced_qty, sold_qty, written_off_qty, closing_qty, is_available, "
        "is_sold_out FROM mart.v_stock_fact WHERE store_id=%s AND product_id=%s AND stock_date BETWEEN %s AND %s "
        "ORDER BY stock_date",
        (store_id, product_id, d0, d1),
    )


def write_offs_raw(conn: psycopg.Connection, d0: date, d1: date) -> pd.DataFrame:
    """Строки core.write_off для независимой проверки стоимости списаний в Python."""
    return fetch_df(
        conn,
        "SELECT write_off_id, write_off_date, store_id, product_id, quantity, reason "
        "FROM core.write_off WHERE write_off_date BETWEEN %s AND %s",
        (d0, d1),
    )


def product_costs(conn: psycopg.Connection) -> pd.DataFrame:
    return fetch_df(
        conn,
        "SELECT product_id, valid_from, unit_cost FROM core.product_cost ORDER BY product_id, valid_from",
    )


def sale_lines_for_check(conn: psycopg.Connection, date_from: date, date_to: date) -> pd.DataFrame:
    return fetch_df(
        conn,
        "SELECT sale_line_id, order_id, sale_date, store_id, product_id, quantity, unit_price, discount_amount, "
        "operation_type, is_cancelled FROM core.sale_line WHERE sale_date BETWEEN %s AND %s",
        (date_from, date_to),
    )


def dq_summary(conn: psycopg.Connection) -> pd.DataFrame:
    return fetch_df(
        conn,
        "SELECT check_code, severity, count(*) AS issues FROM audit.dq_issue GROUP BY 1, 2 ORDER BY 3 DESC",
    )


def events(conn: psycopg.Connection, limit: int = 200) -> pd.DataFrame:
    return fetch_df(
        conn,
        "SELECT event_at, event_type, actor_role, message FROM audit.event_log ORDER BY event_id DESC LIMIT %s",
        (limit,),
    )


def log_event(conn: psycopg.Connection, event_type: str, actor: str, message: str) -> None:
    conn.execute(
        "INSERT INTO audit.event_log (event_type, actor_role, message) VALUES (%s, %s, %s)",
        (event_type, actor, message),
    )
