/* Дашборд «Продажи, ассортимент и списания»: показатели считаются в браузере из window.DATA. */
'use strict';

/* ---------- Данные ---------- */
const STORES = D.stores.map(([id, name], i) => ({i, id, name, short: name.replace('Омск — ', '')}));
const CATS = D.cats.map(([id, name], i) => ({i, id, name}));
const DAYS = D.days, LAST = DAYS.length - 1;
const PRODS = D.prods.map(r => Object.fromEntries(D.prod_cols.map((k, j) => [k, r[j]])));
const RECS = D.recs.map(r => Object.fromEntries(D.rec_cols.map((k, j) => [k, r[j]])));
PRODS.forEach(p => { p.cat = CATS[p.c].name; });
RECS.forEach(r => { r.c = PRODS[r.p].c; });
const REASONS = D.reasons;
const SEV = {'Высокая': {p: 'p-bad', c: '--bad', dot: 'bad'}, 'Средняя': {p: 'p-warn', c: '--warn', dot: 'warn'}, 'Низкая': {p: 'p-vio', c: '--vio', dot: ''}};
const DQ = {DUPLICATE: 'Дубли строк', FK_VIOLATION: 'Ссылка на несуществующую точку или товар', MISSING_VALUE: 'Пустое обязательное поле',
  OUT_OF_RANGE: 'Значение вне диапазона', NEGATIVE_QTY: 'Отрицательное количество', NON_POSITIVE_COST: 'Себестоимость ≤ 0',
  BAD_REASON: 'Неизвестная причина списания', MISSING_PRICE: 'Нет цены', DISCOUNT_OUT_OF_RANGE: 'Скидка вне диапазона'};
F.num = v => v == null || isNaN(v) ? '—' : Number.isInteger(v) ? NF0.format(v) : NF2.format(v);
const pctAx = v => NF0.format(v) + '%';
const sum = (a, f) => a.reduce((s, x) => s + f(x), 0);

/* ---------- Агрегации ---------- */
State.s = {days: 28, store: null, cat: null};
const range = () => [Math.max(0, LAST - State.s.days + 1), LAST];
function prevRange() { const [f, t] = range(), n = t - f + 1; return f - n < 0 ? null : [f - n, f - 1]; }
const keep = (s, c, st) => (st.store == null || s === st.store) && (st.cat == null || c === st.cat);
function aggSales([f, t], key, st = State.s) {
  const m = new Map();
  for (const [d, s, c, rev, revc, cogs, qty] of D.sales) {
    if (d < f || d > t || !keep(s, c, st)) continue;
    const k = key ? key(d, s, c) : 0, a = m.get(k) || {rev: 0, revc: 0, cogs: 0, qty: 0};
    a.rev += rev; a.revc += revc; a.cogs += cogs; a.qty += qty; m.set(k, a);
  }
  return m;
}
function aggWo([f, t], key, st = State.s, reason = null) {
  const m = new Map();
  for (const [d, s, c, r, cost, qty] of D.wo) {
    if (d < f || d > t || !keep(s, c, st) || (reason != null && r !== reason)) continue;
    const k = key ? key(d, s, c, r) : 0, a = m.get(k) || {cost: 0, qty: 0};
    a.cost += cost; a.qty += qty; m.set(k, a);
  }
  return m;
}
function aggStock([f, t], st = State.s) {
  const a = {av: 0, cvEnd: 0, open: 0, unavail: 0, soldout: 0};
  for (const [d, s, c, av, cv, open, un, so] of D.stock) {
    if (d < f || d > t || !keep(s, c, st)) continue;
    a.av += av; a.open += open; a.unavail += un; a.soldout += so; if (d === t) a.cvEnd += cv;
  }
  return a;
}
function orders([f, t], st = State.s) {
  if (st.cat != null) return null;  // чек не делится по категориям
  return sum(D.orders.filter(([d, s]) => d >= f && d <= t && (st.store == null || s === st.store)), x => x[2]);
}
const gp = a => a ? a.revc - a.cogs : null;
const mg = a => a ? ratio(a.revc - a.cogs, a.revc) : null;
const woShare = (wo, cogs) => ratio(wo, wo + cogs);
function totals(rg, st = State.s) {
  if (!rg) return null;
  const s = aggSales(rg, null, st).get(0) || {rev: 0, revc: 0, cogs: 0, qty: 0}, w = aggWo(rg, null, st).get(0) || {cost: 0, qty: 0};
  const o = orders(rg, st), stk = aggStock(rg, st), n = rg[1] - rg[0] + 1;
  return {...s, gp: gp(s), mg: mg(s), wo: w.cost, woQty: w.qty, woShare: woShare(w.cost, s.cogs), orders: o, check: o ? s.rev / o : null,
    turnover: stk.av ? s.cogs / (stk.av / n) : null, dos: s.cogs ? stk.cvEnd / (s.cogs / n) : null,
    oos: ratio(stk.unavail, stk.open), soldout: ratio(stk.soldout, stk.open)};
}
/* Продажи товаров за период (по сети) */
function prodSales([f, t]) {
  const m = PRODS.map(() => ({rev: 0, revc: 0, cogs: 0, qty: 0}));
  for (const [d, p, rev, revc, cogs, qty] of D.pday) {
    if (d < f || d > t) continue;
    const a = m[p]; a.rev += rev; a.revc += revc; a.cogs += cogs; a.qty += qty;
  }
  return m;
}

/* ---------- ABC (порт asa.abc.classify) ---------- */
function classify(items, A = 0.8, B = 0.95) {
  const s = items.slice().sort((x, y) => (y.value - x.value) || (x.id - y.id));
  const total = sum(s.filter(x => x.value > 0), x => x.value);
  let cum = 0;
  s.forEach(x => {
    if (x.value <= 0 || total <= 0) { x.cls = 'C'; x.share = null; x.cum = null; x.note = x.value === 0 ? 'нет продаж' : 'отрицательный вклад'; return; }
    x.share = x.value / total; const before = cum; cum += x.share; x.cum = cum;
    x.cls = before < A - 1e-12 ? 'A' : before < B - 1e-12 ? 'B' : 'C'; x.note = '';
  });
  return s;
}
function abcFor(rg, catFilter = State.s.cat) {
  const ps = prodSales(rg), res = {};
  for (const by of ['rev', 'gp']) {
    const items = PRODS.filter(p => p.is_active && (catFilter == null || p.c === catFilter))
      .map(p => ({id: p.product_id, p: p.p, value: +(by === 'rev' ? ps[p.p].rev : ps[p.p].revc - ps[p.p].cogs).toFixed(2)}));
    res[by] = classify(items);
  }
  return {ps, ...res};
}
window.checkAbc = function () {  // сверка с Python: последние 28 дней, вся сеть, пороги 80/95
  const r = abcFor([LAST - 27, LAST], null);
  let mism = 0, n = 0;
  for (const [by, col] of [['rev', 'abc_revenue'], ['gp', 'abc_profit']]) {
    r[by].forEach(x => { n++; if (PRODS[x.p][col] !== x.cls) mism++; });
  }
  return {checked: n, mismatches: mism};
};

