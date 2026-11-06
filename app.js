/* Дашборд «Продажи, ассортимент и списания». Показатели считаются в браузере из window.DATA,
   выгруженного из базы проекта. Формулы — те же, что в Python (asa.metrics, asa.abc). */
'use strict';

/* ---------- Данные и справочники ---------- */
const STORES = D.stores.map(([id, name], i) => ({i, id, name, short: name.replace('Омск — ', '')}));
const CATS = D.cats.map(([id, name], i) => ({i, id, name}));
const DAYS = D.days, LAST = DAYS.length - 1;
const PRODS = D.prods.map(r => Object.fromEntries(D.prod_cols.map((k, j) => [k, r[j]])));
const RECS = D.recs.map(r => Object.fromEntries(D.rec_cols.map((k, j) => [k, r[j]])));
PRODS.forEach(p => { p.cat = CATS[p.c].name; p.rules = new Set(); });
RECS.forEach(r => { r.c = PRODS[r.p].c; PRODS[r.p].rules.add(r.rule); });
const REASONS = D.reasons;
const RCOL = ['--c3', '--c4', '--c6', '--c7'];
const SEV = {'Высокая': {p: 'p-bad', ac: '--bad', dot: 'bad'}, 'Средняя': {p: 'p-warn', ac: '--warn', dot: 'warn'}, 'Низкая': {p: 'p-vio', ac: '--vio', dot: ''}};
const SEVS = ['Высокая', 'Средняя', 'Низкая'];
const DQ = {DUPLICATE: 'Дубли строк — исключены автоматически', FK_VIOLATION: 'Ссылка на несуществующую точку или товар', MISSING_VALUE: 'Пустое обязательное поле',
  OUT_OF_RANGE: 'Значение вне диапазона', NEGATIVE_QTY: 'Отрицательное количество', NON_POSITIVE_COST: 'Себестоимость ≤ 0',
  BAD_REASON: 'Неизвестная причина списания', DISCOUNT_OUT_OF_RANGE: 'Скидка вне диапазона', MISSING_PRICE: 'Нет цены'};
const HELP = {
  rev: 'Выручка = продажи за вычетом возвратов и скидок, без отменённых чеков.',
  gp: 'Валовая прибыль = выручка − себестоимость проданного. Аренда, персонал и прочие расходы не учитываются.',
  mg: 'Валовая маржинальность = валовая прибыль / выручка (по продажам с известной себестоимостью).',
  wo: 'Стоимость списаний — списанное количество × себестоимость на дату списания.',
  ws: 'Доля списаний = списания / (себестоимость проданного + списания). Знаменатель — себестоимость всего выпуска.',
  check: 'Средний чек = выручка / число чеков. Не считается при фильтре по категории: чек содержит товары разных категорий.',
  oos: 'Доля рабочих точко-дней, когда товара не было в продаже.',
  soldout: 'Доля точко-дней, когда товар распродан к закрытию: спрос был выше выпуска.',
  turnover: 'Оборачиваемость = себестоимость продаж / средний запас за период.',
  dos: 'Дни запаса = остаток на конец периода / средняя дневная себестоимость продаж. Свежая продукция на следующий день не хранится.',
  cv: 'Коэффициент вариации недельных продаж: чем больше, тем нестабильнее спрос. X < 10%, Y 10–25%, Z > 25%.',
};
F.num = v => v == null || isNaN(v) ? '—' : Number.isInteger(v) ? NF0.format(v) : NF2.format(v);
const pctAx = v => NF0.format(v) + '%';
const sum = (a, f) => a.reduce((s, x) => s + f(x), 0);
const median = v => { const s = v.filter(x => x != null).sort((a, b) => a - b); return s.length ? (s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2) : null; };

/* ---------- Агрегации ---------- */
State.s = {days: 28, store: null, cat: null};
const range = () => [Math.max(0, LAST - State.s.days + 1), LAST];
function prevRange() { const [f, t] = range(), n = t - f + 1; return f - n < 0 ? null : [f - n, f - 1]; }
const periodText = ([f, t] = range()) => `${F.date(DAYS[f])} — ${F.date(DAYS[t])}`;
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
  if (st.cat != null) return null;
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
  const ps = prodSales(rg), res = {ps};
  for (const by of ['rev', 'gp']) {
    const items = PRODS.filter(p => p.is_active && (catFilter == null || p.c === catFilter))
      .map(p => ({id: p.product_id, p: p.p, value: +(by === 'rev' ? ps[p.p].rev : ps[p.p].revc - ps[p.p].cogs).toFixed(2)}));
    res[by] = classify(items);
  }
  return res;
}
window.checkAbc = function () {  // сверка с Python: последние 28 дней, вся сеть, пороги 80/95
  const r = abcFor([LAST - 27, LAST], null);
  let mism = 0, n = 0;
  for (const [by, col] of [['rev', 'abc_revenue'], ['gp', 'abc_profit']]) r[by].forEach(x => { n++; if (PRODS[x.p][col] !== x.cls) mism++; });
  return {checked: n, mismatches: mism};
};

/* ---------- Фильтры ---------- */
function buildFilters() {
  const per = $('#f-period');
  per.innerHTML = [[7, '7 дней'], [28, '28 дней'], [DAYS.length, `${DAYS.length} дней`]].map(([v, l]) => `<button data-v="${v}">${l}</button>`).join('');
  $$('button', per).forEach(b => b.onclick = () => State.set({days: +b.dataset.v}));
}
function syncFilters() {
  $$('#f-period button').forEach(b => { const on = +b.dataset.v === State.s.days; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on); });
  const act = [];
  if (State.s.store != null) act.push(`<button class="chip af" data-x="store" aria-label="Снять фильтр: ${esc(STORES[State.s.store].name)}">${esc(STORES[State.s.store].short)} <span aria-hidden="true">×</span></button>`);
  if (State.s.cat != null) act.push(`<button class="chip af" data-x="cat" aria-label="Снять фильтр: ${esc(CATS[State.s.cat].name)}">${esc(CATS[State.s.cat].name)} <span aria-hidden="true">×</span></button>`);
  $('#f-active').innerHTML = act.join('');
  $$('#f-active [data-x]').forEach(b => b.onclick = () => State.set({[b.dataset.x]: null}));
  // период виден только там, где он что-то меняет
  $('#f-period').style.display = ['overview', 'sales', 'store', 'assort', 'writeoffs', 'margin'].includes(Route.v) ? '' : 'none';
}
const where = () => [State.s.store != null ? STORES[State.s.store].name : 'вся сеть', State.s.cat != null ? CATS[State.s.cat].name : 'все категории'].join(' · ');

/* ---------- Навигация: путь вглубь и «хлебные крошки» ---------- */
const Route = {v: 'overview', si: null, from: null};
const TITLE = {overview: 'Сводка', sales: 'Выручка по точкам', assort: 'Ассортимент', writeoffs: 'Списания', margin: 'Маржа товаров',
  tasks: 'Задачи на проверку', reports: 'Отчёты', method: 'Справка'};
function crumbsOf() {
  const r = [['overview', 'Сводка']];
  if (Route.v === 'store') r.push(['sales', TITLE.sales], [null, STORES[Route.si].short]);
  else if (Route.v === 'assort') r.push(['sales', TITLE.sales], [null, TITLE.assort]);
  else if (Route.from != null && ['writeoffs', 'margin'].includes(Route.v)) r.push(['sales', TITLE.sales], ['store:' + Route.from, STORES[Route.from].short], [null, TITLE[Route.v]]);
  else if (Route.v !== 'overview') r.push([null, TITLE[Route.v]]);
  return r;
}
function go(v, opt = {}) {
  Route.v = v; Route.si = opt.si ?? (v === 'store' ? Route.si : null); Route.from = opt.from ?? null;
  Nav.go(v, false);
  history.replaceState(null, '', '#' + v + (v === 'store' ? '/' + Route.si : ''));
  const cr = crumbsOf();
  $('#crumbs').innerHTML = cr.length > 1 ? cr.map(([k, l], i) => i === cr.length - 1 ? `<span aria-current="page">${esc(l)}</span>`
    : `<button class="link" data-go="${k}">${esc(l)}</button><span class="sep" aria-hidden="true">›</span>`).join('') : '';
  bindGo($('#crumbs'));
  syncFilters();
  if (v === 'store') renderStore();
}
function bindGo(root = document) {
  $$('[data-go]', root).forEach(b => b.onclick = () => {
    const [v, a] = b.dataset.go.split(':');
    v === 'store' ? go('store', {si: +a}) : go(v);
  });
}
// бывшие вкладки и страницы → экраны новой структуры
const PAGE = {tasks: 'tasks', losses: 'writeoffs', wodetail: 'writeoffs', margin: 'margin', pdetail: 'margin',
  sales: 'sales', assort: 'assort', reports: 'reports', method: 'method', problems: 'tasks', analytics: 'sales'};
