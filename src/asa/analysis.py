"""Сводный анализ товаров за период: продажи + ABC + XYZ + запасы + списания + динамика.

Один источник данных для экранов «Ассортимент», «Прибыльность», «Остатки и списания»,
«Рекомендации» и для отчётов — поэтому цифры на разных экранах совпадают.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd
import psycopg

from asa import abc, metrics, xyz
from asa import repository as repo

XYZ_WEEKS = 12


@dataclass(frozen=True)
class AnalysisSettings:
    abc: abc.AbcThresholds = field(default_factory=abc.AbcThresholds)
    xyz: xyz.XyzSettings = field(default_factory=xyz.XyzSettings)


def product_analysis(
    conn: psycopg.Connection, d0: date, d1: date, settings: AnalysisSettings | None = None
) -> pd.DataFrame:
    settings = settings or AnalysisSettings()
    sales = metrics.enrich_sales(repo.sales_aggregates(conn, d0, d1, "product"))
    prods = repo.products(conn)
    df = prods.merge(
        sales.drop(columns=["sku", "product_name", "category_name"]), on="product_id", how="left"
    )
    for col in ("revenue", "revenue_costed", "cogs", "net_qty", "gross_profit"):
        df[col] = df[col].map(metrics.D)
    df["lines_no_cost"] = df["lines_no_cost"].fillna(0).astype(int)

    # ABC — раздельно по выручке и по валовой прибыли (не смешиваем).
    active = df[df["is_active"]]
    abc_rev = abc.classify(
        active[["product_id", "revenue"]].rename(columns={"revenue": "value"}), settings.abc
    )
    abc_gp = abc.classify(
        active[["product_id", "gross_profit"]].rename(columns={"gross_profit": "value"}),
        settings.abc,
    )
    df = df.merge(
        abc_rev[["product_id", "share", "cum_share", "abc_class"]].rename(
            columns={
                "share": "revenue_share",
                "cum_share": "revenue_cum",
                "abc_class": "abc_revenue",
            }
        ),
        on="product_id",
        how="left",
    )
    df = df.merge(
        abc_gp[["product_id", "share", "abc_class", "note"]].rename(
            columns={"share": "gp_share", "abc_class": "abc_profit", "note": "abc_profit_note"}
        ),
        on="product_id",
        how="left",
    )

    # XYZ: фиксированное окно — последние XYZ_WEEKS полных недель до конца периода (не зависит от фильтра
    # периода, иначе при коротком периоде наблюдений не хватит), но не раньше начала данных.
    period = repo.data_period(conn)
    xyz_start = (
        max(period[0], d1 - timedelta(weeks=XYZ_WEEKS) + timedelta(days=1)) if period else d0
    )
    weeks = xyz.full_weeks(xyz_start, d1)
    if weeks:
        weekly = repo.weekly_demand(conn, *weeks)
        xz = xyz.classify(weekly, settings.xyz, repo.first_sale_dates(conn), weeks[0])
        df = df.merge(xz, on="product_id", how="left")
    else:
        df["xyz_class"], df["cv"], df["note"], df["weeks_used"], df["weeks_excluded"] = (
            None,
            None,
            "период короче одной полной недели",
            0,
            0,
        )
    df = df.rename(columns={"note": "xyz_note"})

    # Запасы и доступность.
    stock = repo.stock_aggregates(conn, d0, d1, "product")
    df = df.merge(stock, on="product_id", how="left")
    df["turnover"] = [
        metrics.turnover(c, a, n)
        for c, a, n in zip(df["cogs"], df["available_value_sum"], df["days"], strict=True)
    ]
    df["days_of_supply"] = [
        metrics.days_of_supply(v, c, n)
        for v, c, n in zip(df["closing_value_end"], df["cogs"], df["days"], strict=True)
    ]
    df["oos_share"] = [
        metrics.out_of_stock_share(u, o)
        for u, o in zip(df["unavailable_days"], df["open_days"], strict=True)
    ]
    df["sold_out_share"] = [
        metrics.sold_out_share(s, o)
        for s, o in zip(df["sold_out_days"], df["open_days"], strict=True)
    ]

    # Списания.
    wo = repo.write_off_aggregates(conn, d0, d1, "product")
    df = df.merge(wo, on="product_id", how="left")
    df["write_off_cost"] = df["write_off_cost"].map(metrics.D)
    df["write_off_qty"] = df["write_off_qty"].map(metrics.D)
    df["write_off_share"] = [
        metrics.write_off_share(w, c) for w, c in zip(df["write_off_cost"], df["cogs"], strict=True)
    ]

    # Предыдущий период той же длины — для правила «прибыль падает при росте выручки».
    length = (d1 - d0).days + 1
    prev = metrics.enrich_sales(
        repo.sales_aggregates(conn, d0 - timedelta(days=length), d0 - timedelta(days=1), "product")
    )
    prev = prev[["product_id", "revenue", "gross_profit"]].rename(
        columns={"revenue": "revenue_prev", "gross_profit": "gross_profit_prev"}
    )
    df = df.merge(prev, on="product_id", how="left")
    df["revenue_prev"] = df["revenue_prev"].map(
        lambda v: None if v is None or pd.isna(v) else metrics.D(v)
    )
    df["gross_profit_prev"] = df["gross_profit_prev"].map(
        lambda v: None if v is None or pd.isna(v) else metrics.D(v)
    )
    full_prev = period is not None and d0 - timedelta(days=length) >= period[0]
    # Если предыдущий период выходит за начало данных, сравнение было бы нечестным — не сравниваем.
    df["has_prev_period"] = df["revenue_prev"].notna() & full_prev
    return df