/* ---------- Фильтры ---------- */
let catChips;
function buildFilters() {
  const per = $('#f-period');
  per.innerHTML = [[7, '7 дней'], [28, '28 дней'], [DAYS.length, 'Весь период']].map(([v, l]) => `<button data-v="${v}">${l}</button>`).join('');
  $$('button', per).forEach(b => b.onclick = () => State.set({days: +b.dataset.v}));
  const sel = $('#f-store');
  sel.innerHTML = '<option value="">Все точки</option>' + STORES.map(s => `<option value="${s.i}">${esc(s.name)}</option>`).join('');
  sel.onchange = () => State.set({store: sel.value === '' ? null : +sel.value});
  catChips = chipGroup('f-cats', CATS.map(c => ({v: c.i, label: c.name})), {allLabel: 'Все категории', onChange: v => State.set({cat: v})});
}
function syncFilters() {
  $$('#f-period button').forEach(b => b.classList.toggle('on', +b.dataset.v === State.s.days));
  $('#f-store').value = State.s.store ?? '';
  catChips.set(State.s.cat);
  const act = [];
  if (State.s.store != null) act.push(`<button class="chip af" data-x="store">${esc(STORES[State.s.store].name)} <span class="x">×</span></button>`);
  if (State.s.cat != null) act.push(`<button class="chip af" data-x="cat">${esc(CATS[State.s.cat].name)} <span class="x">×</span></button>`);
  if (act.length) act.push('<button class="link" data-x="all">Сбросить</button>');
  $('#f-active').innerHTML = act.join('');
  $$('#f-active [data-x]').forEach(b => b.onclick = () => { const x = b.dataset.x; State.set(x === 'all' ? {store: null, cat: null} : {[x]: null}); });
  const view = (location.hash || '#overview').slice(1);
  $('#filterbar').style.display = view === 'reports' ? 'none' : '';
  const fixed = ['recs'].includes(view);
  $('#f-period').style.display = fixed ? 'none' : '';
  $('#f-store').style.display = fixed ? 'none' : '';
}
const periodText = () => { const [f, t] = range(); return `${F.date(DAYS[f])} — ${F.date(DAYS[t])}`; };
const whereText = (storeOk = true) => [storeOk ? (State.s.store != null ? STORES[State.s.store].name : 'все точки') : 'вся сеть',
  State.s.cat != null ? CATS[State.s.cat].name : 'все категории'].join(' · ');

/* ---------- 1. Обзор ---------- */
function renderOverview() {
  const rg = range(), pr = prevRange(), cur = totals(rg), prev = totals(pr);
  $('#ov-period').textContent = periodText();
  const dIdx = []; for (let d = rg[0]; d <= rg[1]; d++) dIdx.push(d);
  const daily = aggSales(rg, d => d), wday = aggWo(rg, d => d);
  const revD = dIdx.map(d => daily.get(d)?.rev ?? 0), woD = dIdx.map(d => wday.get(d)?.cost ?? 0);
  const cmp = pr ? `к прошлым ${rg[1] - rg[0] + 1} дн.` : 'нет данных для сравнения';
  const kpis = [
    {k: 'rev', l: 'Выручка', v: F.rubc(cur.rev), d: deltaPill(cur.rev, prev?.rev), sp: revD},
    {k: 'gp', l: 'Валовая прибыль', v: F.rubc(cur.gp), d: deltaPill(cur.gp, prev?.gp), sp: dIdx.map(d => gp(daily.get(d)) ?? 0)},
    {k: 'mg', l: 'Маржинальность', dot: 'ok', v: F.pct(cur.mg), d: prev ? deltaPill(cur.mg, prev.mg, {kind: 'pp'}) : '',
      sp: dIdx.map(d => (mg(daily.get(d)) ?? 0) * 100), col: '--c5'},
    {k: 'wo', l: 'Списания', dot: 'bad', v: F.rubc(cur.wo), d: deltaPill(cur.wo, prev?.wo, {invert: true}), sp: woD, col: '--c3',
      act: () => Nav.go('stock')},
    {k: 'ws', l: 'Доля списаний', dot: 'warn', v: F.pct(cur.woShare), d: prev ? deltaPill(cur.woShare, prev.woShare, {kind: 'pp', invert: true}) : '',
      note: 'от себестоимости выпуска', act: () => Nav.go('stock')},
    {k: 'ch', l: 'Средний чек', v: cur.check ? F.rub(cur.check) : '—', d: deltaPill(cur.check, prev?.check),
      note: cur.orders == null ? 'не считается по категории' : `${F.int(cur.orders)} чеков`},
  ];
  $('#kpis').innerHTML = kpis.map(k => `<div class="card kpi ${k.act ? 'click' : ''}" data-k="${k.k}">
    <div class="eyebrow"><span class="dot ${k.dot || ''}"></span>${k.l}</div><div class="kpi-value">${k.v}</div>
    <div class="kpi-foot">${k.d || ''}<span>${k.note || cmp}</span></div>${k.sp ? `<div class="spark" id="sp-${k.k}"></div>` : '<span class="go">Подробнее →</span>'}</div>`).join('');
  kpis.forEach(k => {
    if (k.sp) spark('sp-' + k.k, k.sp, css(k.col || '--c1'));
    if (k.act) $(`[data-k="${k.k}"]`, $('#kpis')).onclick = k.act;
  });
  $('#trend-hint').textContent = periodText();
  const ma = revD.map((_, i) => { const s = revD.slice(Math.max(0, i - 6), i + 1); return s.reduce((a, b) => a + b, 0) / s.length; });
  Charts.set('c-trend', () => ({
    legend: {top: 0, left: 0}, grid: {left: 8, right: 8, top: 40, bottom: 4, containLabel: true},
    tooltip: {trigger: 'axis'},
    xAxis: Charts.axis('category', {data: dIdx.map(d => F.dshort(DAYS[d])), splitLine: {show: false}}),
    yAxis: [Charts.axis('value', {axisLabel: {formatter: v => NF0.format(v / 1000) + ' тыс'}}),
      Charts.axis('value', {splitLine: {show: false}, axisLabel: {formatter: v => NF0.format(v / 1000) + ' тыс'}})],
    series: [
      {name: 'Выручка', type: 'bar', data: revD, barMaxWidth: 18, tooltip: {valueFormatter: F.rub},
        itemStyle: {borderRadius: [6, 6, 0, 0], color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{offset: 0, color: css('--c2')}, {offset: 1, color: css('--c7')}])}},
      {name: 'Среднее за 7 дней', type: 'line', data: ma, smooth: true, symbol: 'none', lineStyle: {width: 2.5, color: css('--c1')}, tooltip: {valueFormatter: F.rub}},
      {name: 'Списания (правая ось)', type: 'line', yAxisIndex: 1, data: woD, smooth: true, symbolSize: 5, lineStyle: {width: 2, color: css('--c3')},
        itemStyle: {color: css('--c3')}, areaStyle: {color: css('--c3') + '22'}, tooltip: {valueFormatter: F.rub}},
    ],
  }));
  const byCat = aggSales(rg, (d, s, c) => c, {...State.s, cat: null});
  Charts.set('c-cats', () => ({
    tooltip: {trigger: 'item', formatter: p => `${p.name}<br><b>${F.rub(p.value)}</b> · ${NF1.format(p.percent)}%<br>маржа ${F.pct(mg(byCat.get(p.data.ci)))}`},
    legend: {bottom: 0, top: 'auto', left: 'center'},
    series: [{type: 'pie', radius: ['42%', '68%'], center: ['50%', '44%'], padAngle: 2, itemStyle: {borderRadius: 8},
      label: {formatter: p => NF0.format(p.percent) + '%', color: css('--text'), fontWeight: 700},
      data: CATS.map(c => ({name: c.name, ci: c.i, value: +(byCat.get(c.i)?.rev ?? 0).toFixed(0),
        itemStyle: {opacity: State.s.cat == null || State.s.cat === c.i ? 1 : 0.3}}))}],
  }), p => State.set({cat: State.s.cat === p.data.ci ? null : p.data.ci}));
  const sS = aggSales(rg, (d, s) => s, {...State.s, store: null}), sW = aggWo(rg, (d, s) => s, {...State.s, store: null});
  const pts = STORES.map(s => {
    const a = sS.get(s.i); if (!a) return null;
    return {s, m: mg(a) * 100, w: woShare(sW.get(s.i)?.cost ?? 0, a.cogs) * 100, rev: a.rev};
  }).filter(Boolean);
  const maxRev = Math.max(...pts.map(p => p.rev));
  Charts.set('c-stores', () => ({
    grid: {left: 8, right: 70, top: 34, bottom: 26, containLabel: true},
    tooltip: {trigger: 'item', formatter: p => `<b>${p.data.name}</b><br>маржа ${NF1.format(p.data.value[0])}%<br>списания ${NF1.format(p.data.value[1])}%<br>выручка ${F.rub(p.data.rev)}`},
    xAxis: Charts.axis('value', {name: 'маржинальность', nameLocation: 'middle', nameGap: 24, nameTextStyle: {color: css('--dim')}, scale: true, axisLabel: {formatter: pctAx}}),
    yAxis: Charts.axis('value', {name: 'доля списаний', nameTextStyle: {color: css('--dim')}, scale: true, axisLabel: {formatter: pctAx}}),
    series: [{type: 'scatter', data: pts.map(p => ({name: p.s.name, si: p.s.i, rev: p.rev, value: [+p.m.toFixed(2), +p.w.toFixed(2)],
      symbolSize: 12 + 26 * Math.sqrt(p.rev / maxRev),
      itemStyle: {color: State.s.store === p.s.i ? css('--c3') : css('--c1'), opacity: State.s.store == null || State.s.store === p.s.i ? 0.85 : 0.25,
        borderColor: '#fff', borderWidth: 1.5}})),
    labelLayout: {hideOverlap: true},
    label: {show: true, position: 'right', formatter: p => p.data.name.replace('Омск — ', ''), color: css('--muted'), fontSize: 10.5}}],
  }), p => State.set({store: State.s.store === p.data.si ? null : p.data.si}));
  const cA = aggSales(rg, (d, s, c) => c, {...State.s, cat: null});
  const tr = sum([...cA.values()], a => a.rev), tg = sum([...cA.values()], a => gp(a));
  Charts.set('c-share', () => ({
    legend: {top: 0, left: 0}, grid: {left: 8, right: 30, top: 36, bottom: 4, containLabel: true},
    tooltip: {trigger: 'axis', axisPointer: {type: 'shadow'}, valueFormatter: v => NF1.format(v) + '%'},
    xAxis: Charts.axis('value', {axisLabel: {formatter: pctAx}}),
    yAxis: Charts.axis('category', {data: CATS.map(c => c.name).reverse(), axisLabel: {color: css('--text')}}),
    series: [['Доля в выручке', a => a.rev / tr, '--c2'], ['Доля в валовой прибыли', a => gp(a) / tg, '--c1']].map(([n, f, col]) => ({
      name: n, type: 'bar', barMaxWidth: 14, itemStyle: {color: css(col), borderRadius: [0, 6, 6, 0]},
      label: {show: true, position: 'right', formatter: p => NF1.format(p.value) + '%', color: css('--muted'), fontSize: 10.5},
      data: CATS.slice().reverse().map(c => +((cA.get(c.i) ? f(cA.get(c.i)) : 0) * 100).toFixed(2))})),
  }), p => { const c = CATS[CATS.length - 1 - p.dataIndex]; State.set({cat: State.s.cat === c.i ? null : c.i}); });
}

