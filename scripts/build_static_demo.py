"""Сборка статичной демо-версии дашборда для GitHub Pages.

Запуск (нужна база с загруженными данными — `asa init-demo`):
    uv run python scripts/build_static_demo.py --out site

Все цифры считаются теми же модулями, что и в приложении (analysis, queries, recommendations).
"""

from __future__ import annotations

import argparse
import html
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).parent))
from static_site_kit import PALETTE, Page, copy_screens, records

from asa import abc, analysis, metrics, queries
from asa import recommendations as rec
from asa import repository as repo
from asa.analysis import XYZ_WEEKS
from asa.db import connect
from asa.xyz import full_weeks

REASON = {
    "expired": "Истёк срок",
    "damaged": "Брак, повреждение",
    "return": "Возврат",
    "other": "Прочее",
}


def rub(x) -> str:
    v = float(x)
    return (
        (f"{v / 1e6:,.1f} млн ₽" if abs(v) >= 1e6 else f"{v:,.0f} ₽")
        .replace(",", " ")
        .replace(".", ",")
    )


def pct(x, signed=False) -> str:
    if x is None:
        return "н/д"
    return (f"{float(x) * 100:+.1f}%" if signed else f"{float(x) * 100:.1f}%").replace(".", ",")


def pp(x) -> str:
    return f"{float(x) * 100:+.1f}".replace(".", ",") + " п. п."