function goTo(v, tab) { go(PAGE[tab] || PAGE[v] || v); }
const chev = '<span class="chev" aria-hidden="true">›</span>';

/* ---------- Данные по точкам (общие для разбора) ---------- */
function storeRows(rg) {
  const st = {...State.s, store: null};
  const sS = aggSales(rg, (d, s) => s, st), sW = aggWo(rg, (d, s) => s, st), net = totals(rg, st);
  const pr = prevRange(), sP = pr ? aggSales(pr, (d, s) => s, st) : null;
  return {net, rows: STORES.map(s => {
    const a = sS.get(s.i); if (!a) return null;
    const m = mg(a), w = sW.get(s.i)?.cost ?? 0, ws = woShare(w, a.cogs), prev = sP?.get(s.i)?.rev;
    const bad = [];
    if (m < net.mg) bad.push('маржа ниже сети');
    if (ws > net.woShare) bad.push('списания выше сети');
    return {si: s.i, name: s.name, short: s.short, rev: a.rev, drev: prev ? ratio(a.rev - prev, prev) : null, mg: m, dmg: m - net.mg, wo: w, ws, dws: ws - net.woShare,
      flag: bad.length === 2 ? '<span class="pill p-bad">Хуже по обоим</span>' : bad.length ? `<span class="pill p-warn">${bad[0] === 'маржа ниже сети' ? 'Маржа ниже' : 'Списания выше'}</span>` : '<span class="hint">не хуже сети</span>'};
  }).filter(Boolean)};
}

/* ---------- Уровень 1. Сводка: одна фраза и четыре «двери» ---------- */
function renderOverview() {
  const rg = range(), pr = prevRange(), cur = totals(rg), prev = totals(pr), n = rg[1] - rg[0] + 1;
  $('#ov-verdict').innerHTML = `За ${n} дн. продано на <b>${F.rubc(cur.rev)}</b>${prev ? ` (${F.spct(ratio(cur.rev - prev.rev, prev.rev))})` : ''}, в списание ушло <b>${F.rubc(cur.wo)}</b>.`;
  const tasks = RECS.filter(r => State.s.cat == null || r.c === State.s.cat), high = tasks.filter(r => r.severity === 'Высокая').length;
  const lowMg = PRODS.filter(p => p.rules.has('R1')).length;
  const doors = [
    {go: 'sales', l: 'Выручка', tip: HELP.rev, v: F.rubc(cur.rev), d: deltaPill(cur.rev, prev?.rev), n: pr ? 'к прошлому периоду' : '', a: 'По точкам'},
    {go: 'margin', l: 'Маржа', tip: HELP.mg, v: F.pct(cur.mg), d: prev ? deltaPill(cur.mg, prev.mg, {kind: 'pp'}) : '', n: `высокая выручка при низкой марже: ${F.int(lowMg)}`, a: 'Какие товары'},
    {go: 'writeoffs', l: 'Списания', tip: HELP.wo, v: F.rubc(cur.wo), d: prev ? deltaPill(cur.woShare, prev.woShare, {kind: 'pp', invert: true}) : '', n: `${F.pct(cur.woShare)} выпуска`, a: 'Где теряем', lvl: 'warn'},
    {go: 'tasks', l: 'Задачи на проверку', tip: 'Задачи по 5 правилам: что проверить и почему. Задачи не утверждают причину.', v: F.int(high), n: `высокой важности · всего ${F.int(tasks.length)}`, a: 'Открыть', lvl: 'bad'},
  ];
  $('#doors').innerHTML = doors.map((d, i) => `<button class="door ${d.lvl || ''}" data-i="${i}">
    <span class="dl">${d.l}${tip(d.tip)}</span><span class="dv">${d.v}</span>
    <span class="dn">${d.d || ''}<span>${d.n}</span></span><span class="da">${d.a} ${chev}</span></button>`).join('');
  $$('#doors .door').forEach(b => b.onclick = e => {
    if (e.target.closest('.tip')) return;
    const d = doors[+b.dataset.i];
    if (d.go === 'tasks') { rcSev = 'Высокая'; rcRule = null; renderRecs(); }
    go(d.go);
  });
}

/* ---------- Уровень 2. Выручка по точкам ---------- */
let tStores, showAllStores = false;
function initSales() {
  tStores = new Table('t-stores', {
    cols: [{k: 'name', label: 'Точка', t: 'text'}, {k: 'rev', label: 'Выручка', t: 'rub'}, {k: 'mg', label: 'Маржа', t: 'pct', help: HELP.mg},
      {k: 'dmg', label: 'Маржа к сети', t: 'pp', help: 'Плюс — лучше сети'}, {k: 'ws', label: 'Доля списаний', t: 'pct', help: HELP.ws},
      {k: 'dws', label: 'Списания к сети', t: 'pp', help: 'Плюс — хуже сети'}],
    rows: [], page: 15, sort: 'rev', onRow: r => go('store', {si: r.si}), csv: 'stores',
  });
}
function renderSales() {
  const rg = range(), {net, rows} = storeRows(rg);
  tStores.setRows(rows);
  const sts = rows.slice().sort((a, b) => b.rev - a.rev), worse = rows.filter(r => r.dmg < 0 && r.dws > 0);
  $('#sl-verdict').innerHTML = sts.length ? `Больше всего продаёт ${esc(sts[0].short)}. Хуже сети и по марже, и по списаниям — <b>${worse.length} из ${rows.length}</b> точек.` : 'Нет продаж за период.';
  const mx = Math.max(...sts.map(s => s.rev), 1), list = showAllStores ? sts : sts.slice(0, 6);
  $('#sl-rank').innerHTML = list.map(s => `<button class="rk" data-go="store:${s.si}">
      <span class="rn">${esc(s.short)}</span><span class="rb"><i style="width:${(100 * s.rev / mx).toFixed(1)}%"></i></span>
      <span class="rv">${F.rubc(s.rev)}</span><span class="rd ${s.drev != null && s.drev < 0 ? 'neg' : 'pos'}">${s.drev != null ? F.spct(s.drev) : ''}</span>${chev}</button>`).join('')
    + (sts.length > 6 ? `<button class="rk more-row" id="sl-all">${showAllStores ? 'Свернуть' : `Показать все ${sts.length} точек`}</button>` : '');
  bindGo($('#sl-rank'));
  if ($('#sl-all')) $('#sl-all').onclick = () => { showAllStores = !showAllStores; renderSales(); };
  const cA = aggSales(rg, (d, s, c) => c, {...State.s, cat: null});
  const tr = sum([...cA.values()], a => a.rev), tg = sum([...cA.values()], a => gp(a));
  Charts.set('c-share', () => ({
    legend: {top: 0, left: 0}, grid: {left: 8, right: 40, top: 36, bottom: 4, containLabel: true},
    tooltip: {trigger: 'axis', axisPointer: {type: 'shadow'}, valueFormatter: v => NF1.format(v) + '%'},
    xAxis: Charts.axis('value', {axisLabel: {formatter: pctAx}}),
    yAxis: Charts.axis('category', {data: CATS.map(c => c.name).reverse(), axisLabel: {color: css('--text')}}),
    series: [['Доля в выручке', a => a.rev / tr, '--c2'], ['Доля в валовой прибыли', a => gp(a) / tg, '--c1']].map(([nm, f, col]) => ({
      name: nm, type: 'bar', barMaxWidth: 13, itemStyle: {color: css(col), borderRadius: [0, 6, 6, 0]},
      label: {show: true, position: 'right', formatter: p => NF1.format(p.value) + '%', color: css('--muted'), fontSize: 10.5},
      data: CATS.slice().reverse().map(c => +((cA.get(c.i) ? f(cA.get(c.i)) : 0) * 100).toFixed(2))})),
  }), p => { const c = CATS[CATS.length - 1 - p.dataIndex]; State.set({cat: State.s.cat === c.i ? null : c.i}); });
}

