"""Интеграционные тесты с PostgreSQL: SQL-задачи, согласованность SQL и Python, данные (ТЗ §29)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal as Dec

import pytest

from asa import abc, analysis, metrics, queries
from asa import repository as repo
from asa.db import fetch_one
from asa.migrate import migrate

pytestmark = pytest.mark.integration

D1 = date(2026, 10, 31)
D0 = D1 - timedelta(days=27)


def total(conn, d0=D0, d1=D1):
    s = repo.sales_aggregates(conn, d0, d1).iloc[0]
    return metrics.from_sums(
        s.revenue, s.revenue_costed, s.cogs, s.net_qty, s.lines_no_cost, s.orders
    )


def test_migrations_are_idempotent(conn):
    assert migrate(conn) == []


@pytest.mark.parametrize("number", list(queries.TASKS))
def test_every_sql_task_runs_and_is_documented(conn, number):
    task = queries.TASKS[number]
    df = queries.run(conn, number, D0, D1)
    header = task.header()
    for word in ("Цель", "Таблицы", "Соединение", "Детализация", "Результат", "Проверка"):
        assert word in header, f"в запросе {number} нет раздела «{word}»"
    if number != 6:
        assert not df.empty


def test_sql_tasks_add_up_to_network_totals(conn):
    t = total(conn)
    t1 = queries.run(conn, 1, D0, D1)
    assert sum(t1["revenue"]) == t.revenue
    assert sum(t1["orders"]) == t.orders
    assert abs(sum(t1["revenue_share"]) - 1) < Dec("1e-12")
    t2 = queries.run(conn, 2, D0, D1)
    assert sum(t2["revenue"]) == t.revenue and abs(sum(t2["revenue_share"]) - 1) < Dec("1e-12")
    t3 = queries.run(conn, 3, D0, D1)
    assert sum(t3["gross_profit"]) == t.gross_profit
    t5 = queries.run(conn, 5, D0, D1)
    assert len(t5) == 28 and sum(t5["revenue"]) == t.revenue
    t9 = queries.run(conn, 9, D0, D1)
    assert sum(v for v in t9["rev_cur"] if v is not None) == t.revenue


def test_sql_and_python_totals_match(conn):
    sql = total(conn)
    py = metrics.python_sales_totals(
        repo.sale_lines_for_check(conn, D0, D1), repo.product_costs(conn)
    )
    assert sql.revenue == py.revenue
    assert sql.cogs.quantize(Dec("0.01")) == py.cogs.quantize(Dec("0.01"))
    assert sql.net_qty == py.net_qty
    assert sql.orders == py.orders and sql.avg_check == py.avg_check


def test_store_margin_uses_ratio_of_sums(conn):
    t4 = queries.run(conn, 4, D0, D1)
    network = sum(t4["gross_profit"]) / sum(t4["revenue_costed"])
    t = total(conn)
    assert abs(network - t.gross_margin) < Dec("1e-12")
    assert t4["margin_rank"].tolist() == sorted(t4["margin_rank"].tolist())


@pytest.mark.parametrize("metric", ["revenue", "gross_profit"])
def test_abc_sql_matches_python(conn, metric):
    sql = queries.run(conn, 8, D0, D1, metric=metric).set_index("product_id")["abc_class"]
    agg = metrics.enrich_sales(repo.sales_aggregates(conn, D0, D1, "product"))
    prods = repo.products(conn)[["product_id"]]
    vals = prods.merge(agg[["product_id", metric]], on="product_id", how="left").rename(
        columns={metric: "value"}
    )
    vals["value"] = vals["value"].map(metrics.D)
    py = abc.classify(vals).set_index("product_id")["abc_class"]
    assert sql.sort_index().to_dict() == py.sort_index().to_dict()


def test_write_off_cost_sql_matches_python(conn):
    sql = repo.write_off_aggregates(conn, D0, D1, "network").iloc[0]["write_off_cost"]
    py = metrics.python_write_off_cost(repo.write_offs_raw(conn, D0, D1), repo.product_costs(conn))
    assert sql == py
    by_reason = repo.write_off_aggregates(conn, D0, D1, "reason")
    assert sum(by_reason["write_off_cost"]) == sql


def test_returns_and_cancellations_in_database(conn):
    row = fetch_one(
        conn,
        """
        SELECT sum(net_revenue) FILTER (WHERE is_cancelled) AS cancelled,
               bool_and(net_revenue < 0) FILTER (WHERE operation_type = 'return' AND NOT is_cancelled) AS returns_neg
        FROM core.sale_line""",
    )
    assert row["cancelled"] == 0 and row["returns_neg"]


def test_stock_balance_and_sold_out_flag(conn):
    bad = fetch_one(
        conn,
        "SELECT count(*) AS n FROM core.stock_daily "
        "WHERE closing_qty <> opening_qty + produced_qty - sold_qty - written_off_qty",
    )
    assert bad["n"] == 0
    row = fetch_one(
        conn,
        "SELECT count(*) FILTER (WHERE is_sold_out AND NOT is_available) AS n FROM mart.v_stock_fact",
    )
    assert row["n"] == 0  # «распродано» возможно только в день, когда товар был в продаже


def test_products_without_sales_distinguishes_unavailability(conn):
    df = queries.run(conn, 6, D0, D1, by_store=True)
    assert set(df["interpretation"]) <= {"не было в продаже", "был в продаже, но не покупали"}
    for r in df.head(5).itertuples():
        sold = fetch_one(
            conn,
            "SELECT COALESCE(sum(net_quantity), 0) AS q FROM core.sale_line "
            "WHERE store_id=%s AND product_id=%s AND sale_date BETWEEN %s AND %s",
            (r.store_id, r.product_id, D0, D1),
        )
        assert sold["q"] <= 0


def test_product_analysis_is_consistent_with_sql(conn):
    a = analysis.product_analysis(conn, D0, D1)
    assert len(a) == 150
    assert sum(a["revenue"]) == total(conn).revenue
    assert set(a["abc_revenue"]) <= {"A", "B", "C"}
    assert a["xyz_class"].notna().sum() > 100
    assert (a["weeks_used"] >= 6).all()
    wo_total = repo.write_off_aggregates(conn, D0, D1, "network").iloc[0]["write_off_cost"]
    assert sum(a["write_off_cost"]) == wo_total


def test_previous_period_outside_data_is_not_compared(conn):
    d0, d1 = repo.data_period(conn)
    a = analysis.product_analysis(conn, d0, d1)
    assert not a["has_prev_period"].any()


def test_short_history_xyz_window_is_fixed(conn):
    d0, _ = repo.data_period(conn)
    a = analysis.product_analysis(conn, d0, d0 + timedelta(days=13))  # 2 недели данных
    assert a["xyz_class"].isna().all()
    assert set(a["xyz_note"]) == {"недостаточно наблюдений"}
