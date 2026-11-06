"""Главная: что происходит с продажами и на что обратить внимание (документ 09, раздел 3)."""

from __future__ import annotations

from datetime import timedelta

import streamlit as st
from components import ui

from asa import metrics
from asa import recommendations as rec
from asa import repository as repo

ui.page_header("Сводка", ui.period_caption())
d0, d1 = ui.current_period()
stores = ui.current_stores()


@st.cache_data(show_spinner=False, ttl=600)
def sales(d0, d1, stores, grain="network"):
    return metrics.enrich_sales(
        repo.sales_aggregates(ui.get_conn(), d0, d1, grain, store_ids=stores)
    )


@st.cache_data(show_spinner=False, ttl=600)
def write_offs(d0, d1, stores, grain="network"):
    return repo.write_off_aggregates(ui.get_conn(), d0, d1, grain, store_ids=stores)


length = (d1 - d0).days + 1
p0, p1 = d0 - timedelta(days=length), d0 - timedelta(days=1)
period = ui.cached_period()
has_prev = period is not None and p0 >= period[0]
cur = sales(d0, d1, stores).iloc[0]
prev = sales(p0, p1, stores).iloc[0] if has_prev else None
wo = write_offs(d0, d1, stores).iloc[0]
wo_prev = write_offs(p0, p1, stores).iloc[0] if has_prev else None
ws = metrics.write_off_share(wo.write_off_cost, cur.cogs)
ws_prev = metrics.write_off_share(wo_prev.write_off_cost, prev.cogs) if has_prev else None


def delta(a, b):
    if b is None:
        return None
    r = metrics.safe_ratio(metrics.D(a) - metrics.D(b), abs(metrics.D(b))) if b else None
    return None if r is None else ui.fmt_pct(r, signed=True)


dm = (
    cur.gross_margin - prev.gross_margin
    if has_prev and cur.gross_margin and prev.gross_margin
    else None
)
recs = rec.build(ui.product_analysis())
high = int((recs["severity"] == "Высокая").sum())
low_mg = int((recs["rule"] == "R1").sum())

# --- Уровень 1: одна фраза и четыре «двери» в разбор -------------------------------------------
where = "выбранных точек" if stores else "сети"
st.markdown(
    f"### За {length} дн. продано на {ui.fmt_rub(cur.revenue)}, "
    f"в списание ушло {ui.fmt_rub(wo.write_off_cost)}"
)
k = st.columns(4)
ui.door(
    k[0], "Выручка", ui.fmt_rub(cur.revenue),
    delta=delta(cur.revenue, prev.revenue if has_prev else None),
    note=f"{where}, к прошлому периоду" if has_prev else where,
    action="По точкам", page="views/sales.py", key="door_sales", help=ui.HELP["rev"],
)  # fmt: skip
ui.door(
    k[1], "Маржа", ui.fmt_pct(cur.gross_margin), delta=ui.fmt_pp(dm) if dm is not None else None,
    note=f"высокая выручка при низкой марже: {low_mg}", action="Какие товары",
    page="views/profitability.py", key="door_margin", help=ui.HELP["mg"],
)  # fmt: skip
ui.door(
    k[2], "Списания", ui.fmt_rub(wo.write_off_cost),
    delta=ui.fmt_pp(ws - ws_prev) if ws is not None and ws_prev is not None else None,
    delta_color="inverse", note=f"{ui.fmt_pct(ws)} выпуска", action="Где теряем",
    page="views/stock.py", key="door_stock", help=ui.HELP["wo"],
)  # fmt: skip
ui.door(
    k[3], "Задачи на проверку", f"{high:,}".replace(",", " "), note=f"высокой важности · всего {len(recs)}",
    action="Открыть", page="views/recommendations.py", state={"rc_preset_sev": ["Высокая"]},
    key="door_tasks", help="Задачи по 5 правилам: что проверить и почему. Причину задачи не утверждают.",
)  # fmt: skip
ui.footer()