/* ---------- 2. Ассортимент ---------- */
let abcBy = 'rev', abcSel = null, xyzSel = null, tProds, xyzChips;
function initAssortment() {
  $('#xyz-w').textContent = D.meta.xyz_weeks;
  const seg = $('#abc-by');
  seg.innerHTML = '<button data-v="rev">по выручке</button><button data-v="gp">по прибыли</button>';
  $$('button', seg).forEach(b => b.onclick = () => { abcBy = b.dataset.v; renderAssortment(); });
  xyzChips = chipGroup('as-chips', [], {allLabel: 'Любой XYZ', onChange: v => { xyzSel = v; renderAssortment(); }});
  tProds = new Table('t-prods', {
    cols: [{k: 'sku', label: 'Артикул', t: 'text'}, {k: 'name', label: 'Товар', t: 'text', w: 170}, {k: 'cat', label: 'Категория', t: 'text'},
      {k: 'qty', label: 'Продано, шт', t: 'int'}, {k: 'rev', label: 'Выручка', t: 'rub'}, {k: 'gpv', label: 'Прибыль', t: 'rub'},
      {k: 'mgv', label: 'Маржа', t: 'pct'}, {k: 'share', label: 'Доля', t: 'pct'}, {k: 'abc_h', label: 'ABC выр./приб.', t: 'html'},
      {k: 'xyz_h', label: 'XYZ', t: 'html'}, {k: 'cv', label: 'CV', t: 'pct'}, {k: 'mark', label: 'Пометка', t: 'text', w: 180}],
    rows: [], page: 15, search: ['name', 'sku'], onRow: r => productCard(r.p), csv: 'assortment', sort: 'rev',
  });
}
const clsPill = c => `<span class="pill ${c === 'A' ? 'p-ok' : c === 'B' ? 'p-warn' : c === 'C' ? 'p-bad' : ''}">${c ?? '—'}</span>`;
const xyzPill = z => `<span class="pill ${z === 'X' ? 'p-vio' : z === 'Y' ? 'p-warn' : z === 'Z' ? 'p-bad' : ''}">${z ?? '—'}</span>`;
function renderAssortment() {
  const rg = range(), r = abcFor(rg), list = r[abcBy];
  $('#as-eyebrow').textContent = `ABC: ${periodText()} · ${whereText(false)} · XYZ: ${D.meta.xyz_weeks} недель до ${F.date(D.meta.d1)}`;
  $$('#abc-by button').forEach(b => b.classList.toggle('on', b.dataset.v === abcBy));
  const other = Object.fromEntries(r[abcBy === 'rev' ? 'gp' : 'rev'].map(x => [x.p, x.cls]));
  const total = sum(list.filter(x => x.value > 0), x => x.value);
  const cards = ['A', 'B', 'C'].map(c => {
    const part = list.filter(x => x.cls === c);
    return {c, n: part.length, sh: sum(part, x => x.share || 0), v: sum(part, x => x.value)};
  });
  const desc = {A: 'дают ~80% вклада', B: 'следующие ~15%', C: 'оставшиеся ~5% и без продаж'};
  $('#abc-kpis').innerHTML = cards.map(k => `<div class="card kpi click" data-c="${k.c}" style="${abcSel === k.c ? 'border-color:var(--bd2);box-shadow:0 0 0 3px var(--vio-soft)' : ''}">
    <div class="eyebrow"><span class="dot ${k.c === 'A' ? 'ok' : k.c === 'B' ? 'warn' : 'bad'}"></span>Класс ${k.c} · ${abcBy === 'rev' ? 'выручка' : 'прибыль'}</div>
    <div class="kpi-value">${k.n} <span style="font-size:15px;color:var(--muted)">товаров</span></div>
    <div class="kpi-foot"><span class="delta flat">${F.pct(k.sh)}</span><span>${desc[k.c]} · ${F.rubc(k.v)}</span></div></div>`).join('')
    + `<div class="card kpi"><div class="eyebrow"><span class="dot"></span>Классы расходятся</div>
    <div class="kpi-value">${list.filter(x => other[x.p] !== x.cls).length}</div><div class="kpi-foot"><span>у стольких товаров класс по выручке ≠ по прибыли</span></div></div>`;
  $$('#abc-kpis [data-c]').forEach(c => c.onclick = () => { abcSel = abcSel === c.dataset.c ? null : c.dataset.c; renderAssortment(); });

  const pos = list.filter(x => x.value > 0);
  Charts.set('c-pareto', () => ({
    grid: {left: 8, right: 8, top: 30, bottom: 4, containLabel: true}, legend: {show: false},
    tooltip: {trigger: 'axis', formatter: ps => { const x = pos[ps[0].dataIndex], p = PRODS[x.p];
      return `<b>${esc(p.name)}</b><br>${abcBy === 'rev' ? 'выручка' : 'прибыль'} ${F.rub(x.value)} · класс ${x.cls}<br>накопленная доля ${F.pct(x.cum)}`; }},
    xAxis: Charts.axis('category', {data: pos.map((x, i) => i + 1), axisLabel: {interval: 19}, splitLine: {show: false}, name: 'товары по убыванию вклада', nameLocation: 'middle', nameGap: 22, nameTextStyle: {color: css('--dim')}}),
    yAxis: [Charts.axis('value', {axisLabel: {formatter: v => NF0.format(v / 1000) + ' тыс'}}), Charts.axis('value', {max: 100, splitLine: {show: false}, axisLabel: {formatter: pctAx}})],
    series: [{type: 'bar', barCategoryGap: '15%', data: pos.map(x => ({value: x.value, itemStyle: {
      color: css(x.cls === 'A' ? '--c1' : x.cls === 'B' ? '--c2' : '--c7'), opacity: !abcSel || abcSel === x.cls ? 1 : 0.3}}))},
    {type: 'line', yAxisIndex: 1, data: pos.map(x => +(x.cum * 100).toFixed(2)), symbol: 'none', smooth: true, lineStyle: {width: 2.5, color: css('--c3')},
      markLine: {symbol: 'none', silent: true, lineStyle: {type: 'dashed', color: css('--dim')}, label: {formatter: p => p.value + '%', color: css('--muted'), position: 'insideStartTop'},
        data: [{yAxis: 80}, {yAxis: 95}]}}],
  }), p => { const x = pos[p.dataIndex]; if (x) productCard(x.p); });

  const xyzOf = p => PRODS[p].xyz_class || '—', XS = ['X', 'Y', 'Z', '—'], AS = ['A', 'B', 'C'];
  const cnt = {}; list.forEach(x => { const k = x.cls + xyzOf(x.p); cnt[k] = (cnt[k] || 0) + 1; });
  const heat = []; AS.forEach((a, yi) => XS.forEach((z, xi) => heat.push([xi, yi, cnt[a + z] || 0])));
  Charts.set('c-matrix', () => ({
    grid: {left: 8, right: 8, top: 30, bottom: 50, containLabel: true},
    tooltip: {trigger: 'item', formatter: p => `${AS[p.value[1]]}${XS[p.value[0]]}: <b>${p.value[2]}</b> товаров`},
    xAxis: Charts.axis('category', {data: ['X стабильный', 'Y колеблется', 'Z нерегулярный', '— мало данных'], position: 'top', splitLine: {show: false},
      axisLabel: {color: css('--text'), fontWeight: 700, interval: 0, fontSize: 11, formatter: v => v.replace(' ', '\n')}}),
    yAxis: Charts.axis('category', {data: AS, inverse: true, splitLine: {show: false}, axisLabel: {color: css('--text'), fontWeight: 800, fontSize: 14}}),
    visualMap: {min: 0, max: Math.max(1, ...heat.map(h => h[2])), calculable: false, orient: 'horizontal', left: 'center', bottom: 0, itemHeight: 140,
      inRange: {color: [css('--bg2'), css('--c2'), css('--c1')]}, textStyle: {color: css('--muted')}},
    series: [{type: 'heatmap', data: heat, label: {show: true, fontWeight: 800, fontSize: 15, color: css('--fg')},
      itemStyle: {borderRadius: 10, borderColor: css('--glass'), borderWidth: 4},
      emphasis: {itemStyle: {shadowBlur: 12, shadowColor: 'rgba(80,60,200,.35)'}}}],
  }), p => {
    const a = AS[p.value[1]], z = XS[p.value[0]];
    if (abcSel === a && xyzSel === z) { abcSel = null; xyzSel = null; } else { abcSel = a; xyzSel = z; }
    renderAssortment();
  });

  const xc = {}; list.forEach(x => { if (!abcSel || x.cls === abcSel) xc[xyzOf(x.p)] = (xc[xyzOf(x.p)] || 0) + 1; });
  xyzChips.update(XS.map(z => ({v: z, label: z === '—' ? 'XYZ не определён' : 'XYZ: ' + z, n: xc[z] || 0})));
  xyzChips.set(xyzSel);
  const rows = list.map(x => {
    const p = PRODS[x.p], s = r.ps[x.p];
    const cr = abcBy === 'rev' ? x.cls : other[x.p], cg = abcBy === 'gp' ? x.cls : other[x.p];
    return {p: x.p, sku: p.sku, name: p.name, cat: p.cat, qty: s.qty, rev: s.rev, gpv: s.revc - s.cogs, mgv: ratio(s.revc - s.cogs, s.revc),
      share: x.share, cls: x.cls, xyz: xyzOf(x.p), abc_h: `${clsPill(cr)} ${clsPill(cg)}`, xyz_h: xyzPill(p.xyz_class),
      cv: p.cv, mark: [x.note, p.xyz_note].filter(Boolean).join('; ')};
  });
  tProds.setRows(rows);
  tProds.filter(x => (!abcSel || x.cls === abcSel) && (!xyzSel || x.xyz === xyzSel));
}

