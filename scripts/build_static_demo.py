"""Сборка интерактивной демо-версии дашборда для GitHub Pages.

Запуск (нужна база с загруженными данными — `asa init-demo`):
    uv run python scripts/build_static_demo.py --out site

Что делает: выгружает из базы компактные данные (продажи, списания и остатки по дням × точкам ×
категориям; продажи по товарам × дням; результат товарного анализа и рекомендаций за последние
28 дней; недельный спрос; результаты 10 SQL-задач) в site/data.js и копирует рядом страницу, стили,
код дашборда и библиотеку графиков ECharts. Показатели, фильтры и ABC за выбранный период считаются
в браузере; ABC за период по умолчанию сверяется с результатом Python (функция window.checkAbc).
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd

from asa import analysis, queries, report_catalog
from asa import recommendations as rec
from asa import repository as repo
from asa.analysis import XYZ_WEEKS
from asa.config import DEMO_NOTE
from asa.db import connect, fetch_df
from asa.report_catalog import COLUMNS, REPORTS
from asa.xyz import full_weeks

WEB = Path(__file__).parent / "web"
REASONS = [
    ("expired", "Истёк срок"),
    ("damaged", "Брак, повреждение"),
    ("return", "Возврат"),
    ("other", "Прочее"),
]


def _v(x):
    if x is None:
        return None
    if isinstance(x, Decimal):
        return round(float(x), 4)
    if isinstance(x, datetime | pd.Timestamp):
        return x.strftime("%Y-%m-%d %H:%M")
    if isinstance(x, date):
        return x.isoformat()
    if isinstance(x, float):
        return None if pd.isna(x) else round(x, 4)
    if x is pd.NA or x is pd.NaT:
        return None
    if hasattr(x, "item"):
        return x.item()
    return x


def rows(df: pd.DataFrame, cols: list[str]) -> list[list]:
    return [[_v(v) for v in r] for r in df[cols].itertuples(index=False, name=None)]


def collect(conn) -> dict:
    d_start, d1 = repo.data_period(conn)
    d0 = d1 - timedelta(days=27)
    days = [d.isoformat() for d in pd.date_range(d_start, d1).date]
    di = {d: i for i, d in enumerate(days)}
    stores = repo.stores(conn)
    cats = repo.categories(conn)
    prods = repo.products(conn)
    si = {int(s): i for i, s in enumerate(stores["store_id"])}
    ci = {int(c): i for i, c in enumerate(cats["category_id"])}
    pi = {int(p): i for i, p in enumerate(prods["product_id"])}
    ri = {r: i for i, (r, _) in enumerate(REASONS)}

    def idx(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
        out = df.copy()
        out["d"] = out[date_col].map(lambda v: di[v.isoformat()])
        if "store_id" in out:
            out["s"] = out["store_id"].map(lambda v: si[int(v)])
        if "category_id" in out:
            out["c"] = out["category_id"].map(lambda v: ci[int(v)])
        if "product_id" in out:
            out["p"] = out["product_id"].map(lambda v: pi[int(v)])
        return out

    sales = idx(
        fetch_df(
            conn,
            """
            SELECT sale_date, store_id, category_id,
                   COALESCE(sum(net_revenue), 0) AS rev,
                   COALESCE(sum(net_revenue) FILTER (WHERE unit_cost IS NOT NULL), 0) AS revc,
                   COALESCE(sum(net_cogs), 0) AS cogs,
                   COALESCE(sum(net_quantity), 0) AS qty
            FROM core.v_sale_fact GROUP BY 1, 2, 3""",
        ),
        "sale_date",
    )
    orders = idx(
        fetch_df(
            conn,
            "SELECT sale_date, store_id, count(DISTINCT order_id) AS n FROM core.v_sale_fact "
            "WHERE NOT is_cancelled GROUP BY 1, 2",
        ),
        "sale_date",
    )
    wo = idx(
        fetch_df(
            conn,
            "SELECT write_off_date, store_id, category_id, reason, sum(quantity) AS qty, "
            "COALESCE(sum(cost_amount), 0) AS cost FROM mart.v_write_off_fact GROUP BY 1, 2, 3, 4",
        ),
        "write_off_date",
    )
    wo["r"] = wo["reason"].map(ri)
    stock = idx(
        fetch_df(
            conn,
            """
            SELECT stock_date, store_id, category_id,
                   COALESCE(sum(available_value), 0) AS av,
                   COALESCE(sum(closing_value), 0) AS cv,
                   count(*) FILTER (WHERE is_open) AS open_days,
                   count(*) FILTER (WHERE is_open AND NOT is_available) AS unavail,
                   count(*) FILTER (WHERE is_sold_out) AS soldout
            FROM mart.v_stock_fact GROUP BY 1, 2, 3""",
        ),
        "stock_date",
    )
    pday = idx(
        fetch_df(
            conn,
            """
            SELECT sale_date, product_id,
                   COALESCE(sum(net_revenue), 0) AS rev,
                   COALESCE(sum(net_revenue) FILTER (WHERE unit_cost IS NOT NULL), 0) AS revc,
                   COALESCE(sum(net_cogs), 0) AS cogs,
                   COALESCE(sum(net_quantity), 0) AS qty
            FROM core.v_sale_fact GROUP BY 1, 2""",
        ),
        "sale_date",
    )

    a = analysis.product_analysis(conn, d0, d1)
    a["p"] = a["product_id"].map(lambda v: pi[int(v)])
    a["c"] = a["category_id"].map(lambda v: ci[int(v)])
    prod_cols = [
        "p", "product_id", "sku", "name", "c", "is_active", "net_qty", "revenue", "gross_profit",
        "gross_margin", "abc_revenue", "abc_profit", "abc_profit_note", "xyz_class", "cv",
        "weeks_used", "xyz_note", "write_off_cost", "write_off_share", "turnover", "days_of_supply",
        "oos_share", "sold_out_share", "revenue_prev", "gross_profit_prev",
    ]  # fmt: skip

    recs = rec.build(a)
    recs["p"] = recs["product_id"].map(lambda v: pi[int(v)])
    rec_cols = [
        "rule", "severity", "p", "product_name", "category_name", "problem", "basis", "value",
        "possible_cause", "action", "limitations",
    ]  # fmt: skip

    weeks = full_weeks(max(d_start, d1 - timedelta(weeks=XYZ_WEEKS) + timedelta(days=1)), d1)
    wk = repo.weekly_demand(conn, *weeks)

    sql = []
    for n, task in queries.TASKS.items():
        df = queries.run(conn, n, d0, d1)
        note = ""
        if n == 6 and df.empty:
            df = queries.run(conn, 6, d0, d1, by_store=True)
            note = "по сети пусто — показан вариант по точкам"
        sql.append(
            {
                "n": n,
                "title": task.title,
                "header": task.header(),
                "human": REPORTS[n],
                "method": report_catalog.method_text(task.header()),
                "text": task.text(),
                "note": note,
                "cols": list(df.columns),
                "num": [
                    bool(
                        pd.api.types.is_numeric_dtype(df[c])
                        or df[c].map(lambda v: isinstance(v, Decimal | int | float)).all()
                    )
                    and not df.empty
                    for c in df.columns
                ],
                "rows": rows(df, list(df.columns)),
            }
        )

    return {
        "meta": {
            "note": DEMO_NOTE,
            "d0": d0.isoformat(),
            "d1": d1.isoformat(),
            "built": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "xyz_weeks": XYZ_WEEKS,
            "abc_py": {
                "rev": a.loc[a["is_active"], "abc_revenue"].value_counts().to_dict(),
                "gp": a.loc[a["is_active"], "abc_profit"].value_counts().to_dict(),
            },
        },
        "days": days,
        "stores": rows(stores, ["store_id", "name"]),
        "cats": rows(cats, ["category_id", "name"]),
        "reasons": [label for _, label in REASONS],
        "sales": rows(sales, ["d", "s", "c", "rev", "revc", "cogs", "qty"]),
        "orders": rows(orders, ["d", "s", "n"]),
        "wo": rows(wo, ["d", "s", "c", "r", "cost", "qty"]),
        "stock": rows(stock, ["d", "s", "c", "av", "cv", "open_days", "unavail", "soldout"]),
        "pday": rows(pday, ["d", "p", "rev", "revc", "cogs", "qty"]),
        "prod_cols": prod_cols,
        "prods": rows(a.sort_values("p"), prod_cols),
        "rec_cols": rec_cols,
        "recs": rows(recs, rec_cols),
        "rule_titles": rec.RULE_TITLES,
        "weekly": {
            str(pi[int(p)]): rows(g, ["week_start", "net_qty", "availability"])
            for p, g in wk.groupby("product_id")
        },
        "sql": sql,
        "dq": rows(repo.dq_summary(conn), ["check_code", "severity", "issues"]),
        "col_ru": COLUMNS,
    }


def build(out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        data = collect(conn)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    (out / "data.js").write_text(f"window.DATA={payload};\n", encoding="utf-8")
    for name in ("index.html", "common.css", "common.js", "app.js"):
        shutil.copy(WEB / name, out / name)
    shutil.copy(WEB / "vendor" / "echarts.min.js", out / "echarts.min.js")
    (out / ".nojekyll").touch()
    size = sum(p.stat().st_size for p in out.iterdir() if p.is_file()) / 1e6
    print(f"Собрано: {out / 'index.html'} (всего {size:.1f} МБ)")
    return out / "index.html"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("site"))
    build(ap.parse_args().out)