def build(out: Path) -> Path:
    conn = connect()
    d_start, d1 = repo.data_period(conn)
    d0 = d1 - timedelta(days=27)
    p0, p1 = d0 - timedelta(days=28), d0 - timedelta(days=1)
    a = analysis.product_analysis(conn, d0, d1)
    recs = rec.build(a)
    page = Page(
        "Анализ продаж, ассортимента и списаний",
        f"Период {d0:%d.%m.%Y} — {d1:%d.%m.%Y}, вся сеть. ABC — за период; XYZ — по {XYZ_WEEKS} полным "
        "неделям до конца периода; пороги по умолчанию (A 80%, B 95%, X 10%, Y 25%).",
    )

    # --- Обзор бизнеса --------------------------------------------------------------------------
    def sales(x0, x1, grain="network"):
        return metrics.enrich_sales(repo.sales_aggregates(conn, x0, x1, grain))

    cur, prev = sales(d0, d1).iloc[0], sales(p0, p1).iloc[0]
    wo, wo_prev = (
        repo.write_off_aggregates(conn, d0, d1, "network").iloc[0],
        repo.write_off_aggregates(conn, p0, p1, "network").iloc[0],
    )
    active = int((repo.sales_aggregates(conn, d0, d1, "product")["net_qty"] > 0).sum())

    def ch(x, y):
        return pct((metrics.D(x) - metrics.D(y)) / abs(metrics.D(y)), True) + " к прошлым 28 дням"

    ov = page.tab("overview", "Обзор бизнеса")
    ov.append(
        page.kpis(
            [
                ("Выручка", rub(cur.revenue), ch(cur.revenue, prev.revenue)),
                ("Валовая прибыль", rub(cur.gross_profit), ch(cur.gross_profit, prev.gross_profit)),
                ("Маржинальность", pct(cur.gross_margin), pp(cur.gross_margin - prev.gross_margin)),
                (
                    "Стоимость списаний",
                    rub(wo.write_off_cost),
                    ch(wo.write_off_cost, wo_prev.write_off_cost),
                ),
                ("Активные SKU", str(active), "из 150 — с продажами за период"),
                ("Средний чек", rub(cur.avg_check), ch(cur.avg_check, prev.avg_check)),
            ]
        )
    )
    dd = queries.run(conn, 5, d0, d1)
    f = go.Figure()
    f.add_bar(
        x=dd["sale_date"],
        y=dd["revenue"].map(float),
        name="Выручка за день",
        marker_color=PALETTE["accent2"],
    )
    f.add_scatter(
        x=dd["sale_date"],
        y=dd["revenue_ma7"].map(float),
        name="Скользящая средняя 7 дней",
        line={"color": PALETTE["accent"], "width": 2.5},
    )
    f.update_layout(title="Динамика выручки сети, ₽ (SQL-задача 5)", yaxis_tickformat=",.0f")
    f.update_xaxes(tickformat="%d.%m")
    cat = sales(d0, d1, "category")
    tr = cat["revenue"].map(float).sum()
    tg = cat["gross_profit"].map(float).sum()
    f2 = go.Figure()
    f2.add_bar(
        y=cat["category_name"],
        x=cat["revenue"].map(float) / tr * 100,
        name="Доля в выручке",
        orientation="h",
        marker_color=PALETTE["accent2"],
    )
    f2.add_bar(
        y=cat["category_name"],
        x=cat["gross_profit"].map(float) / tg * 100,
        name="Доля в валовой прибыли",
        orientation="h",
        marker_color=PALETTE["accent"],
    )
    f2.update_layout(
        title="Вклад категорий, %",
        barmode="group",
        xaxis_ticksuffix="%",
        yaxis={"autorange": "reversed"},
    )
    ov.append(page.row(page.figure(f, 340), page.figure(f2, 340), widths=[7, 5]))
    st = sales(d0, d1, "store").merge(
        repo.write_off_aggregates(conn, d0, d1, "store")[["store_id", "write_off_cost"]],
        on="store_id",
    )
    st["wo_share"] = [
        metrics.write_off_share(w, c) for w, c in zip(st["write_off_cost"], st["cogs"], strict=True)
    ]
    st["rev_share"] = st["revenue"].map(float) / tr
    ov.append(page.h("Сравнение торговых точек"))
    ov.append(
        page.table(
            st.sort_values("revenue", ascending=False),
            [
                ("store_name", "Точка", "text"),
                ("revenue", "Выручка", "rub"),
                ("rev_share", "Доля", "pct"),
                ("gross_profit", "Валовая прибыль", "rub"),
                ("gross_margin", "Маржа", "pct"),
                ("orders", "Чеков", "int"),
                ("avg_check", "Средний чек", "rub"),
                ("write_off_cost", "Списания", "rub"),
                ("wo_share", "Доля списаний", "pct"),
            ],
            page_size=15,
            csv_name="stores",
        )
    )

    # --- Ассортимент ---------------------------------------------------------------------------
    asr = page.tab("assortment", "Ассортимент")
    s_rev = abc.summary(
        a.rename(columns={"abc_revenue": "abc_class", "revenue_share": "share", "revenue": "value"})
    )
    s_gp = abc.summary(
        a.rename(columns={"abc_profit": "abc_class", "gp_share": "share", "gross_profit": "value"})
    )
    matrix = (
        pd.crosstab(a["abc_revenue"], a["xyz_class"].fillna("—"))
        .reindex(index=["A", "B", "C"])
        .fillna(0)
    )
    m_html = (
        "<table><thead><tr><th>ABC \\ XYZ</th>"
        + "".join(f"<th class='num'>{c}</th>" for c in matrix.columns)
        + "</tr></thead><tbody>"
        + "".join(
            f"<tr><td><b>{i}</b></td>"
            + "".join(f"<td class='num'>{int(v)}</td>" for v in r)
            + "</tr>"
            for i, r in matrix.iterrows()
        )
        + "</tbody></table>"
    )
    differs = int((a["abc_revenue"] != a["abc_profit"]).sum())
    asr.append(
        page.row(
            page.h("ABC по выручке")
            + page.table(
                s_rev,
                [
                    ("abc_class", "Класс", "text"),
                    ("products", "Товаров", "int"),
                    ("value", "Выручка", "rub"),
                    ("share", "Доля", "pct"),
                ],
                page_size=5,
            ),
            page.h("ABC по валовой прибыли")
            + page.table(
                s_gp,
                [
                    ("abc_class", "Класс", "text"),
                    ("products", "Товаров", "int"),
                    ("value", "Прибыль", "rub"),
                    ("share", "Доля", "pct"),
                ],
                page_size=5,
            ),
            page.h("Матрица ABC × XYZ, товаров")
            + f"<div class='tbl'>{m_html}<div class='tbl-foot'>У {differs} товаров "
            "класс по выручке и по прибыли различается — классификации не смешиваются.</div></div>",
        )
    )
    a2 = a.copy()
    a2["xyz"] = a2["xyz_class"].fillna("—")
    a2["mark"] = (a2["xyz_note"].fillna("") + " " + a2["abc_profit_note"].fillna("")).str.strip()
    asr.append(
        page.note(
            "Нажмите на товар, чтобы увидеть недельный спрос. Недели, когда товар был доступен меньше "
            "чем в 80% рабочих точко-дней, в XYZ не используются — они выделены цветом."
        )
    )
    asr.append(
        page.table(
            a2.sort_values(["revenue", "product_id"], ascending=[False, True]),
            [
                ("sku", "Артикул", "text"),
                ("name", "Товар", "text"),
                ("category_name", "Категория", "text"),
                ("net_qty", "Продано, шт", "int"),
                ("revenue", "Выручка", "rub"),
                ("gross_profit", "Прибыль", "rub"),
                ("gross_margin", "Маржа", "pct"),
                ("abc_revenue", "ABC выр.", "text"),
                ("abc_profit", "ABC приб.", "text"),
                ("xyz", "XYZ", "text"),
                ("cv", "CV", "pct"),
                ("weeks_used", "Недель", "int"),
                ("mark", "Пометка", "text"),
            ],
            filters=[
                ("category_name", "Категория"),
                ("abc_revenue", "ABC выручка"),
                ("xyz", "XYZ"),
            ],
            search=["name", "sku"],
            page_size=25,
            row_click="demandCard",
            csv_name="assortment",
        )
    )
    t = page.tables[list(page.tables)[-1]]
    t["keys"].append("product_id")
    for r, pid in zip(
        t["rows"],
        a2.sort_values(["revenue", "product_id"], ascending=[False, True])["product_id"],
        strict=True,
    ):
        r.append(int(pid))
    weeks = full_weeks(max(d_start, d1 - timedelta(weeks=XYZ_WEEKS) + timedelta(days=1)), d1)
    wk = repo.weekly_demand(conn, *weeks)
    page.data["weekly"] = {
        str(int(p)): records(g, ["week_start", "net_qty", "availability"])
        for p, g in wk.groupby("product_id")
    }

    # --- Прибыльность --------------------------------------------------------------------------
    pf = page.tab("profit", "Прибыльность")
    net_m = cur.gross_margin
    cs = cat.sort_values("gross_margin")
    f = px.bar(
        x=cs["gross_margin"].map(lambda v: float(v) * 100),
        y=cs["category_name"],
        orientation="h",
        color_discrete_sequence=[PALETTE["accent"]],
    )
    f.add_vline(
        x=float(net_m) * 100, line_dash="dash", line_color=PALETTE["muted"], annotation_text="сеть"
    )
    f.update_layout(
        title="Маржинальность по категориям, %",
        xaxis_title=None,
        yaxis_title=None,
        xaxis_ticksuffix="%",
    )
    sm = queries.run(conn, 4, d0, d1).sort_values("gross_margin")
    f2 = px.bar(
        x=sm["diff_from_network"].map(lambda v: float(v) * 100),
        y=sm["store_name"],
        orientation="h",
        color=sm["diff_from_network"].map(lambda v: v < 0),
        color_discrete_map={True: PALETTE["warn"], False: PALETTE["accent"]},
    )
    f2.update_layout(
        title="Точки: отклонение маржинальности от сети, п. п. (SQL-задача 4)",
        showlegend=False,
        xaxis_title=None,
        yaxis_title=None,
    )
    pf.append(page.row(page.figure(f, 320), page.figure(f2, 360)))
    prod = sales(d0, d1, "product")
    pd_ = prod.assign(
        m=prod["gross_margin"].map(lambda v: float(v) * 100),
        r=prod["revenue"].map(float),
        g=prod["gross_profit"].map(lambda v: max(float(v), 1)),
    )
    f3 = px.scatter(
        pd_,
        x="r",
        y="m",
        color="category_name",
        hover_name="product_name",
        size="g",
        size_max=22,
        log_x=True,
        labels={"r": "Выручка, ₽ (лог. шкала)", "m": "Маржа, %", "category_name": "Категория"},
    )
    f3.add_hline(
        y=float(net_m) * 100 - 5,
        line_dash="dash",
        line_color=PALETTE["warn"],
        annotation_text="сеть − 5 п. п.",
        annotation_position="bottom right",
    )
    f3.update_layout(title="Товары: выручка и маржинальность", yaxis_ticksuffix="%")
    pf.append(page.figure(f3, 400))
    prod["diff"] = prod["gross_margin"].map(lambda v: None if v is None else v - net_m)
    prod["problem"] = [
        "Убыток"
        if g < 0
        else "Маржа ниже сети на 5+ п. п."
        if m is not None and m < net_m - metrics.D("0.05")
        else ""
        for g, m in zip(prod["gross_profit"], prod["gross_margin"], strict=True)
    ]
    pf.append(page.h(f"Проблемные позиции (маржинальность сети {pct(net_m)})"))
    pf.append(
        page.table(
            prod[prod["problem"] != ""].sort_values("diff"),
            [
                ("sku", "Артикул", "text"),
                ("product_name", "Товар", "text"),
                ("category_name", "Категория", "text"),
                ("revenue", "Выручка", "rub"),
                ("gross_profit", "Прибыль", "rub"),
                ("gross_margin", "Маржа", "pct"),
                ("diff", "Отклонение от сети", "pp"),
                ("problem", "Проблема", "text"),
            ],
            filters=[("category_name", "Категория")],
            search=["product_name"],
            csv_name="problems",
        )
    )

    # --- Остатки и списания ---------------------------------------------------------------------
    so = page.tab("stock", "Остатки и списания")
    stn = repo.stock_aggregates(conn, d0, d1, "network").iloc[0]
    so.append(
        page.kpis(
            [
                (
                    "Стоимость списаний",
                    rub(wo.write_off_cost),
                    f"{float(wo.write_off_qty):,.0f} шт".replace(",", " "),
                ),
                (
                    "Доля списаний",
                    pct(metrics.write_off_share(wo.write_off_cost, cur.cogs)),
                    "в себестоимости выпуска",
                ),
                (
                    "Оборачиваемость",
                    f"{float(metrics.turnover(cur.cogs, stn.available_value_sum, stn.days)):.1f} раз".replace(
                        ".", ","
                    ),
                    "себестоимость продаж / средний запас",
                ),
                (
                    "Дни запаса на конец",
                    f"{float(metrics.days_of_supply(stn.closing_value_end, cur.cogs, stn.days)):.1f}".replace(
                        ".", ","
                    ),
                    "свежая продукция на следующий день не хранится",
                ),
                (
                    "Нет в продаже",
                    pct(metrics.out_of_stock_share(stn.unavailable_days, stn.open_days)),
                    f"распродано к закрытию: {pct(metrics.sold_out_share(stn.sold_out_days, stn.open_days))}",
                ),
            ]
        )
    )
    by_r = repo.write_off_aggregates(conn, d0, d1, "reason")
    by_r["Причина"] = by_r["reason"].map(REASON)
    f = px.bar(
        by_r.sort_values("write_off_cost"),
        x=by_r.sort_values("write_off_cost")["write_off_cost"].map(float),
        y="Причина",
        orientation="h",
        color_discrete_sequence=[PALETTE["accent"]],
    )
    f.update_layout(
        title="Причины списаний, ₽", xaxis_title=None, yaxis_title=None, xaxis_tickformat=",.0f"
    )
    day = repo.write_off_aggregates(conn, d0, d1, "day")
    f2 = go.Figure()
    f2.add_scatter(
        x=day["write_off_date"],
        y=day["write_off_cost"].map(float),
        name="Списания за день",
        line={"color": PALETTE["warn"], "width": 2},
    )
    f2.update_layout(title="Динамика списаний, ₽", yaxis_tickformat=",.0f")
    f2.update_xaxes(tickformat="%d.%m")
    so.append(page.row(page.figure(f, 280), page.figure(f2, 280)))
    figs = []
    for grain, title, label, key in (
        ("category", "Списания по категориям", "category_name", "category_id"),
        ("store", "Списания по точкам", "store_name", "store_id"),
    ):
        w = repo.write_off_aggregates(conn, d0, d1, grain).merge(
            sales(d0, d1, grain)[[key, "cogs"]], on=key
        )
        w["share"] = [
            float(metrics.write_off_share(x, c)) * 100
            for x, c in zip(w["write_off_cost"], w["cogs"], strict=True)
        ]
        w = w.sort_values("share")
        fg = px.bar(
            w, x="share", y=label, orientation="h", color_discrete_sequence=[PALETTE["accent2"]]
        )
        fg.update_layout(
            title=f"{title}: доля в себестоимости выпуска, %",
            xaxis_title=None,
            yaxis_title=None,
            xaxis_ticksuffix="%",
        )
        figs.append(page.figure(fg, 360 if grain == "store" else 280))
    so.append(page.row(*figs))
    share = a["write_off_share"].map(
        lambda v: float(v) if v is not None and not pd.isna(v) else float("nan")
    )
    med = share.groupby(a["category_name"]).median()
    dev = a.assign(cat_median=a["category_name"].map(med), dev=share - a["category_name"].map(med))
    dev["kind"] = [
        "Высокие списания"
        if d >= 0.15
        else ("Часто нет в продаже" if o is not None and float(o) >= 0.03 else "Без отклонений")
        for d, o in zip(dev["dev"], dev["oos_share"], strict=True)
    ]
    so.append(page.h("Товары с отклонениями"))
    so.append(
        page.table(
            dev.sort_values("write_off_cost", ascending=False),
            [
                ("name", "Товар", "text"),
                ("category_name", "Категория", "text"),
                ("write_off_cost", "Списано", "rub"),
                ("write_off_share", "Доля списаний", "pct"),
                ("cat_median", "Медиана категории", "pct"),
                ("turnover", "Оборачиваемость", "num1"),
                ("days_of_supply", "Дни запаса", "num1"),
                ("oos_share", "Нет в продаже", "pct"),
                ("sold_out_share", "Распродано", "pct"),
                ("kind", "Отклонение", "text"),
            ],
            filters=[("kind", "Отклонение"), ("category_name", "Категория")],
            search=["name"],
            csv_name="write_offs",
            note="Доля списаний сравнивается с медианой своей категории: у свежей продукции списания выше по природе.",
        )
    )

    # --- Рекомендации ---------------------------------------------------------------------------
    rc = page.tab("recs", "Рекомендации")
    cnt = recs["severity"].value_counts()
    rc.append(
        page.kpis(
            [
                (f"Важность: {s.lower()}", str(cnt.get(s, 0)), None)
                for s in ("Высокая", "Средняя", "Низкая")
            ]
            + [("Товаров с рекомендациями", str(recs["product_id"].nunique()), None)]
        )
    )
    rc.append(
        page.note(
            "Рекомендации говорят, что проверить, и не утверждают причину. Ни одна не предлагает вывести "
            "товар из ассортимента только по классу ABC/XYZ."
        )
    )
    page.data["recs"] = records(
        recs,
        [
            "rule",
            "severity",
            "product_name",
            "category_name",
            "problem",
            "basis",
            "value",
            "possible_cause",
            "action",
            "limitations",
            "sku",
        ],
    )
    page.data["rule_titles"] = rec.RULE_TITLES
    rc.append("""<div class='tbl-tools'><select id='rf-sev'><option value=''>Важность: любая</option>
      <option>Высокая</option><option>Средняя</option><option>Низкая</option></select>
      <select id='rf-rule'><option value=''>Правило: любое</option></select>
      <select id='rf-cat'><option value=''>Категория: все</option></select><span id='rf-n' style='color:#5B6B7A'></span>
      </div><div id='rec-list'></div>""")

    # --- Отчёты: SQL-задачи ------------------------------------------------------------------------
    rp = page.tab("reports", "Отчёты (SQL)")
    rp.append(
        page.note(
            "Результаты 10 SQL-запросов проекта за период с параметрами по умолчанию. Под каждым — "
            "документация и текст запроса. Названия колонок — как в SQL."
        )
    )
    for n, task in queries.TASKS.items():
        df = queries.run(conn, n, d0, d1)
        if n == 6 and df.empty:
            df = queries.run(conn, 6, d0, d1, by_store=True)
            extra = " (по сети пусто — показан вариант по точкам)"
        else:
            extra = ""
        cols = [
            (c, c, "num2" if df[c].map(lambda v: hasattr(v, "as_tuple")).any() else "text")
            for c in df.columns
        ]
        rp.append(
            f"<details class='box'><summary><b>{n}. {html.escape(task.title)}</b> — строк: {len(df)}{extra}"
            f"</summary><pre>{html.escape(task.header())}</pre>"
            + page.table(df, cols, page_size=10, csv_name=f"sql_{n:02d}")
            + f"<details><summary>Текст запроса</summary><pre>{html.escape(task.text())}</pre></details></details>"
        )

    page.js = SCRIPT
    path = page.write(out)
    copy_screens(Path(__file__).parents[1] / "docs" / "screenshots", out)
    print(f"Собрано: {path} ({path.stat().st_size / 1e6:.1f} МБ)")
    return path


