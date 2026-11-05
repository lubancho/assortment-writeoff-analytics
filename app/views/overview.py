"""Главная: что происходит с продажами и на что обратить внимание (документ 09, раздел 3)."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components import ui

from asa import metrics, queries
from asa import recommendations as rec
from asa import repository as repo

ui.page_header("Что происходит с продажами", ui.period_caption())
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
NOTE = "к предыдущему периоду той же длины"


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
where = "по выбранным точкам" if stores else "по сети"
summary = f"За {length} дн. {where} выручка **{ui.fmt_rub(cur.revenue)}**"
if has_prev:
    summary += f" ({delta(cur.revenue, prev.revenue)})"
summary += f", валовая маржинальность **{ui.fmt_pct(cur.gross_margin)}**"
if dm is not None:
    summary += f" ({ui.fmt_pp(dm)})"
summary += f". В списание ушло **{ui.fmt_rub(wo.write_off_cost)}** — {ui.fmt_pct(ws)} себестоимости выпуска."
st.markdown(summary)

ui.level(
    "Состояние",
    "Основные показатели",
    f"Изменение — к предыдущим {length} дн. ({p0:%d.%m.%Y} — {p1:%d.%m.%Y}); зелёный — лучше для бизнеса "
    "(рост списаний — красный)."
    if has_prev
    else "Для выбранного периода нет предыдущего периода той же длины — сравнение не показывается.",
)
k = [*st.columns(3), *st.columns(3)]
k[0].metric(
    "Выручка",
    ui.fmt_rub(cur.revenue),
    delta(cur.revenue, prev.revenue if has_prev else None),
    delta_description=NOTE,
    help=ui.HELP["rev"],
)
k[1].metric(
    "Валовая прибыль",
    ui.fmt_rub(cur.gross_profit),
    delta(cur.gross_profit, prev.gross_profit if has_prev else None),
    delta_description=NOTE,
    help=ui.HELP["gp"],
)
k[2].metric(
    "Маржинальность",
    ui.fmt_pct(cur.gross_margin),
    ui.fmt_pp(dm) if dm is not None else None,
    delta_description=NOTE,
    help=ui.HELP["mg"],
)
k[3].metric(
    "Стоимость списаний",
    ui.fmt_rub(wo.write_off_cost),
    delta(wo.write_off_cost, wo_prev.write_off_cost if has_prev else None),
    delta_color="inverse",
    delta_description=NOTE,
    help=ui.HELP["wo"],
)
k[4].metric(
    "Доля списаний",
    ui.fmt_pct(ws),
    ui.fmt_pp(ws - ws_prev) if ws is not None and ws_prev is not None else None,
    delta_color="inverse",
    delta_description=NOTE,
    help=ui.HELP["ws"],
)
k[5].metric(
    "Средний чек",
    ui.fmt_rub(cur.avg_check),
    delta(cur.avg_check, prev.avg_check if has_prev else None),
    delta_description=NOTE,
    help=ui.HELP["check"],
)

# --- Что требует внимания -----------------------------------------------------------------------
ui.level(
    "Внимание", "Что требует внимания", "Только факты из данных. «Открыть» — перейти к деталям."
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
ui.attention(items, "ov_attn")

ui.level("Подробно", "Динамика и сравнение")
g1, g2 = st.columns([7, 5])
with g1:
    dd = ui.to_display(daily(d0, d1))
    fig = go.Figure()
    fig.add_bar(
        x=dd["sale_date"],
        y=dd["revenue"],
        name="Выручка за день",
        marker_color=ui.PALETTE["accent2"],
    )
    fig.add_scatter(
        x=dd["sale_date"],
        y=dd["revenue_ma7"],
        name="Скользящая средняя за 7 дней",
        line={"color": ui.PALETTE["accent"], "width": 2.5},
    )
    fig.update_layout(title="Выручка сети по дням, ₽", height=340, yaxis_tickformat=",.0f")
    fig.update_xaxes(tickformat="%d.%m", hoverformat="%d.%m.%Y")
    st.plotly_chart(fig, width="stretch")
    if stores:
        st.caption("График динамики — по всей сети (SQL-задача 5).")
with g2:
    cat = ui.to_display(sales(d0, d1, stores, "category"))
    cat["share"] = cat["revenue"] / cat["revenue"].sum() * 100
    cat["gp_share"] = cat["gross_profit"] / cat["gross_profit"].sum() * 100
    fig = go.Figure()
    fig.add_bar(
        y=cat["category_name"],
        x=cat["share"],
        name="Доля в выручке",
        orientation="h",
        marker_color=ui.PALETTE["accent2"],
    )
    fig.add_bar(
        y=cat["category_name"],
        x=cat["gp_share"],
        name="Доля в валовой прибыли",
        orientation="h",
        marker_color=ui.PALETTE["accent"],
    )
    fig.update_layout(
        title="Какие категории приносят выручку и прибыль, %",
        height=340,
        barmode="group",
        xaxis_ticksuffix="%",
        yaxis={"autorange": "reversed"},
    )
    st.plotly_chart(fig, width="stretch")

st.markdown("**Точки: продажи, маржа и списания** — отклонения к сети, процентные пункты")
show = pd.DataFrame(
    {
        "Точка": tbl["store_name"],
        "Выручка, ₽": tbl["revenue"],
        "Маржа": tbl["gross_margin"],
        "Маржа к сети": tbl["d_margin"],
        "Списания, ₽": tbl["write_off_cost"],
        "Доля списаний": tbl["write_off_share"],
        "Списания к сети": tbl["d_ws"],
        "Средний чек, ₽": tbl["avg_check"],
    }
).sort_values(
    "Списания к сети",
    ascending=False,
    key=lambda s: s.map(lambda v: float(v) if v is not None else -9),
)
fmts = {
    "Выручка, ₽": "rub",
    "Маржа": "pct",
    "Маржа к сети": "pp",
    "Списания, ₽": "rub",
    "Доля списаний": "pct",
    "Списания к сети": "pp",
    "Средний чек, ₽": "rub",
}
st.dataframe(
    ui.styled(show, fmts),
    hide_index=True,
    width="stretch",
    column_config={
        **ui.num_cfg(fmts),
        "Маржа к сети": st.column_config.TextColumn(
            help="Плюс — маржа выше сети (лучше)", alignment="right"
        ),
        "Списания к сети": st.column_config.TextColumn(
            help="Плюс — доля списаний выше сети (хуже)", alignment="right"
        ),
    },
)
ui.footer()
