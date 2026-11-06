"""Главная: что происходит с продажами и на что обратить внимание (документ 09, раздел 3)."""

from __future__ import annotations

from datetime import timedelta

import plotly.graph_objects as go
import streamlit as st
from components import ui

from asa import metrics, queries
from asa import recommendations as rec
from asa import repository as repo

ui.page_header("Обзор: продажи и потери", ui.period_caption())
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


@st.cache_data(show_spinner=False, ttl=600)
def active_skus(d0, d1, stores):
    df = repo.sales_aggregates(ui.get_conn(), d0, d1, "product", store_ids=stores)
    return int((df["net_qty"] > 0).sum())


@st.cache_data(show_spinner=False, ttl=600)
def daily(d0, d1):
    return queries.run(ui.get_conn(), 5, d0, d1)


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
NOTE = "к прошлому"  # база сравнения — предыдущий период той же длины (в подписи раздела)


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
by_store = sales(d0, d1, None, "store")
wo_store = write_offs(d0, d1, None, "store")
tbl = by_store.merge(wo_store[["store_id", "write_off_cost"]], on="store_id", how="left")
tbl["write_off_share"] = [
    metrics.write_off_share(w, c) for w, c in zip(tbl["write_off_cost"], tbl["cogs"], strict=True)
]
net = sales(d0, d1, None).iloc[0]
net_ws = metrics.write_off_share(write_offs(d0, d1, None).iloc[0].write_off_cost, net.cogs)
tbl["d_margin"] = [None if m is None else m - net.gross_margin for m in tbl["gross_margin"]]
tbl["d_ws"] = [None if w is None else w - net_ws for w in tbl["write_off_share"]]
recs = rec.build(ui.product_analysis())
items = []
high = recs[recs["severity"] == "Высокая"]
if len(high):
    parts = high["rule"].value_counts()
    items.append(
        dict(lvl="crit", title="Задачи высокой важности", value=f"{len(high)} задач",
             why="; ".join(f"{rec.RULE_TITLES[r].lower()} — {n}" for r, n in parts.items())
             + ". Задачи — по сети за выбранный период.",
             page="views/recommendations.py", state={"rc_preset_sev": ["Высокая"]}))  # fmt: skip
if has_prev and wo.write_off_cost > wo_prev.write_off_cost:
    items.append(
        dict(lvl="warn", title="Списания выросли", value=delta(wo.write_off_cost, wo_prev.write_off_cost),
             why=f"{ui.fmt_rub(wo.write_off_cost)} против {ui.fmt_rub(wo_prev.write_off_cost)} за предыдущий период.",
             page="views/stock.py"))  # fmt: skip
if not stores and len(tbl):
    w = tbl.sort_values("d_ws", ascending=False).iloc[0]
    if w["d_ws"] is not None and w["d_ws"] > 0:
        items.append(
            dict(lvl="warn", title=f"Самая высокая доля списаний — {w['store_name']}",
                 value=ui.fmt_pp(w["d_ws"]) + " к сети",
                 why=f"{ui.fmt_pct(w['write_off_share'])} при {ui.fmt_pct(net_ws)} по сети; "
                 f"списано {ui.fmt_rub(w['write_off_cost'])}.",
                 page="views/stock.py", state={"stores": [int(w["store_id"])]}))  # fmt: skip
    m = tbl.sort_values("d_margin").iloc[0]
    if m["d_margin"] is not None and m["d_margin"] < 0:
        items.append(
            dict(lvl="warn", title=f"Самая низкая маржа — {m['store_name']}",
                 value=ui.fmt_pp(m["d_margin"]) + " к сети",
                 why=f"{ui.fmt_pct(m['gross_margin'])} при {ui.fmt_pct(net.gross_margin)} по сети. Возможные "
                 "факторы — структура продаж, скидки, себестоимость (не установлено).",
                 page="views/profitability.py", state={"stores": [int(m["store_id"])]}))  # fmt: skip
if dm is not None and dm < 0:
    items.append(
        dict(lvl="info", title="Маржинальность снизилась", value=ui.fmt_pp(dm),
             why="Товары, у которых прибыль падает при росте выручки, — в задачах (правило R5).",
             page="views/recommendations.py", state={"rc_preset_rule": ["R5"]}))  # fmt: skip

# --- Главный показатель и вывод -------------------------------------------------------------------
where = "выбранных точек" if stores else "сети"
st.markdown(
    f"### Выручка {where} — {ui.fmt_rub(cur.revenue)}, в списание ушло {ui.fmt_rub(wo.write_off_cost)}"
)
sub = [f"Это {ui.fmt_pct(ws)} всего выпуска за {length} дн."]
if items:
    sub.append(f"Главное сейчас: {items[0]['title'].lower()} — {items[0]['value']}.")
st.markdown(" ".join(sub))

k = st.columns(4)
k[0].metric(
    "Выручка",
    ui.fmt_rub(cur.revenue),
    delta(cur.revenue, prev.revenue if has_prev else None),
    delta_description=NOTE,
    help=ui.HELP["rev"],
)
k[1].metric(
    "Маржа",
    ui.fmt_pct(cur.gross_margin),
    ui.fmt_pp(dm) if dm is not None else None,
    delta_description=NOTE,
    help=ui.HELP["mg"],
)
k[2].metric(
    "Потери на списаниях",
    ui.fmt_rub(wo.write_off_cost),
    delta(wo.write_off_cost, wo_prev.write_off_cost if has_prev else None),
    delta_color="inverse",
    delta_description=NOTE,
    help=ui.HELP["wo"],
)
k[3].metric(
    "Доля списаний",
    ui.fmt_pct(ws),
    ui.fmt_pp(ws - ws_prev) if ws is not None and ws_prev is not None else None,
    delta_color="inverse",
    delta_description=NOTE,
    help=ui.HELP["ws"],
)

# --- Не больше трёх главных проблем ---------------------------------------------------------------
ui.level(
    "Внимание",
    "Главные проблемы",
    f"Показаны 3 из {len(items)} — остальные — на страницах «Задачи на проверку», «Списания» и «Маржа товаров»."
    if len(items) > 3
    else None,
)
ui.attention(items[:3], "ov_attn")
if st.button(f"Открыть список задач: {len(recs)} →", type="primary"):
    st.switch_page("views/recommendations.py")

# --- Один график ---------------------------------------------------------------------------------
dd = ui.to_display(daily(d0, d1))
fig = go.Figure()
fig.add_bar(
    x=dd["sale_date"], y=dd["revenue"], name="Выручка за день", marker_color=ui.PALETTE["accent3"]
)
fig.add_scatter(
    x=dd["sale_date"],
    y=dd["revenue_ma7"],
    name="Среднее за 7 дней",
    line={"color": ui.PALETTE["accent"], "width": 2.5},
)
fig.update_layout(title="Выручка сети по дням, ₽", height=300, yaxis_tickformat=",.0f")
fig.update_xaxes(tickformat="%d.%m", hoverformat="%d.%m.%Y")
st.plotly_chart(fig, width="stretch")
if stores:
    st.caption("График — по всей сети. Подробности по точкам — на странице «Продажи по точкам».")
ui.footer()