SCRIPT = r"""
function demandCard(T, r){
  const g = k => r[T.keys.indexOf(k)];
  const w = P.data.weekly[String(g('product_id'))] || [];
  const toISO = s => s.split('.').reverse().join('-');
  const ok = w.filter(v=>v[2]>=0.8), bad = w.filter(v=>v[2]<0.8);
  const h = `<h3 style="margin-top:0">${fmt(g('name'),'text')} · ${g('sku')} · ${fmt(g('category_name'),'text')}</h3>
    <div class="kpis"><div class="kpi"><div class="kpi-l">ABC по выручке / прибыли</div><div class="kpi-v">${g('abc_revenue')} / ${g('abc_profit')}</div></div>
    <div class="kpi"><div class="kpi-l">XYZ</div><div class="kpi-v">${g('xyz')}</div><div class="kpi-d">CV ${fmt(g('cv'),'pct')}, недель ${fmt(g('weeks_used'),'int')}</div></div>
    <div class="kpi"><div class="kpi-l">Маржа</div><div class="kpi-v">${fmt(g('gross_margin'),'pct')}</div></div></div>
    <div id="dm-fig" style="height:300px"></div>
    <p style="color:#5B6B7A">${g('mark')?('Пометка: '+g('mark')+'. '):''}Недели с доступностью ниже 80% не используются в XYZ: низкие продажи в них не означают низкий спрос.</p>`;
  openModal(h, [['dm-fig', [
    {type:'bar', name:'Неделя пригодна', x:ok.map(v=>toISO(v[0])), y:ok.map(v=>v[1]), marker:{color:'#3E5C76'}},
    {type:'bar', name:'Товара часто не было', x:bad.map(v=>toISO(v[0])), y:bad.map(v=>v[1]), marker:{color:'#B26A00'}}],
    {title:{text:'Недельный спрос, шт'}, margin:{l:50,r:10,t:40,b:30}, xaxis:{tickformat:'%d.%m'}, separators:', ',
     legend:{orientation:'h',y:-0.2}, font:{family:'Inter, Segoe UI, sans-serif'}}]]);
}
const ICON = {'Высокая':'🔴','Средняя':'🟠','Низкая':'⚪'};
function renderRecs(){
  const sev = document.getElementById('rf-sev').value, rule = document.getElementById('rf-rule').value,
        cat = document.getElementById('rf-cat').value;
  const list = P.data.recs.filter(r=>(!sev||r[1]===sev)&&(!rule||r[0]===rule)&&(!cat||r[3]===cat));
  document.getElementById('rf-n').textContent = `Показано ${list.length} из ${P.data.recs.length}`;
  document.getElementById('rec-list').innerHTML = list.map(r=>`<div class="rec"><div class="t">${ICON[r[1]]} ${fmt(r[4],'text')} — ${fmt(r[2],'text')} (${fmt(r[3],'text')})</div>
    <div class="grid"><div><b>Основание в данных.</b> ${fmt(r[5],'text')}</div><div><b>Рекомендуемое действие.</b> ${fmt(r[8],'text')}</div>
    <div><b>Значение показателя.</b> ${fmt(r[6],'text')}</div><div><b>Ограничения интерпретации.</b> ${fmt(r[9],'text')}</div>
    <div><b>Возможная причина.</b> ${fmt(r[7],'text')}</div><div style="color:#8A97A3">Правило ${r[0]} · важность ${r[1].toLowerCase()} · ${r[10]}</div></div></div>`).join('');
}
(function(){
  const rs = document.getElementById('rf-rule');
  Object.entries(P.data.rule_titles).forEach(([k,v])=>rs.insertAdjacentHTML('beforeend',`<option value="${k}">${k}. ${v}</option>`));
  const cs = document.getElementById('rf-cat');
  [...new Set(P.data.recs.map(r=>r[3]))].sort().forEach(c=>cs.insertAdjacentHTML('beforeend',`<option>${c}</option>`));
  ['rf-sev','rf-rule','rf-cat'].forEach(id=>document.getElementById(id).onchange=renderRecs);
  renderRecs();
})();
"""

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("site"))
    build(ap.parse_args().out)