/* ---------- Карточка товара ---------- */
function productCard(pIdx) {
  const p = PRODS[pIdx], w = D.weekly[String(pIdx)] || [], recs = RECS.filter(r => r.p === pIdx);
  const rg = range(), daily = new Map();
  for (const [d, pp, rev, revc, cogs] of D.pday) if (pp === pIdx && d >= rg[0] && d <= rg[1]) daily.set(d, {rev, gp: revc - cogs});
  const dIdx = []; for (let d = rg[0]; d <= rg[1]; d++) dIdx.push(d);
  Drawer.open(`<div class="eyebrow"><span class="dot"></span>${esc(p.cat)} · ${esc(p.sku)}${p.is_active ? '' : ' · выведен'}</div>
    <h2>${esc(p.name)}</h2><div class="meta">Показатели — по сети за последние 28 дней (до ${F.date(D.meta.d1)}).</div>
    <div class="mini"><div><span>ABC выручка / прибыль</span><b>${clsPill(p.abc_revenue)} ${clsPill(p.abc_profit)}</b></div>
      <div><span>XYZ · CV</span><b>${p.xyz_class ?? '—'} · ${F.pct(p.cv)}</b></div>
      <div><span>Выручка · маржа</span><b>${F.rubc(p.revenue)} · ${F.pct(p.gross_margin)}</b></div>
      <div><span>Доля списаний</span><b>${F.pct(p.write_off_share)}</b></div>
      <div><span>Нет в продаже</span><b>${F.pct(p.oos_share)}</b></div><div><span>Распродано к закрытию</span><b>${F.pct(p.sold_out_share)}</b></div></div>
    <div class="card-head" style="margin-top:12px"><h3>Недельный спрос, шт</h3><span class="hint">неделя «не в счёт» — товар был доступен &lt; 80% точко-дней</span></div>
    <div class="chart short" id="c-week"></div>
    <div class="card-head" style="margin-top:8px"><h3>Выручка по дням · ${periodText()}</h3></div><div class="chart short" id="c-pday"></div>
    ${p.xyz_note ? `<div class="callout">XYZ: ${esc(p.xyz_note)}</div>` : ''}
    ${recs.map(r => `<div class="callout ${r.severity === 'Высокая' ? 'bad' : r.severity === 'Средняя' ? 'warn' : ''}"><b>${esc(r.rule)} · ${esc(r.problem)}.</b>
      ${esc(r.value)}.<br><b>Основание:</b> ${esc(r.basis)}.<br><b>Возможная причина:</b> ${esc(r.possible_cause)}.<br><b>Проверить:</b> ${esc(r.action)}.
      <br><b>Ограничения:</b> ${esc(r.limitations)}.</div>`).join('')}`, () => {
    Charts.set('c-week', () => ({
      grid: {left: 8, right: 8, top: 30, bottom: 4, containLabel: true}, legend: {top: 0, left: 0},
      tooltip: {trigger: 'axis', axisPointer: {type: 'shadow'}, formatter: ps => { const x = w[ps[0].dataIndex];
        return `неделя с ${F.date(x[0])}<br><b>${F.int(x[1])} шт</b><br>доступность ${F.pct(x[2])}`; }},
      xAxis: Charts.axis('category', {data: w.map(x => F.dshort(x[0])), splitLine: {show: false}}),
      yAxis: Charts.axis('value'),
      series: [{name: 'Неделя в расчёте', type: 'bar', stack: 'w', barMaxWidth: 26, itemStyle: {color: css('--c1'), borderRadius: [6, 6, 0, 0]},
        data: w.map(x => x[2] >= 0.8 ? x[1] : '-')},
      {name: 'Не в счёт (мало доступности)', type: 'bar', stack: 'w', barMaxWidth: 26, itemStyle: {color: css('--c4'), borderRadius: [6, 6, 0, 0]},
        data: w.map(x => x[2] < 0.8 ? x[1] : '-')}],
    }));
    Charts.set('c-pday', () => ({
      grid: {left: 8, right: 8, top: 14, bottom: 4, containLabel: true}, tooltip: {trigger: 'axis', valueFormatter: F.rub},
      xAxis: Charts.axis('category', {data: dIdx.map(d => F.dshort(DAYS[d])), splitLine: {show: false}}),
      yAxis: Charts.axis('value'),
      series: [{name: 'Выручка', type: 'line', smooth: true, symbol: 'none', data: dIdx.map(d => daily.get(d)?.rev ?? 0),
        lineStyle: {width: 2.5, color: css('--c1')}, areaStyle: {color: css('--c1') + '22'}},
      {name: 'Валовая прибыль', type: 'line', smooth: true, symbol: 'none', data: dIdx.map(d => daily.get(d)?.gp ?? 0), lineStyle: {width: 2, color: css('--c5')}}],
    }));
  });
}