/* ---------- Уровень 3. Одна точка: категории, маржа и списания ---------- */
function renderStore() {
  if (Route.si == null) return;
  const s = STORES[Route.si], rg = range(), {net, rows} = storeRows(rg), r = rows.find(x => x.si === s.i);
  $('#h-st').textContent = s.name;
  if (!r) { $('#st-verdict').textContent = 'Нет продаж за период.'; $('#st-list').innerHTML = ''; return; }
  $('#st-verdict').innerHTML = `Выручка <b>${F.rubc(r.rev)}</b>. Маржа ${F.pct(r.mg)} — ${r.dmg >= 0 ? 'выше' : 'ниже'} сети на ${F.num1(Math.abs(r.dmg) * 100)} п. п.; списания ${F.pct(r.ws)} — ${r.dws > 0 ? 'выше' : 'ниже'} сети на ${F.num1(Math.abs(r.dws) * 100)} п. п.`;
  const st = {...State.s, store: s.i, cat: null}, cS = aggSales(rg, (d, x, c) => c, st), cW = aggWo(rg, (d, x, c) => c, st);
  const cats = CATS.map(c => { const a = cS.get(c.i); return a ? {c, rev: a.rev, mg: mg(a), ws: woShare(cW.get(c.i)?.cost ?? 0, a.cogs)} : null; }).filter(Boolean).sort((a, b) => b.rev - a.rev);
  $('#st-list').innerHTML = `<div class="rk head"><span class="rn">Категория</span><span class="rv">Выручка</span><span class="rv">Маржа</span><span class="rv">Списания</span><span></span></div>`
    + cats.map(x => `<div class="rk static"><span class="rn">${esc(x.c.name)}</span><span class="rv">${F.rubc(x.rev)}</span>
      <span class="rv ${x.mg < net.mg ? 'neg' : ''}">${F.pct(x.mg)}</span><span class="rv ${x.ws > net.woShare ? 'neg' : ''}">${F.pct(x.ws)}</span><span></span></div>`).join('');
  $('#st-next').innerHTML = `<button class="btn primary" id="st-wo">Списания точки ${chev}</button><button class="btn" id="st-mg">Маржа товаров точки ${chev}</button>`;
  $('#st-wo').onclick = () => { State.set({store: s.i}); go('writeoffs', {from: s.i}); $('#st-kpis').closest('details').open = true; };
  $('#st-mg').onclick = () => { State.set({store: s.i}); go('margin', {from: s.i}); };
}

