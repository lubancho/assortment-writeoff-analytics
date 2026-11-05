"""Метрики продаж, запасов и списаний (документ 04, раздел 2).

Общие правила:
- деньги — Decimal; float — только в слое отображения;
- знаменатель 0, отрицательный или неизвестный → None («н/д»), а не 0;
- показатели групп считаются как отношение сумм, а не как среднее отношений.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd

ZERO = Decimal(0)
CENT = Decimal("0.01")


def D(x) -> Decimal:
    if x is None or (not isinstance(x, Decimal) and pd.isna(x)):
        return ZERO
    return x if isinstance(x, Decimal) else Decimal(str(x))


def safe_ratio(num: Decimal | None, den: Decimal | None) -> Decimal | None:
    if num is None or den is None or den <= 0:
        return None
    return num / den


# --- Продажи -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class SalesMetrics:
    revenue: Decimal
    revenue_costed: Decimal
    cogs: Decimal
    gross_profit: Decimal
    gross_margin: Decimal | None
    net_qty: Decimal
    orders: int
    avg_check: Decimal | None
    lines_no_cost: int


def from_sums(revenue, revenue_costed, cogs, net_qty, lines_no_cost=0, orders=0) -> SalesMetrics:
    revenue, revenue_costed, cogs, net_qty = D(revenue), D(revenue_costed), D(cogs), D(net_qty)
    gp = revenue_costed - cogs
    return SalesMetrics(
        revenue=revenue,
        revenue_costed=revenue_costed,
        cogs=cogs,
        gross_profit=gp,
        gross_margin=safe_ratio(gp, revenue_costed),
        net_qty=net_qty,
        orders=int(orders or 0),
        avg_check=safe_ratio(revenue, Decimal(int(orders or 0))),
        lines_no_cost=int(lines_no_cost or 0),
    )


def enrich_sales(agg: pd.DataFrame) -> pd.DataFrame:
    """Добавляет gross_profit, gross_margin, avg_check к результату repository.sales_aggregates."""
    out = agg.copy()
    ms = [
        from_sums(r.revenue, r.revenue_costed, r.cogs, r.net_qty, r.lines_no_cost, r.orders)
        for r in out.itertuples(index=False)
    ]
    out["gross_profit"] = [m.gross_profit for m in ms]
    out["gross_margin"] = [m.gross_margin for m in ms]
    out["avg_check"] = [m.avg_check for m in ms]
    return out


def contribution(df: pd.DataFrame, column: str) -> pd.Series:
    """Вклад строки в итог по колонке. Если итог ≤ 0 — None.

    Если в колонке есть отрицательные значения (убыточная категория), доли могут быть > 100%
    и < 0% — это честное отражение данных, а не ошибка.
    """
    total = sum((D(v) for v in df[column]), ZERO)
    return df[column].map(lambda v: safe_ratio(D(v), total) if total > 0 else None)


# --- Запасы и списания -----------------------------------------------------------------------


def write_off_share(write_off_cost, cogs) -> Decimal | None:
    """Доля списаний в себестоимости выпуска: списания / (себестоимость продаж + списания)."""
    wo, c = D(write_off_cost), D(cogs)
    return safe_ratio(wo, wo + c)


def turnover(cogs, available_value_sum, days) -> Decimal | None:
    """Оборачиваемость, раз за период: себестоимость продаж / средний дневной доступный запас."""
    avg_stock = safe_ratio(D(available_value_sum), Decimal(int(days or 0)))
    return safe_ratio(D(cogs), avg_stock)


def days_of_supply(closing_value_end, cogs, days) -> Decimal | None:
    """Дни запаса: остаток на конец периода / средняя дневная себестоимость продаж."""
    daily_cogs = safe_ratio(D(cogs), Decimal(int(days or 0)))
    # Нет продаж — «на сколько дней хватит запаса» не определено (не 0 и не бесконечность).
    return safe_ratio(D(closing_value_end), daily_cogs)


def out_of_stock_share(unavailable_days, open_days) -> Decimal | None:
    """Доля рабочих «точко-дней», когда товара не было в продаже."""
    return safe_ratio(Decimal(int(unavailable_days or 0)), Decimal(int(open_days or 0)))


def sold_out_share(sold_out_days, open_days) -> Decimal | None:
    """Доля рабочих «точко-дней», когда к закрытию товар закончился.

    Для свежей продукции это может означать и точное планирование, поэтому показатель
    информационный и в правила рекомендаций не входит.
    """
    return safe_ratio(Decimal(int(sold_out_days or 0)), Decimal(int(open_days or 0)))


# --- Независимые расчёты в Python для сверки с SQL -----------------------------------------------


def _sign(row) -> int:
    return 0 if row["is_cancelled"] else (-1 if row["operation_type"] == "return" else 1)


def python_sales_totals(lines: pd.DataFrame, costs: pd.DataFrame) -> SalesMetrics:
    """М-01…М-05 и средний чек из сырых строк без SQL-представлений (для теста согласованности)."""
    if lines.empty:
        return from_sums(ZERO, ZERO, ZERO, ZERO)
    df = lines.copy()
    sign = df.apply(_sign, axis=1)
    df["net_qty"] = [Decimal(s) * D(q) for s, q in zip(sign, df["quantity"], strict=True)]
    df["net_revenue"] = [
        (Decimal(s) * (D(q) * D(p) - D(d))).quantize(CENT, ROUND_HALF_UP)
        for s, q, p, d in zip(
            sign, df["quantity"], df["unit_price"], df["discount_amount"], strict=True
        )
    ]
    merged = _merge_cost(df, costs, "sale_date")
    has_cost = merged["unit_cost"].notna()
    orders = (
        merged.loc[
            (~merged["is_cancelled"]) & (merged["operation_type"] == "sale"), "order_id"
        ].nunique()
        if "order_id" in merged
        else 0
    )
    return from_sums(
        sum(merged["net_revenue"], ZERO),
        sum(merged.loc[has_cost, "net_revenue"], ZERO),
        sum(
            (
                q * D(u)
                for q, u in zip(
                    merged.loc[has_cost, "net_qty"], merged.loc[has_cost, "unit_cost"], strict=True
                )
            ),
            ZERO,
        ),
        sum(merged["net_qty"], ZERO),
        int((~has_cost & ~merged["is_cancelled"]).sum()),
        orders,
    )


def python_write_off_cost(write_offs: pd.DataFrame, costs: pd.DataFrame) -> Decimal:
    """Стоимость списаний: количество × себестоимость на дату списания (для теста согласованности)."""
    if write_offs.empty:
        return ZERO
    merged = _merge_cost(write_offs, costs, "write_off_date")
    return sum(
        (
            D(q) * D(u)
            for q, u in zip(merged["quantity"], merged["unit_cost"], strict=True)
            if u is not None and not pd.isna(u)
        ),
        ZERO,
    )


def _merge_cost(df: pd.DataFrame, costs: pd.DataFrame, date_col: str) -> pd.DataFrame:
    left = df.assign(_d=pd.to_datetime(df[date_col])).sort_values("_d")
    right = costs.assign(_d=pd.to_datetime(costs["valid_from"])).sort_values("_d")[
        ["product_id", "_d", "unit_cost"]
    ]
    return pd.merge_asof(left, right, on="_d", by="product_id", direction="backward")