/* ---------- 3. Прибыльность ---------- */
let tProblems;
function initProfit() {
  tProblems = new Table('t-problems', {
    cols: [{k: 'sku', label: 'Артикул', t: 'text'}, {k: 'name', label: 'Товар', t: 'text', w: 170}, {k: 'cat', label: 'Категория', t: 'text'},
      {k: 'rev', label: 'Выручка', t: 'rub'}, {k: 'gpv', label: 'Прибыль', t: 'rub'}, {k: 'mgv', label: 'Маржа', t: 'pct'},
      {k: 'diff', label: 'От сети', t: 'pp'}, {k: 'prob', label: 'Проблема', t: 'html'}],
    rows: [], page: 12, search: ['name', 'sku'], onRow: r => productCard(r.p), csv: 'problems', sort: 'diff', dir: 1,
  });
}
function renderProfit() {
  const rg = range(), ps = prodSales(rg);
  const net = mg(aggSales(rg, null, {store: null, cat: null}).get(0));
  $('#pf-eyebrow').textContent = `${periodText()} · товары — по сети · маржинальность сети ${F.pct(net)}`;
  const pts = PRODS.map(p => ({p, s: ps[p.p]})).filter(x => x.s.rev > 0 && (State.s.cat == null || x.p.c === State.s.cat));
  const maxGp = Math.max(...pts.map(x => Math.max(1, x.s.revc - x.s.cogs)));
  Charts.set('c-scatter', () => ({
    legend: {top: 0, left: 0}, grid: {left: 8, right: 24, top: 40, bottom: 28, containLabel: true},
    tooltip: {trigger: 'item', formatter: p => `<b>${esc(p.data.n)}</b><br>выручка ${F.rub(p.data.value[0])}<br>маржа ${NF1.format(p.data.value[1])}%<br>прибыль ${F.rub(p.data.g)}`},
    xAxis: Charts.axis('log', {name: 'выручка, ₽ (логарифмическая шкала)', nameLocation: 'middle', nameGap: 26, nameTextStyle: {color: css('--dim')},
      axisLabel: {formatter: v => v >= 1e6 ? NF0.format(v / 1e6) + ' млн' : NF0.format(v / 1000) + ' тыс'}}),
    yAxis: Charts.axis('value', {scale: true, axisLabel: {formatter: pctAx}}),
    series: CATS.map((c, i) => ({name: c.name, type: 'scatter', itemStyle: {color: PAL()[i], opacity: 0.8, borderColor: '#fff', borderWidth: 1},
      data: pts.filter(x => x.p.c === c.i).map(x => { const g = x.s.revc - x.s.cogs;
        return {n: x.p.name, pi: x.p.p, g, value: [+x.s.rev.toFixed(0), +((ratio(g, x.s.revc) ?? 0) * 100).toFixed(2)], symbolSize: 8 + 24 * Math.sqrt(Math.max(1, g) / maxGp)}; }),
      markLine: i === 0 ? {symbol: 'none', silent: true, lineStyle: {type: 'dashed', color: css('--bad')},
        label: {formatter: 'сеть − 5 п. п.', color: css('--bad'), position: 'insideEndTop'}, data: [{yAxis: +((net - 0.05) * 100).toFixed(2)}]} : undefined})),
  }), p => productCard(p.data.pi));
  const cA = aggSales(rg, (d, s, c) => c, {...State.s, cat: null});
  const cs = CATS.map(c => ({c, m: mg(cA.get(c.i))})).filter(x => x.m != null).sort((a, b) => a.m - b.m);
  const netF = mg(aggSales(rg, null, {...State.s, cat: null}).get(0));
  Charts.set('c-catm', () => ({
    grid: {left: 8, right: 44, top: 10, bottom: 4, containLabel: true}, tooltip: {trigger: 'axis', axisPointer: {type: 'shadow'}, valueFormatter: v => NF1.format(v) + '%'},
    xAxis: Charts.axis('value', {scale: true, axisLabel: {formatter: pctAx}}),
    yAxis: Charts.axis('category', {data: cs.map(x => x.c.name), axisLabel: {color: css('--text')}}),
    series: [{type: 'bar', barMaxWidth: 20, label: {show: true, position: 'right', formatter: p => NF1.format(p.value) + '%', color: css('--muted')},
      data: cs.map(x => ({value: +(x.m * 100).toFixed(2), ci: x.c.i, itemStyle: {borderRadius: [0, 8, 8, 0],
        color: x.m < netF ? css('--c4') : css('--c1'), opacity: State.s.cat == null || State.s.cat === x.c.i ? 1 : 0.3}})),
      markLine: {symbol: 'none', silent: true, lineStyle: {type: 'dashed', color: css('--dim')}, label: {formatter: 'среднее', color: css('--dim')}, data: [{xAxis: +(netF * 100).toFixed(2)}]}}],
  }), p => State.set({cat: State.s.cat === p.data.ci ? null : p.data.ci}));
  const sA = aggSales(rg, (d, s) => s, {...State.s, store: null}), netS = mg(aggSales(rg, null, {...State.s, store: null}).get(0));
  const ss = STORES.map(s => ({s, d: (mg(sA.get(s.i)) ?? netS) - netS})).sort((a, b) => a.d - b.d);
  Charts.set('c-stdev', () => ({
    grid: {left: 8, right: 44, top: 6, bottom: 4, containLabel: true}, tooltip: {trigger: 'axis', axisPointer: {type: 'shadow'}, valueFormatter: v => (v > 0 ? '+' : '') + NF1.format(v) + ' п. п.'},
    xAxis: Charts.axis('value', {axisLabel: {formatter: v => (v > 0 ? '+' : '') + v}}),
    yAxis: Charts.axis('category', {data: ss.map(x => x.s.short), axisLabel: {color: css('--text'), fontSize: 11}}),
    series: [{type: 'bar', barMaxWidth: 14, label: {show: true, position: 'right', formatter: p => (p.value > 0 ? '+' : '') + NF1.format(p.value), color: css('--muted'), fontSize: 10.5},
      data: ss.map(x => ({value: +(x.d * 100).toFixed(2), si: x.s.i, itemStyle: {borderRadius: 6, color: x.d < 0 ? css('--c3') : css('--c5'),
        opacity: State.s.store == null || State.s.store === x.s.i ? 1 : 0.3}}))}],
  }), p => State.set({store: State.s.store === p.data.si ? null : p.data.si}));
  $('#pf-hint').textContent = `убыток или маржа ниже сети (${F.pct(net)}) на 5+ п. п. · по сети`;
  tProblems.setRows(pts.map(x => { const g = x.s.revc - x.s.cogs, m = ratio(g, x.s.revc);
    const prob = g < 0 ? '<span class="pill p-bad">Убыток</span>' : m != null && m < net - 0.05 ? '<span class="pill p-warn">Маржа ниже сети на 5+ п. п.</span>' : '';
    return {p: x.p.p, sku: x.p.sku, name: x.p.name, cat: x.p.cat, rev: x.s.rev, gpv: g, mgv: m, diff: m == null ? null : m - net, prob};
  }).filter(r => r.prob));
}