/* ---------- 2. Ассортимент ---------- */
let grpSel = null, abcBy = 'rev', abcSel = null, xyzSel = null, tGrp, tProds, xyzChips;
const GROUPS = [
  {k: 'main', t: 'Основные источники выручки', d: 'класс A: вместе дают около 80% выручки за период', ac: '--c1', test: x => x.abcRev === 'A'},
  {k: 'stable', t: 'Стабильный спрос', d: 'класс X: недельные продажи колеблются меньше чем на 10%', ac: '--c5', test: x => x.p.xyz_class === 'X'},
  {k: 'unstable', t: 'Нестабильный спрос', d: 'классы Y и Z: продажи заметно меняются от недели к неделе', ac: '--c4', test: x => ['Y', 'Z'].includes(x.p.xyz_class)},
  {k: 'wo', t: 'Высокая доля списаний', d: 'правило R3: ≥ 20% выпуска и выше медианы категории на 15+ п. п.', ac: '--c3', test: x => x.p.rules.has('R3')},
  {k: 'check', t: 'Требуют проверки', d: 'есть хотя бы одна задача (правила R1–R5)', ac: '--bad', test: x => x.p.rules.size > 0},
];
const clsPill = c => `<span class="pill ${c === 'A' ? 'p-ok' : c === 'B' ? 'p-warn' : c === 'C' ? 'p-bad' : ''}">${c ?? '—'}</span>`;
const xyzPill = z => `<span class="pill ${z === 'X' ? 'p-vio' : z === 'Y' ? 'p-warn' : z === 'Z' ? 'p-bad' : ''}">${z ?? '—'}</span>`;
const XYZ_WORD = {X: 'стабильный', Y: 'колеблется', Z: 'нестабильный'};
function initAssortment() {
  tGrp = new Table('t-grp', {
    cols: [{k: 'name', label: 'Товар', t: 'text', w: 170}, {k: 'cat', label: 'Категория', t: 'text'}, {k: 'rev', label: 'Выручка', t: 'rub', help: HELP.rev},
      {k: 'share', label: 'Доля в выручке', t: 'pct', na: '0%'}, {k: 'mgv', label: 'Маржа', t: 'pct', help: HELP.mg},
      {k: 'demand', label: 'Спрос', t: 'text', help: HELP.cv, na: 'мало данных'}, {k: 'ws', label: 'Доля списаний', t: 'pct', help: HELP.ws + ' За последние 28 дней.'},
      {k: 'tasks', label: 'Задачи', t: 'html'}],
    rows: [], page: 15, search: ['name', 'sku'], onRow: r => productCard(r.p), csv: 'products', sort: 'rev',
  });
  $('#grp-reset').onclick = () => { grpSel = null; renderAssortment(); };
  const seg = $('#abc-by');
  seg.innerHTML = '<button data-v="rev">по выручке</button><button data-v="gp">по прибыли</button>';
  $$('button', seg).forEach(b => b.onclick = () => { abcBy = b.dataset.v; renderAssortment(); });
  xyzChips = chipGroup('as-chips', [], {allLabel: 'Любой XYZ', onChange: v => { xyzSel = v; renderAssortment(); }});
  tProds = new Table('t-prods', {
    cols: [{k: 'sku', label: 'Артикул', t: 'text'}, {k: 'name', label: 'Товар', t: 'text', w: 170}, {k: 'cat', label: 'Категория', t: 'text'},
      {k: 'qty', label: 'Продано, шт', t: 'int'}, {k: 'rev', label: 'Выручка', t: 'rub'}, {k: 'gpv', label: 'Прибыль', t: 'rub'},
      {k: 'mgv', label: 'Маржа', t: 'pct'}, {k: 'share', label: 'Доля', t: 'pct'}, {k: 'abc_h', label: 'ABC выр. / приб.', t: 'html', help: 'Класс по выручке и по валовой прибыли — считаются отдельно'},
      {k: 'xyz_h', label: 'XYZ', t: 'html'}, {k: 'cv', label: 'CV', t: 'pct', help: HELP.cv}, {k: 'mark', label: 'Пометка', t: 'text', w: 180, na: ''}],
    rows: [], page: 15, search: ['name', 'sku'], onRow: r => productCard(r.p), csv: 'abc_xyz', sort: 'rev',
  });
}
function renderAssortment() {
  const rg = range(), r = abcFor(rg), list = r[abcBy];
  const rev = Object.fromEntries(r.rev.map(x => [x.p, x])), gpc = Object.fromEntries(r.gp.map(x => [x.p, x]));
  $$('.an-eyebrow').forEach(el => el.textContent = `${periodText(rg)} · ${where()}`);
  $('#as-scope').innerHTML = `Ассортимент анализируется <b>по всей сети</b>${State.s.store != null ? ' — фильтр точки здесь не применяется' : ''}.
    Доля в выручке и класс ABC — за выбранный период; спрос (XYZ) — по ${D.meta.xyz_weeks} полным неделям до ${F.date(D.meta.d1)};
    доля списаний и задачи — за последние 28 дней.`;
  const items = r.rev.map(x => ({p: PRODS[x.p], abcRev: x.cls, x}));
  $('#grp').innerHTML = GROUPS.map(g => {
    const part = items.filter(g.test), rv = sum(part, i => r.ps[i.p.p].rev), tot = sum(items, i => r.ps[i.p.p].rev);
    return `<div class="grp ${grpSel === g.k ? 'on' : ''}" data-g="${g.k}" style="--ac:var(${g.ac})" aria-pressed="${grpSel === g.k}">
      <div class="gt">${g.t}</div><div class="gv">${part.length} <small>товаров</small></div>
      <div class="gd">${F.pct(ratio(rv, tot))} выручки · ${g.d}</div></div>`;
  }).join('');
  $$('#grp .grp').forEach(c => clickable(c, () => { grpSel = grpSel === c.dataset.g ? null : c.dataset.g; renderAssortment(); }));
  const g = GROUPS.find(x => x.k === grpSel);
  $('#grp-title').textContent = g ? `${g.t}: ${items.filter(g.test).length} товаров` : `Все товары: ${items.length}`;
  $('#grp-reset').hidden = !g;
  tGrp.setRows(items.filter(i => !g || g.test(i)).map(i => {
    const s = r.ps[i.p.p];
    return {p: i.p.p, name: i.p.name, sku: i.p.sku, cat: i.p.cat, rev: s.rev, share: i.x.share, mgv: ratio(s.revc - s.cogs, s.revc),
      demand: i.p.xyz_class ? `${XYZ_WORD[i.p.xyz_class]} (${i.p.xyz_class})` : null, ws: i.p.write_off_share,
      tasks: i.p.rules.size ? [...i.p.rules].sort().map(x => `<span class="pill p-warn" title="${esc(D.rule_titles[x])}">${x}</span>`).join(' ') : '<span class="na">нет</span>'};
  }));

  // профессиональный режим
  $$('#abc-by button').forEach(b => b.classList.toggle('on', b.dataset.v === abcBy));
  const other = abcBy === 'rev' ? gpc : rev;
  const cards = ['A', 'B', 'C'].map(c => { const part = list.filter(x => x.cls === c); return {c, n: part.length, sh: sum(part, x => x.share || 0), v: sum(part, x => x.value)}; });
  const desc = {A: '≈ 80% вклада', B: 'следующие ≈ 15%', C: 'остальные ≈ 5% и без продаж'};
  $('#abc-kpis').innerHTML = cards.map(k => `<div class="card kpi click" data-c="${k.c}" style="${abcSel === k.c ? 'box-shadow:0 0 0 3px var(--bd2)' : ''}" aria-pressed="${abcSel === k.c}">
    <div class="eyebrow"><span class="dot ${k.c === 'A' ? 'ok' : k.c === 'B' ? 'warn' : 'bad'}"></span>Класс ${k.c} · ${abcBy === 'rev' ? 'выручка' : 'прибыль'}</div>
    <div class="kpi-value">${k.n} <span style="font-size:15px;color:var(--muted)">товаров</span></div>
    <div class="kpi-foot"><span class="delta flat">${F.pct(k.sh)}</span><span>${desc[k.c]} · ${F.rubc(k.v)}</span></div></div>`).join('')
    + `<div class="card kpi"><div class="eyebrow"><span class="dot"></span>Классы расходятся${tip('Класс по выручке и по прибыли считаются отдельно и могут не совпадать')}</div>
    <div class="kpi-value">${list.filter(x => other[x.p]?.cls !== x.cls).length}</div><div class="kpi-foot"><span>товаров: класс по выручке ≠ по прибыли</span></div></div>`;
  $$('#abc-kpis [data-c]').forEach(c => clickable(c, () => { abcSel = abcSel === c.dataset.c ? null : c.dataset.c; renderAssortment(); }));
  const pos = list.filter(x => x.value > 0);
  Charts.set('c-pareto', () => ({
    grid: {left: 8, right: 8, top: 30, bottom: 26, containLabel: true}, legend: {show: false},
    tooltip: {trigger: 'axis', formatter: ps => { const x = pos[ps[0].dataIndex], p = PRODS[x.p];
      return `<b>${esc(p.name)}</b><br>${abcBy === 'rev' ? 'выручка' : 'прибыль'} ${F.rub(x.value)} · класс ${x.cls}<br>накопленная доля ${F.pct(x.cum)}`; }},
    xAxis: Charts.axis('category', {data: pos.map((x, i) => i + 1), axisLabel: {interval: 19}, splitLine: {show: false}, name: 'товары по убыванию вклада', nameLocation: 'middle', nameGap: 24, nameTextStyle: {color: css('--dim')}}),
    yAxis: [Charts.axis('value', {axisLabel: {formatter: v => NF0.format(v / 1000) + ' тыс ₽'}}), Charts.axis('value', {max: 100, splitLine: {show: false}, axisLabel: {formatter: pctAx}})],
    series: [{type: 'bar', barCategoryGap: '15%', data: pos.map(x => ({value: x.value, itemStyle: {
      color: css(x.cls === 'A' ? '--c1' : x.cls === 'B' ? '--c2' : '--c7'), opacity: !abcSel || abcSel === x.cls ? 1 : 0.3}}))},
    {type: 'line', yAxisIndex: 1, data: pos.map(x => +(x.cum * 100).toFixed(2)), symbol: 'none', smooth: true, lineStyle: {width: 2.5, color: css('--c3')},
      markLine: {symbol: 'none', silent: true, lineStyle: {type: 'dashed', color: css('--dim')}, label: {formatter: p => 'граница ' + p.value + '%', color: css('--muted'), position: 'insideStartTop'},
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
      itemStyle: {borderRadius: 10, borderColor: css('--glass'), borderWidth: 4}}],
  }), p => {
    const a = AS[p.value[1]], z = XS[p.value[0]];
    if (abcSel === a && xyzSel === z) { abcSel = null; xyzSel = null; } else { abcSel = a; xyzSel = z; }
    renderAssortment();
  });
  const xc = {}; list.forEach(x => { if (!abcSel || x.cls === abcSel) xc[xyzOf(x.p)] = (xc[xyzOf(x.p)] || 0) + 1; });
  xyzChips.update(XS.map(z => ({v: z, label: z === '—' ? 'XYZ не определён' : `XYZ: ${z} — ${XYZ_WORD[z]}`, n: xc[z] || 0})));
  xyzChips.set(xyzSel);
  tProds.setRows(list.map(x => {
    const p = PRODS[x.p], s = r.ps[x.p];
    return {p: x.p, sku: p.sku, name: p.name, cat: p.cat, qty: s.qty, rev: s.rev, gpv: s.revc - s.cogs, mgv: ratio(s.revc - s.cogs, s.revc),
      share: x.share, cls: x.cls, xyz: xyzOf(x.p), abc_h: `${clsPill(rev[x.p]?.cls)} ${clsPill(gpc[x.p]?.cls)}`, xyz_h: xyzPill(p.xyz_class),
      cv: p.cv, mark: [x.note, p.xyz_note].filter(Boolean).join('; ')};
  }));
  tProds.filter(x => (!abcSel || x.cls === abcSel) && (!xyzSel || x.xyz === xyzSel));
}

/* ---------- Карточка товара ---------- */
function productCard(pIdx) {
  const p = PRODS[pIdx], w = D.weekly[String(pIdx)] || [], recs = RECS.filter(r => r.p === pIdx);
  const rg = range(), daily = new Map();
  for (const [d, pp, rev, revc, cogs] of D.pday) if (pp === pIdx && d >= rg[0] && d <= rg[1]) daily.set(d, {rev, gp: revc - cogs});
  const dIdx = []; for (let d = rg[0]; d <= rg[1]; d++) dIdx.push(d);
  Drawer.open(`<div class="eyebrow"><span class="dot ${recs.some(r => r.severity === 'Высокая') ? 'bad' : ''}"></span>${esc(p.cat)} · ${esc(p.sku)}${p.is_active ? '' : ' · выведен из ассортимента'}</div>
    <h2>${esc(p.name)}</h2><div class="meta">Показатели — по всей сети за последние 28 дней (до ${F.date(D.meta.d1)}).</div>
    ${recs.length ? `<h3 style="margin:6px 0">Что проверить</h3>` + recs.map(r => `<div class="callout ${r.severity === 'Высокая' ? 'bad' : r.severity === 'Средняя' ? 'warn' : ''}">
      <span class="pill ${SEV[r.severity].p}">${r.severity}</span> <b>${esc(r.rule)} · ${esc(r.problem)}.</b><br>
      <b>Доказательство:</b> ${esc(r.value)}.<br><b>Основание:</b> ${esc(r.basis)}.<br><b>Возможная причина (не установлена):</b> ${esc(r.possible_cause)}.<br><b>Проверить:</b> ${esc(r.action)}.<br><span class="hint"><b>Ограничения:</b> ${esc(r.limitations)}.</span></div>`).join('')
    : '<div class="callout ok">Задач по этому товару нет.</div>'}
    <div class="mini"><div><span>Выручка · маржа</span><b>${F.rubc(p.revenue)} · ${F.pct(p.gross_margin)}</b></div>
      <div><span>Спрос (XYZ) ${tip(HELP.cv)}</span><b>${p.xyz_class ? XYZ_WORD[p.xyz_class] + ' · CV ' + F.pct(p.cv) : 'мало данных'}</b></div>
      <div><span>Доля списаний ${tip(HELP.ws)}</span><b>${F.pct(p.write_off_share)}</b></div>
      <div><span>Нет в продаже ${tip(HELP.oos)}</span><b>${F.pct(p.oos_share)}</b></div>
      <div><span>ABC выручка / прибыль</span><b>${clsPill(p.abc_revenue)} ${clsPill(p.abc_profit)}</b></div>
      <div><span>Распродано к закрытию ${tip(HELP.soldout, true)}</span><b>${F.pct(p.sold_out_share)}</b></div></div>
    <div class="card-head" style="margin-top:12px"><h3>Недельный спрос, шт</h3></div>
    <p class="hint" style="margin:0 0 4px">Оранжевые недели не учитываются в оценке спроса: товар был доступен меньше чем в 80% точко-дней, низкие продажи там не означают низкий спрос.</p>
    <div class="chart short" id="c-week" role="img" aria-label="Недельный спрос"></div>
    <div class="card-head" style="margin-top:8px"><h3>Выручка и прибыль по дням, ₽ · ${periodText()}</h3></div><div class="chart short" id="c-pday" role="img" aria-label="Выручка по дням"></div>
    ${p.xyz_note ? `<div class="callout">Спрос: ${esc(p.xyz_note)}</div>` : ''}`, () => {
    Charts.set('c-week', () => ({
      grid: {left: 8, right: 8, top: 30, bottom: 4, containLabel: true}, legend: {top: 0, left: 0},
      tooltip: {trigger: 'axis', axisPointer: {type: 'shadow'}, formatter: ps => { const x = w[ps[0].dataIndex];
        return `неделя с ${F.date(x[0])}<br><b>${F.int(x[1])} шт</b><br>доступность ${F.pct(x[2])}`; }},
      xAxis: Charts.axis('category', {data: w.map(x => F.dshort(x[0])), splitLine: {show: false}}), yAxis: Charts.axis('value'),
      series: [{name: 'Учтена в оценке спроса', type: 'bar', stack: 'w', barMaxWidth: 26, itemStyle: {color: css('--c1'), borderRadius: [6, 6, 0, 0]}, data: w.map(x => x[2] >= 0.8 ? x[1] : '-')},
        {name: 'Не учтена: товара часто не было', type: 'bar', stack: 'w', barMaxWidth: 26, itemStyle: {color: css('--c4'), borderRadius: [6, 6, 0, 0]}, data: w.map(x => x[2] < 0.8 ? x[1] : '-')}],
    }));
    Charts.set('c-pday', () => ({
      grid: {left: 8, right: 8, top: 30, bottom: 4, containLabel: true}, legend: {top: 0, left: 0}, tooltip: {trigger: 'axis', valueFormatter: F.rub},
      xAxis: Charts.axis('category', {data: dIdx.map(d => F.dshort(DAYS[d])), splitLine: {show: false}}), yAxis: Charts.axis('value'),
      series: [{name: 'Выручка', type: 'line', smooth: true, symbol: 'none', data: dIdx.map(d => daily.get(d)?.rev ?? 0), lineStyle: {width: 2.5, color: css('--c1')}, areaStyle: {color: css('--c1') + '22'}},
        {name: 'Валовая прибыль', type: 'line', smooth: true, symbol: 'none', data: dIdx.map(d => daily.get(d)?.gp ?? 0), lineStyle: {width: 2, color: css('--c5')}}],
    }));
  });
}

/* ---------- 3. Прибыльность ---------- */
let tPcat, tPst, tProblems;
const FACTORS_GROUP = 'Структура продаж (больше дешёвых позиций), скидки, рост себестоимости — не установлено, проверить';
function initProfit() {
  const base = [{k: 'mgv', label: 'Маржа', t: 'pct', help: HELP.mg}, {k: 'base', label: 'Сеть', t: 'pct', help: 'База сравнения — маржинальность сети за тот же период и с теми же фильтрами'},
    {k: 'diff', label: 'Отклонение', t: 'pp'}];
  tPcat = new Table('t-pcat', {cols: [{k: 'name', label: 'Категория', t: 'text'}, ...base, {k: 'gpv', label: 'Прибыль', t: 'rub'}],
    rows: [], page: 8, sort: 'diff', dir: 1, onRow: r => State.set({cat: State.s.cat === r.ci ? null : r.ci}), empty: 'Нет категорий ниже сети'});
  tPst = new Table('t-pst', {cols: [{k: 'name', label: 'Точка', t: 'text'}, ...base, {k: 'gpv', label: 'Прибыль', t: 'rub'}],
    rows: [], page: 8, sort: 'diff', dir: 1, onRow: r => State.set({store: State.s.store === r.si ? null : r.si}), empty: 'Нет точек ниже сети'});
  tProblems = new Table('t-problems', {
    cols: [{k: 'name_h', label: 'Товар', t: 'html', w: 200}, {k: 'mg_h', label: 'Маржа', t: 'html', help: HELP.mg + ' Ниже — разница с маржой сети, п. п.'},
      {k: 'rev', label: 'Выручка', t: 'rub'}, {k: 'next_h', label: 'Что проверить', t: 'html', w: 380, help: 'Ниже — возможные факторы: гипотезы, а не установленные причины'}],
    rows: [], page: 12, search: ['name', 'sku'], onRow: r => productCard(r.p), csv: 'low_margin', sort: 'diff', dir: 1,
  });
}
function renderProfit() {
  const rg = range(), ps = prodSales(rg);
  const netAll = mg(aggSales(rg, null, {store: null, cat: null}).get(0));
  $$('.pr-eyebrow').forEach(el => el.textContent = `${periodText(rg)} · ${where()}`);
  const cA = aggSales(rg, (d, s, c) => c, {...State.s, cat: null}), netC = mg(aggSales(rg, null, {...State.s, cat: null}).get(0));
  const sA = aggSales(rg, (d, s) => s, {...State.s, store: null}), netS = mg(aggSales(rg, null, {...State.s, store: null}).get(0));
  $('#pf-net').textContent = `база сравнения — маржинальность сети ${F.pct(netC)}`;
  tPcat.setRows(CATS.map(c => ({ci: c.i, name: c.name, mgv: mg(cA.get(c.i)), base: netC, diff: mg(cA.get(c.i)) - netC, gpv: gp(cA.get(c.i))})).filter(x => x.diff < 0));
  tPst.setRows(STORES.map(s => ({si: s.i, name: s.name, mgv: mg(sA.get(s.i)), base: netS, diff: mg(sA.get(s.i)) - netS, gpv: gp(sA.get(s.i))})).filter(x => x.mgv != null && x.diff < 0));
  const pts = PRODS.map(p => ({p, s: ps[p.p]})).filter(x => x.s.rev > 0 && (State.s.cat == null || x.p.c === State.s.cat));
  $('#pf-hint').textContent = `убыток или маржа ниже сети (${F.pct(netAll)}) более чем на 5 п. п. — порог правила R1 · клик — карточка`;
  const r1 = Object.fromEntries(RECS.filter(r => r.rule === 'R1' || r.rule === 'R5').map(r => [r.p, r]));
  tProblems.setRows(pts.map(x => { const g = x.s.revc - x.s.cogs, m = ratio(g, x.s.revc);
    const prob = g < 0 ? '<span class="pill p-bad">Убыток</span>' : m != null && m < netAll - 0.05 ? '<span class="pill p-warn">Маржа ниже сети на 5+ п. п.</span>' : '';
    const rec = r1[x.p.p];
    return {p: x.p.p, sku: x.p.sku, name: x.p.name, cat: x.p.cat, rev: x.s.rev, mgv: m, base: netAll, diff: m == null ? null : m - netAll, prob,
      name_h: `${esc(x.p.name)}<br><span class="hint">${esc(x.p.cat)}</span>${g < 0 ? ' <span class="pill p-bad">убыток</span>' : ''}`,
      factors: rec ? rec.possible_cause : 'Рост себестоимости, скидки или промо, цена ниже рынка — не установлено',
      next: rec ? rec.action : 'Проверить себестоимость (техкарта, закупка), действующую цену и скидки'};
  }).map(r => ({...r, mg_h: `${F.pct(r.mgv)}<div class="hint">${r.diff == null ? '' : (r.diff >= 0 ? '+' : '−') + F.num1(Math.abs(r.diff) * 100) + ' п. п.'}</div>`,
    next_h: `${esc(r.next)}<div class="hint">${esc(r.factors)}</div>`})).filter(r => r.prob));
  const nLow = tProblems.rows.length, nLoss = tProblems.rows.filter(r => r.prob.includes('Убыток')).length;
  $('#mg-verdict').innerHTML = `Маржа сети ${F.pct(netAll)}. Ниже неё более чем на 5 п. п. — <b>${F.int(nLow)}</b> товаров${nLoss ? `, из них в убытке — <b>${nLoss}</b>` : ''}.`;
  const maxGp = Math.max(...pts.map(x => Math.max(1, x.s.revc - x.s.cogs)));
  Charts.set('c-scatter', () => ({
    legend: {top: 0, left: 0}, grid: {left: 8, right: 24, top: 40, bottom: 28, containLabel: true},
    tooltip: {trigger: 'item', formatter: p => `<b>${esc(p.data.n)}</b><br>выручка ${F.rub(p.data.value[0])}<br>маржа ${NF1.format(p.data.value[1])}%`},
    xAxis: Charts.axis('log', {name: 'выручка, ₽ (логарифмическая шкала)', nameLocation: 'middle', nameGap: 26, nameTextStyle: {color: css('--dim')},
      axisLabel: {formatter: v => v >= 1e6 ? NF0.format(v / 1e6) + ' млн' : NF0.format(v / 1000) + ' тыс'}}),
    yAxis: Charts.axis('value', {scale: true, axisLabel: {formatter: pctAx}}),
    series: CATS.map((c, i) => ({name: c.name, type: 'scatter', itemStyle: {color: PAL()[i], opacity: 0.8},
      data: pts.filter(x => x.p.c === c.i).map(x => { const g = x.s.revc - x.s.cogs;
        return {n: x.p.name, pi: x.p.p, value: [+x.s.rev.toFixed(0), +((ratio(g, x.s.revc) ?? 0) * 100).toFixed(2)], symbolSize: 8 + 24 * Math.sqrt(Math.max(1, g) / maxGp)}; }),
      markLine: i === 0 ? {symbol: 'none', silent: true, lineStyle: {type: 'dashed', color: css('--bad')}, label: {formatter: 'сеть − 5 п. п.', color: css('--bad'), position: 'insideEndTop'},
        data: [{yAxis: +((netAll - 0.05) * 100).toFixed(2)}]} : undefined})),
  }), p => productCard(p.data.pi));
}

/* ---------- 4. Списания ---------- */
let woReason = null, woKind = null, tWo, kindChips, tWost;
function initStock() {
  kindChips = chipGroup('st-chips', [], {allLabel: 'Все товары', onChange: v => { woKind = v; renderStock(); }});
  tWo = new Table('t-wo', {
    cols: [{k: 'name_h', label: 'Товар', t: 'html', w: 220}, {k: 'write_off_cost', label: 'Списано, ₽', t: 'rub', help: HELP.wo},
      {k: 'ws_h', label: 'Доля списаний', t: 'html', help: HELP.ws + ' Ниже — медиана категории (база сравнения).'},
      {k: 'oos_share', label: 'Нет в продаже', t: 'pct', help: HELP.oos},
      {k: 'kind_h', label: 'Отклонение', t: 'html'}],
    rows: [], page: 10, search: ['name'], onRow: r => productCard(r.p), csv: 'write_offs', sort: 'write_off_cost',
  });
  const med = {};
  CATS.forEach(c => { med[c.i] = median(PRODS.filter(p => p.c === c.i && p.is_active).map(p => p.write_off_share)); });
  tWo.base = PRODS.filter(p => p.is_active).map(p => {
    const kind = p.rules.has('R3') ? 'Высокие списания (R3)' : p.rules.has('R2') ? 'Часто нет в продаже (R2)' : 'Без отклонений';
    return {...p, med: med[p.c], name_h: `${esc(p.name)}<div class="hint">${esc(p.cat)}</div>`,
      ws_h: `${F.pct(p.write_off_share)}<div class="hint">медиана ${F.pct(med[p.c])}</div>`, dev: p.write_off_share != null && med[p.c] != null ? p.write_off_share - med[p.c] : null, kind,
      // коротко и без зелёного «всё хорошо» в каждой строке: выделяются только отклонения
      kind_h: kind.startsWith('Без') ? '<span class="hint">нет</span>' : `<span class="pill ${kind.startsWith('Высокие') ? 'p-bad' : 'p-warn'}">${kind.replace(/ \(R\d\)/, '')}</span>`};
  });
  tWost = new Table('t-wost', {
    cols: [{k: 'name', label: 'Точка', t: 'text'}, {k: 'wo', label: 'Списано, ₽', t: 'rub'}, {k: 'ws', label: 'Доля', t: 'pct', help: HELP.ws},
      {k: 'dws', label: 'К сети', t: 'pp', help: 'Разница доли списаний точки и сети. Плюс — хуже сети.'}],
    rows: [], page: 8, sort: 'dws', onRow: r => State.set({store: State.s.store === r.si ? null : r.si}),
  });
}
function renderStock() {
  const rg = range(), cur = totals(rg), prev = totals(prevRange());
  const byR = aggWo(rg, (d, s, c, r) => r), top = [...byR.entries()].sort((a, b) => b[1].cost - a[1].cost)[0];
  $('#st-summary').innerHTML = `За ${rg[1] - rg[0] + 1} дн. списано продукции на <b>${F.rubc(cur.wo)}</b> — <b>${F.pct(cur.woShare)}</b> себестоимости выпуска.
    ${top ? `Главная причина — «${REASONS[top[0]].toLowerCase()}» (${F.pct(ratio(top[1].cost, cur.wo))} стоимости).` : ''} Ниже — товары, на которых теряется больше всего.`;
  const k = [
    {l: 'Потери на списаниях', h: HELP.wo, dot: 'bad', v: F.rubc(cur.wo), d: deltaPill(cur.wo, prev?.wo, {invert: true}), n: `${F.int(cur.woQty)} шт`},
    {l: 'Доля списаний', h: HELP.ws, dot: 'warn', v: F.pct(cur.woShare), d: prev ? deltaPill(cur.woShare, prev.woShare, {kind: 'pp', invert: true}) : '', n: 'от себестоимости выпуска'},
    {l: 'Нет в продаже', h: HELP.oos, dot: 'bad', v: F.pct(cur.oos), d: prev ? deltaPill(cur.oos, prev.oos, {kind: 'pp', invert: true}) : '', n: 'рабочих точко-дней'},
    {l: 'Распродано к закрытию', h: HELP.soldout, v: F.pct(cur.soldout), n: 'спрос выше выпуска'},
    {l: 'Оборачиваемость', h: HELP.turnover, v: cur.turnover != null ? F.num1(cur.turnover) + ' раз' : null, n: 'за период'},
    {l: 'Дни запаса на конец', h: HELP.dos, v: F.num1(cur.dos), n: 'свежая продукция не хранится'},
  ];
  $('#st-kpis').innerHTML = k.map(x => `<div class="card kpi"><div class="eyebrow"><span class="dot ${x.dot || ''}"></span>${x.l}${tip(x.h)}</div>
    <div class="kpi-value">${x.v ?? NA}</div><div class="kpi-foot">${x.d || ''}<span>${x.n}${x.d ? ' · к предыдущему периоду' : ''}</span></div></div>`).join('');
  Charts.set('c-reasons', () => ({
    tooltip: {trigger: 'item', formatter: p => `${p.name}<br><b>${F.rub(p.value)}</b> · ${NF1.format(p.percent)}%`},
    legend: {bottom: 0, top: 'auto', left: 'center'},
    series: [{type: 'pie', radius: ['40%', '66%'], center: ['50%', '42%'], padAngle: 2, itemStyle: {borderRadius: 8},
      label: {formatter: p => p.percent >= 1 ? NF0.format(p.percent) + '%' : '', fontWeight: 700, color: css('--text')},
      data: REASONS.map((r, i) => ({name: r, ri: i, value: +(byR.get(i)?.cost ?? 0).toFixed(0), itemStyle: {color: css(RCOL[i]), opacity: woReason == null || woReason === i ? 1 : 0.3}}))}],
  }), p => { woReason = woReason === p.data.ri ? null : p.data.ri; renderStock(); });
  const dIdx = []; for (let d = rg[0]; d <= rg[1]; d++) dIdx.push(d);
  const byDR = aggWo(rg, (d, s, c, r) => d * 10 + r);
  Charts.set('c-woday', () => ({
    legend: {top: 0, left: 0}, grid: {left: 8, right: 8, top: 36, bottom: 4, containLabel: true},
    tooltip: {trigger: 'axis', axisPointer: {type: 'shadow'}, valueFormatter: F.rub},
    xAxis: Charts.axis('category', {data: dIdx.map(d => F.dshort(DAYS[d])), splitLine: {show: false}}),
    yAxis: Charts.axis('value', {axisLabel: {formatter: v => NF0.format(v / 1000) + ' тыс'}}),
    series: REASONS.map((r, i) => ({name: r, type: 'bar', stack: 'r', barMaxWidth: 18, itemStyle: {color: css(RCOL[i]), opacity: woReason == null || woReason === i ? 1 : 0.2},
      data: dIdx.map(d => +(byDR.get(d * 10 + i)?.cost ?? 0).toFixed(0))})),
  }), p => { woReason = woReason === p.seriesIndex ? null : p.seriesIndex; renderStock(); });
  const share = (key, st) => { const s = aggSales(rg, key, st), w = aggWo(rg, key, st, woReason); return k2 => s.get(k2) ? {ws: woShare(w.get(k2)?.cost ?? 0, s.get(k2).cogs), wo: w.get(k2)?.cost ?? 0} : null; };
  const fc = share((d, s, c) => c, {...State.s, cat: null});
  const cs = CATS.map(c => ({c, v: fc(c.i)?.ws})).filter(x => x.v != null).sort((a, b) => a.v - b.v);
  Charts.set('c-wocat', () => ({
    grid: {left: 8, right: 44, top: 6, bottom: 4, containLabel: true}, tooltip: {trigger: 'axis', axisPointer: {type: 'shadow'}, valueFormatter: v => NF1.format(v) + '%'},
    xAxis: Charts.axis('value', {axisLabel: {formatter: pctAx}}), yAxis: Charts.axis('category', {data: cs.map(x => x.c.name), axisLabel: {color: css('--text')}}),
    series: [{type: 'bar', barMaxWidth: 20, label: {show: true, position: 'right', formatter: p => NF1.format(p.value) + '%', color: css('--muted')},
      data: cs.map(x => ({value: +(x.v * 100).toFixed(2), ci: x.c.i, itemStyle: {borderRadius: [0, 8, 8, 0], color: css('--c3'), opacity: State.s.cat == null || State.s.cat === x.c.i ? 1 : 0.3}}))}],
  }), p => State.set({cat: State.s.cat === p.data.ci ? null : p.data.ci}));
  const fs = share((d, s) => s, {...State.s, store: null});
  const netW = (() => { const s = aggSales(rg, null, {...State.s, store: null}).get(0), w = aggWo(rg, null, {...State.s, store: null}, woReason).get(0); return s ? woShare(w?.cost ?? 0, s.cogs) : null; })();
  tWost.setRows(STORES.map(s => { const v = fs(s.i); return v ? {si: s.i, name: s.name, wo: v.wo, ws: v.ws, dws: v.ws - netW} : null; }).filter(Boolean));
  const base = tWo.base.filter(r => State.s.cat == null || r.c === State.s.cat);
  kindChips.update(['Высокие списания (R3)', 'Часто нет в продаже (R2)', 'Без отклонений'].map(v => ({v, label: v, n: base.filter(r => r.kind === v).length,
    cls: v.startsWith('Высокие') ? 'bad' : v.startsWith('Без') ? 'ok' : 'warn'})));
  kindChips.set(woKind);
  tWo.setRows(tWo.base);
  tWo.filter(r => (State.s.cat == null || r.c === State.s.cat) && (!woKind || r.kind === woKind));
}

/* ---------- 5. Задачи ---------- */
let rcSev = null, rcRule = null, rcShown = 15, ruleChips;
function initRecs() {
  ruleChips = chipGroup('rc-rules', [], {allLabel: 'Все правила', onChange: v => { rcRule = v; rcShown = 15; renderRecs(); }});
  $('#rc-d1').textContent = F.date(D.meta.d1);
  tRecs = new Table('rc-list', {
    cols: [{k: 'obj_h', label: 'Товар', t: 'html', w: 230}, {k: 'prob_h', label: 'Проблема', t: 'html', w: 300, help: 'Ниже — цифры, на которых основана задача'},
      {k: 'action', label: 'Что проверить', t: 'text', w: 320}],
    rows: [], page: 12, search: ['product_name', 'problem'], csv: 'tasks', sort: 'ord', dir: 1, onRow: r => productCard(r.p),
  });
}
let tRecs;
function renderRecs() {
  if (rcRule) $('#rc-rules').closest('details').open = true;  // фильтр задан с обзора — показываем его
  const scope = RECS.filter(r => State.s.cat == null || r.c === State.s.cat);
  const SD = {'Высокая': 'высокая важность — в первую очередь', 'Средняя': 'средняя — в плановом порядке', 'Низкая': 'низкая — к сведению'};
  $('#rc-kpis').innerHTML = SEVS.map(s => `<button class="grp-b ${rcSev === s ? 'on' : ''} ${s === 'Высокая' ? 'bad' : s === 'Средняя' ? 'warn' : ''}" data-s="${s}" aria-pressed="${rcSev === s}">
    <span class="gv">${scope.filter(r => r.severity === s).length}</span><span class="gl">${SD[s]}</span></button>`).join('');
  $$('#rc-kpis [data-s]').forEach(c => c.onclick = () => { rcSev = rcSev === c.dataset.s ? null : c.dataset.s; rcShown = 15; renderRecs(); });
  const nh = scope.filter(r => r.severity === 'Высокая').length;
  $('#tk-verdict').innerHTML = `Всего <b>${F.int(scope.length)}</b> задач, из них <b>${F.int(nh)}</b> — в первую очередь. Нажмите на строку — откроется карточка товара.`;
  const s2 = scope.filter(r => !rcSev || r.severity === rcSev);
  ruleChips.update(Object.keys(D.rule_titles).map(k => ({v: k, label: `${k} · ${D.rule_titles[k]}`, n: s2.filter(r => r.rule === k).length})));
  ruleChips.set(rcRule);
  const list = s2.filter(r => !rcRule || r.rule === rcRule).sort((a, b) => SEVS.indexOf(a.severity) - SEVS.indexOf(b.severity));
  tRecs.setRows(list.map((r, i) => ({...r, ord: i, sev_h: `<span class="pill ${SEV[r.severity].p}">${r.severity}</span>`,
    obj_h: `${esc(r.product_name)}<div class="hint">${esc(r.category_name)} · <span class="pill ${SEV[r.severity].p}">${r.severity}</span></div>`,
    prob_h: `${esc(r.problem)}<div class="hint">${esc(r.value)}</div>`})));
}

/* ---------- 6. Методика и данные ---------- */
const COL_RU = D.col_ru;
const colType = (c, isNum) => /share|margin|pct|cum_/.test(c) && c !== 'margin_rank' ? 'pct' : /revenue|cogs|profit|cost|check|value|rev_|gp_/.test(c) && isNum && !/rank/.test(c) ? 'rub2' : isNum ? 'num' : 'text';
const TECH = ['Откуда данные', 'Как соединяются', 'Как проверено'];
function reportHighlights(q) {
  const [nameCol, valCol, fmt, order] = q.human.highlight, ni = q.cols.indexOf(nameCol), vi = q.cols.indexOf(valCol);
  if (!q.rows.length) return '<p class="hint">Нет строк за период.</p>';
  let rows = q.rows.slice();
  if (order !== 'none') rows.sort((a, b) => ((a[vi] ?? 0) - (b[vi] ?? 0)) * (order === 'desc' ? -1 : 1));
  const nm = v => nameCol === 'sale_date' ? F.date(v) : esc(v);
  const val = v => fmt === 'text' ? esc(v) : F[fmt](v);
  return `<div class="hint">${esc(q.human.lead)}:</div><ol>${rows.slice(0, 3).map(r => `<li>${nm(r[ni])} — <b>${val(r[vi])}</b></li>`).join('')}</ol>`;
}
function initReports() {
  $('#m-formulas').innerHTML = `<h3 style="margin-top:0">Формулы показателей</h3>
    <ul>${[['Выручка', HELP.rev], ['Валовая прибыль', HELP.gp], ['Маржинальность', HELP.mg], ['Доля списаний', HELP.ws], ['Средний чек', HELP.check],
      ['Нет в продаже', HELP.oos], ['Оборачиваемость', HELP.turnover], ['Дни запаса', HELP.dos]].map(([a, b]) => `<li><b>${a}.</b> ${b}</li>`).join('')}</ul>
    <h3>ABC-анализ</h3><p>Товары сортируются по вкладу (выручке или валовой прибыли) от большего к меньшему; накопленная доля до товара &lt; 80% — класс A, до 95% — B, остальные — C.
      Товар на границе остаётся в старшем классе. Выручка и прибыль классифицируются отдельно. Товары без продаж — C.</p>
    <h3>XYZ-анализ</h3><p>${HELP.cv} Окно — ${D.meta.xyz_weeks} полных недель; недели, когда товар был доступен меньше чем в 80% точко-дней, не учитываются; нужно не меньше 6 недель.</p>`;
  $('#m-rules').innerHTML = `<h3 style="margin-top:0">Правила задач</h3>
    <ul><li><b>R1 · ${D.rule_titles.R1}.</b> Класс A по выручке и маржа ниже сетевой более чем на 5 п. п. Важность — высокая.</li>
      <li><b>R2 · ${D.rule_titles.R2}.</b> Спрос X или Y и товара не было в продаже в 3% и более рабочих точко-дней. X — высокая важность, Y — средняя.</li>
      <li><b>R3 · ${D.rule_titles.R3}.</b> Доля списаний ≥ 20% и выше медианы своей категории на 15+ п. п.; на 30+ п. п. — высокая важность.</li>
      <li><b>R4 · ${D.rule_titles.R4}.</b> Класс C по выручке и спрос Z — повод для дополнительной оценки (роль в чеке, сезонность, отзывы), а не для вывода товара. Важность — низкая.</li>
      <li><b>R5 · ${D.rule_titles.R5}.</b> Выручка выросла, а валовая прибыль упала более чем на 3% к предыдущему периоду той же длины.</li></ul>
    <p class="hint">Правила говорят, что проверить, и не утверждают причину. Ни одно не предлагает вывести товар только по ABC/XYZ.</p>`;
  $('#m-limits').innerHTML = `<h3 style="margin-top:0">Ограничения модели</h3>
    <ul><li>Данные синтетические, сгенерированы для учебного проекта; модель выпуска упрощена, доля списаний свежей продукции выше типичной.</li>
      <li>Маржа валовая: аренда, персонал и логистика не учитываются.</li>
      <li>Товарные показатели, ABC и задачи — по всей сети: в демо-версии продажи по товарам не разбиты по точкам.</li>
      <li>XYZ, задачи и показатели запасов по товарам — за последние 28 дней и не меняются фильтром периода.</li>
      <li>Демо-версия статичная: не выполняет серверных операций; пороги ABC/XYZ и правил настраиваются в полной версии.</li></ul>`;
  $('#sql-list').innerHTML = D.sql.map(q => `<article class="card report" data-n="${q.n}">
    <h3>${esc(q.human.title)}</h3><p class="q">${esc(q.human.question)}</p>
    ${reportHighlights(q)}
    <div class="acts"><button class="btn" data-full="${q.n}" aria-expanded="false">Полная таблица · ${F.int(q.rows.length)} строк</button></div>
    <div class="full" id="sql-t-${q.n}" hidden></div>
    <details class="more"><summary>Как считается</summary>
      <div class="method-doc">${q.method.filter(([l]) => !TECH.includes(l)).map(([l, t]) => `<b>${l}:</b> ${esc(t)}`).join('\n')}${q.note ? '\n<b>Примечание:</b> ' + esc(q.note) : ''}</div>
      <details class="more"><summary>Технические детали: источники данных и исходный SQL</summary>
        <div class="method-doc">${q.method.filter(([l]) => TECH.includes(l)).map(([l, t]) => `<b>${l}:</b> ${esc(t)}`).join('\n')}</div>
        <pre>${esc(q.text)}</pre></details></details></article>`).join('');
  $$('#sql-list [data-full]').forEach(b => b.onclick = () => {
    const q = D.sql.find(x => x.n === +b.dataset.full), box = document.getElementById('sql-t-' + q.n);
    if (!box.dataset.done) {
      box.dataset.done = 1;
      new Table(box, {cols: q.cols.map((c, i) => ({k: i, c, label: COL_RU[c] || c, help: `Колонка в SQL: ${c}`, t: c === 'is_fresh' ? 'text' : colType(c, q.num[i])})).filter(x => !x.c.endsWith('_id')),
        rows: q.rows.map(r => r.map((v, i) => q.cols[i] === 'is_fresh' ? (v ? 'да' : 'нет') : v)), page: 10, csv: `report_${String(q.n).padStart(2, '0')}`}).render();
    }
    box.hidden = !box.hidden; b.setAttribute('aria-expanded', !box.hidden);
    b.textContent = box.hidden ? `Полная таблица · ${F.int(q.rows.length)} строк` : 'Скрыть таблицу';
  });
  new Table('t-dq', {cols: [{k: 0, label: 'Проверка', t: 'html'}, {k: 1, label: 'Уровень', t: 'html'}, {k: 2, label: 'Строк', t: 'int'}],
    rows: D.dq.map(([c, sev, n]) => [`${DQ[c] || esc(c)} <span class="hint">${c}</span>`,
      sev === 'CRIT' ? '<span class="pill p-bad">Исключено из расчёта</span>' : '<span class="pill p-vio">Информация</span>', n]), page: 10}).render();
}

/* ---------- Запуск ---------- */
shell();
buildFilters();
initSales(); initAssortment(); initProfit(); initStock(); initRecs(); initReports();
$('#foot').innerHTML = `${esc(D.meta.note)} Статичная демо-версия: данные выгружены из базы проекта, собрано ${D.meta.built}.
  ABC за выбранный период пересчитывается в браузере по тому же правилу, что в Python. Настройка порогов — в полной версии (запуск через Docker, см. README).<br>Канаева Любовь · учебный проект бизнес-аналитика · <a href="https://github.com/lubancho/assortment-writeoff-analytics" target="_blank" rel="noopener">Код и документация на GitHub →</a>`;
function renderAll() { syncFilters(); renderOverview(); renderSales(); renderAssortment(); renderProfit(); renderStock(); renderRecs(); if (Route.v === 'store') renderStore(); }
State.on(renderAll);
// Старые адреса ведут на экраны новой структуры.
const ALIAS = {recs: 'tasks', problems: 'tasks', stock: 'writeoffs', profit: 'margin', assortment: 'assort', analytics: 'sales'};
function fromHash() {
  const [k, a] = (location.hash || '').slice(1).split('/');
  const v = ALIAS[k] || k;
  if (v === 'store' && STORES[+a]) return go('store', {si: +a});
  go(document.getElementById('v-' + v) && v !== 'store' ? v : 'overview');
}
window.addEventListener('hashchange', fromHash);
bindGo();
renderAll();
fromHash();