/* ---------- 4. Остатки и списания ---------- */
let woReason = null, woKind = null, tWo, kindChips;
function initStock() {
  kindChips = chipGroup('st-chips', [], {allLabel: 'Все товары', onChange: v => { woKind = v; renderStock(); }});
  tWo = new Table('t-wo', {
    cols: [{k: 'name', label: 'Товар', t: 'text', w: 170}, {k: 'cat', label: 'Категория', t: 'text'}, {k: 'write_off_cost', label: 'Списано', t: 'rub'},
      {k: 'write_off_share', label: 'Доля списаний', t: 'pct'}, {k: 'med', label: 'Медиана категории', t: 'pct'}, {k: 'turnover', label: 'Оборач.', t: 'num1'},
      {k: 'days_of_supply', label: 'Дни запаса', t: 'num1'}, {k: 'oos_share', label: 'Нет в продаже', t: 'pct'}, {k: 'sold_out_share', label: 'Распродано', t: 'pct'},
      {k: 'kind_h', label: 'Отклонение', t: 'html'}],
    rows: [], page: 12, search: ['name'], onRow: r => productCard(r.p), csv: 'write_offs', sort: 'write_off_cost',
  });
  const med = {};
  CATS.forEach(c => {
    const v = PRODS.filter(p => p.c === c.i && p.write_off_share != null).map(p => p.write_off_share).sort((a, b) => a - b);
    med[c.i] = v.length ? (v.length % 2 ? v[(v.length - 1) / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2) : null;
  });
  tWo.base = PRODS.filter(p => p.is_active).map(p => {
    const kind = p.write_off_share != null && med[p.c] != null && p.write_off_share - med[p.c] >= 0.15 ? 'Высокие списания'
      : p.oos_share != null && p.oos_share >= 0.03 ? 'Часто нет в продаже' : 'Без отклонений';
    return {...p, med: med[p.c], kind, kind_h: `<span class="pill ${kind === 'Высокие списания' ? 'p-bad' : kind === 'Часто нет в продаже' ? 'p-warn' : 'p-ok'}">${kind}</span>`};
  });
  tWo.setRows(tWo.base);
}
function renderStock() {
  const rg = range(), cur = totals(rg), prev = totals(prevRange());
  $('#st-eyebrow').textContent = `${periodText()} · ${whereText()}`;
  const k = [
    {l: 'Стоимость списаний', dot: 'bad', v: F.rubc(cur.wo), d: deltaPill(cur.wo, prev?.wo, {invert: true}), n: `${F.int(cur.woQty)} шт`},
    {l: 'Доля списаний', dot: 'warn', v: F.pct(cur.woShare), d: prev ? deltaPill(cur.woShare, prev.woShare, {kind: 'pp', invert: true}) : '', n: 'в себестоимости выпуска'},
    {l: 'Оборачиваемость', v: F.num1(cur.turnover) + ' раз', n: 'себестоимость продаж / средний запас'},
    {l: 'Дни запаса на конец', v: F.num1(cur.dos), n: 'свежая продукция не хранится'},
    {l: 'Нет в продаже', dot: 'bad', v: F.pct(cur.oos), d: prev ? deltaPill(cur.oos, prev.oos, {kind: 'pp', invert: true}) : '', n: 'доля рабочих точко-дней'},
    {l: 'Распродано к закрытию', dot: 'ok', v: F.pct(cur.soldout), n: 'спрос выше выпуска'},
  ];
  $('#st-kpis').innerHTML = k.map(x => `<div class="card kpi"><div class="eyebrow"><span class="dot ${x.dot || ''}"></span>${x.l}</div>
    <div class="kpi-value">${x.v}</div><div class="kpi-foot">${x.d || ''}<span>${x.n}</span></div></div>`).join('');
  const byR = aggWo(rg, (d, s, c, r) => r);
  Charts.set('c-reasons', () => ({
    tooltip: {trigger: 'item', formatter: p => `${p.name}<br><b>${F.rub(p.value)}</b> · ${NF1.format(p.percent)}%`},
    legend: {bottom: 0, top: 'auto', left: 'center'},
    series: [{type: 'pie', radius: ['40%', '66%'], center: ['50%', '42%'], padAngle: 2, itemStyle: {borderRadius: 8},
      label: {formatter: p => NF0.format(p.percent) + '%', fontWeight: 700, color: css('--text')},
      data: REASONS.map((r, i) => ({name: r, ri: i, value: +(byR.get(i)?.cost ?? 0).toFixed(0),
        itemStyle: {color: [css('--c3'), css('--c4'), css('--c6'), css('--c7')][i], opacity: woReason == null || woReason === i ? 1 : 0.3}}))}],
  }), p => { woReason = woReason === p.data.ri ? null : p.data.ri; renderStock(); });
  const dIdx = []; for (let d = rg[0]; d <= rg[1]; d++) dIdx.push(d);
  const byDR = aggWo(rg, (d, s, c, r) => d * 10 + r);
  Charts.set('c-woday', () => ({
    legend: {top: 0, left: 0}, grid: {left: 8, right: 8, top: 36, bottom: 4, containLabel: true},
    tooltip: {trigger: 'axis', axisPointer: {type: 'shadow'}, valueFormatter: F.rub},
    xAxis: Charts.axis('category', {data: dIdx.map(d => F.dshort(DAYS[d])), splitLine: {show: false}}),
    yAxis: Charts.axis('value', {axisLabel: {formatter: v => NF0.format(v / 1000) + ' тыс'}}),
    series: REASONS.map((r, i) => ({name: r, type: 'bar', stack: 'r', barMaxWidth: 18,
      itemStyle: {color: [css('--c3'), css('--c4'), css('--c6'), css('--c7')][i], opacity: woReason == null || woReason === i ? 1 : 0.2},
      data: dIdx.map(d => +(byDR.get(d * 10 + i)?.cost ?? 0).toFixed(0))})),
  }), p => { woReason = woReason === p.seriesIndex ? null : p.seriesIndex; renderStock(); });
  const share = (key, st) => {
    const s = aggSales(rg, key, st), w = aggWo(rg, key, st, woReason);
    return k2 => s.get(k2) ? woShare(w.get(k2)?.cost ?? 0, s.get(k2).cogs) : null;
  };
  const fc = share((d, s, c) => c, {...State.s, cat: null});
  const cs = CATS.map(c => ({c, v: fc(c.i)})).filter(x => x.v != null).sort((a, b) => a.v - b.v);
  const suffix = woReason != null ? ` · «${REASONS[woReason]}»` : '';
  Charts.set('c-wocat', () => ({
    title: {text: suffix ? 'только причина' + suffix : '', right: 0, top: 0, textStyle: {fontSize: 11, color: css('--muted'), fontWeight: 600}},
    grid: {left: 8, right: 44, top: 22, bottom: 4, containLabel: true}, tooltip: {trigger: 'axis', axisPointer: {type: 'shadow'}, valueFormatter: v => NF1.format(v) + '%'},
    xAxis: Charts.axis('value', {axisLabel: {formatter: pctAx}}), yAxis: Charts.axis('category', {data: cs.map(x => x.c.name), axisLabel: {color: css('--text')}}),
    series: [{type: 'bar', barMaxWidth: 20, label: {show: true, position: 'right', formatter: p => NF1.format(p.value) + '%', color: css('--muted')},
      data: cs.map(x => ({value: +(x.v * 100).toFixed(2), ci: x.c.i, itemStyle: {borderRadius: [0, 8, 8, 0], color: css('--c3'),
        opacity: State.s.cat == null || State.s.cat === x.c.i ? 1 : 0.3}}))}],
  }), p => State.set({cat: State.s.cat === p.data.ci ? null : p.data.ci}));
  const fs = share((d, s) => s, {...State.s, store: null});
  const ss = STORES.map(s => ({s, v: fs(s.i)})).filter(x => x.v != null).sort((a, b) => a.v - b.v);
  Charts.set('c-wost', () => ({
    grid: {left: 8, right: 44, top: 6, bottom: 4, containLabel: true}, tooltip: {trigger: 'axis', axisPointer: {type: 'shadow'}, valueFormatter: v => NF1.format(v) + '%'},
    xAxis: Charts.axis('value', {axisLabel: {formatter: pctAx}}), yAxis: Charts.axis('category', {data: ss.map(x => x.s.short), axisLabel: {color: css('--text'), fontSize: 11}}),
    series: [{type: 'bar', barMaxWidth: 14, label: {show: true, position: 'right', formatter: p => NF1.format(p.value) + '%', color: css('--muted'), fontSize: 10.5},
      data: ss.map(x => ({value: +(x.v * 100).toFixed(2), si: x.s.i, itemStyle: {borderRadius: [0, 6, 6, 0], color: css('--c4'),
        opacity: State.s.store == null || State.s.store === x.s.i ? 1 : 0.3}}))}],
  }), p => State.set({store: State.s.store === p.data.si ? null : p.data.si}));
  const base = tWo.base.filter(r => State.s.cat == null || r.c === State.s.cat);
  kindChips.update(['Высокие списания', 'Часто нет в продаже', 'Без отклонений'].map(v => ({v, label: v, n: base.filter(r => r.kind === v).length,
    cls: v === 'Высокие списания' ? 'bad' : v === 'Без отклонений' ? 'ok' : 'warn'})));
  kindChips.set(woKind);
  tWo.filter(r => (State.s.cat == null || r.c === State.s.cat) && (!woKind || r.kind === woKind));
}

/* ---------- 5. Рекомендации ---------- */
let rcSev = null, rcRule = null, rcShown = 12, ruleChips;
function initRecs() {
  ruleChips = chipGroup('rc-rules', [], {allLabel: 'Все правила', onChange: v => { rcRule = v; rcShown = 12; renderRecs(); }});
  $('#cnt-recs').textContent = RECS.filter(r => r.severity === 'Высокая').length;
}
function renderRecs() {
  $('#rc-eyebrow').textContent = `По сети за последние 28 дней (до ${F.date(D.meta.d1)}) · ${State.s.cat != null ? CATS[State.s.cat].name : 'все категории'}`;
  const scope = RECS.filter(r => State.s.cat == null || r.c === State.s.cat);
  const sevs = ['Высокая', 'Средняя', 'Низкая'];
  $('#rc-kpis').innerHTML = sevs.map(s => `<div class="card kpi click" data-s="${s}" style="${rcSev === s ? 'border-color:var(--bd2);box-shadow:0 0 0 3px var(--vio-soft)' : ''}">
    <div class="eyebrow"><span class="dot ${SEV[s].dot}"></span>Важность: ${s.toLowerCase()}</div><div class="kpi-value">${scope.filter(r => r.severity === s).length}</div>
    <div class="kpi-foot"><span>нажмите, чтобы показать</span></div></div>`).join('')
    + `<div class="card kpi"><div class="eyebrow"><span class="dot"></span>Товаров с рекомендациями</div><div class="kpi-value">${new Set(scope.map(r => r.p)).size}</div>
    <div class="kpi-foot"><span>из ${PRODS.filter(p => p.is_active && (State.s.cat == null || p.c === State.s.cat)).length} активных</span></div></div>`;
  $$('#rc-kpis [data-s]').forEach(c => c.onclick = () => { rcSev = rcSev === c.dataset.s ? null : c.dataset.s; rcShown = 12; renderRecs(); });
  const s2 = scope.filter(r => !rcSev || r.severity === rcSev);
  ruleChips.update(Object.keys(D.rule_titles).map(k => ({v: k, label: `${k} · ${D.rule_titles[k]}`, n: s2.filter(r => r.rule === k).length})));
  ruleChips.set(rcRule);
  const list = s2.filter(r => !rcRule || r.rule === rcRule).sort((a, b) => sevs.indexOf(a.severity) - sevs.indexOf(b.severity));
  $('#rc-list').innerHTML = list.slice(0, rcShown).map((r, i) => `<div class="card rec" data-i="${i}" style="--rc:var(${SEV[r.severity].c})">
    <div class="rec-head"><span class="pill ${SEV[r.severity].p}">${r.severity}</span><span class="pill p-vio">${r.rule}</span>
      <span class="rec-title">${esc(r.product_name)}</span><span class="rec-sub">${esc(r.category_name)}</span></div>
    <div style="margin-top:8px;font-weight:700">${esc(r.problem)}</div><div class="rec-sub">${esc(r.value)}</div>
    <div class="rec-grid"><div><b>Основание</b>${esc(r.basis)}</div><div><b>Что проверить</b>${esc(r.action)}</div></div>
    <span class="go" style="font-size:12px;font-weight:800;color:var(--lil);margin-top:8px;display:inline-block">Причина, ограничения и спрос товара →</span></div>`).join('')
    || '<div class="empty">Нет рекомендаций для выбранных фильтров</div>';
  $$('#rc-list .rec').forEach(c => c.onclick = () => productCard(list[+c.dataset.i].p));
  $('#rc-more').innerHTML = `<span>Показано ${Math.min(rcShown, list.length)} из ${list.length}</span>` +
    (list.length > rcShown ? '<button class="btn" id="rc-btn">Показать ещё</button>' : '');
  if ($('#rc-btn')) $('#rc-btn').onclick = () => { rcShown += 12; renderRecs(); };
}

/* ---------- 6. Отчёты SQL ---------- */
function initReports() {
  $('#rp-eyebrow').textContent = `Период ${F.date(D.meta.d0)} — ${F.date(D.meta.d1)} · PostgreSQL`;
  $('#sql-list').innerHTML = D.sql.map(q => `<details class="card sql" data-n="${q.n}"><summary><span class="num-ic">${q.n}</span>
    <span><b>${esc(q.title)}</b><br><span class="hint">строк: ${F.int(q.rows.length)}${q.note ? ' · ' + esc(q.note) : ''}</span></span><span class="chev">›</span></summary>
    <div class="mt" id="sql-t-${q.n}"></div><details class="mt"><summary class="link">Документация и текст запроса</summary><pre>${esc(q.header)}</pre><pre>${esc(q.text)}</pre></details></details>`).join('');
  $$('#sql-list details.sql').forEach(el => el.addEventListener('toggle', () => {
    if (!el.open || el.dataset.done) return;
    el.dataset.done = 1;
    const q = D.sql.find(x => x.n === +el.dataset.n);
    new Table('sql-t-' + q.n, {cols: q.cols.map((c, i) => ({k: i, label: c, t: q.num[i] ? 'num' : 'text'})), rows: q.rows, page: 10,
      csv: `sql_${String(q.n).padStart(2, '0')}`}).render();
  }));
  new Table('t-dq', {cols: [{k: 0, label: 'Проверка', t: 'html'}, {k: 1, label: 'Критичность', t: 'html'}, {k: 2, label: 'Строк', t: 'int'}],
    rows: D.dq.map(([c, sev, n]) => [DQ[c] ? `${DQ[c]} <span class="hint">${c}</span>` : esc(c),
      sev === 'CRIT' ? '<span class="pill p-bad">Критично</span>' : '<span class="pill p-warn">Внимание</span>', n]), page: 10}).render();
}

/* ---------- Запуск ---------- */
shell();
buildFilters();
initAssortment(); initProfit(); initStock(); initRecs(); initReports();
$('#foot').innerHTML = `${esc(D.meta.note)} Статичная демо-версия: данные выгружены из базы проекта, собрано ${D.meta.built}.
  ABC за выбранный период пересчитывается в браузере по тому же правилу, что в Python; XYZ, рекомендации и товарные показатели запасов — за последние 28 дней.
  Полная версия с настройкой порогов — запуск через Docker (см. README).`;
function renderAll() { syncFilters(); renderOverview(); renderAssortment(); renderProfit(); renderStock(); renderRecs(); }
State.on(renderAll);
const navGo = Nav.go.bind(Nav);
Nav.go = (k, push) => { navGo(k, push); syncFilters(); };
window.addEventListener('hashchange', syncFilters);
Nav.init();
renderAll();
