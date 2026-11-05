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
let catChips;
function buildFilters() {
  const per = $('#f-period');
  per.innerHTML = [[7, '7 дней'], [28, '28 дней'], [DAYS.length, `Весь период (${DAYS.length} дн.)`]].map(([v, l]) => `<button data-v="${v}">${l}</button>`).join('');
  $$('button', per).forEach(b => b.onclick = () => State.set({days: +b.dataset.v}));
  const sel = $('#f-store');
  sel.innerHTML = '<option value="">Все точки</option>' + STORES.map(s => `<option value="${s.i}">${esc(s.name)}</option>`).join('');
  sel.onchange = () => State.set({store: sel.value === '' ? null : +sel.value});
  catChips = chipGroup('f-cats', CATS.map(c => ({v: c.i, label: c.name})), {allLabel: 'Все категории', onChange: v => State.set({cat: v})});
}
const view = () => (location.hash || '#overview').slice(1) || 'overview';
function syncFilters() {
  $$('#f-period button').forEach(b => { const on = +b.dataset.v === State.s.days; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on); });
  $('#f-store').value = State.s.store ?? '';
  catChips.set(State.s.cat);
  const act = [];
  if (State.s.store != null) act.push(`<button class="chip af" data-x="store" aria-label="Снять фильтр: ${esc(STORES[State.s.store].name)}">${esc(STORES[State.s.store].name)} <span aria-hidden="true">×</span></button>`);
  if (State.s.cat != null) act.push(`<button class="chip af" data-x="cat" aria-label="Снять фильтр: ${esc(CATS[State.s.cat].name)}">${esc(CATS[State.s.cat].name)} <span aria-hidden="true">×</span></button>`);
  if (act.length) act.push('<button class="link" data-x="all">Сбросить фильтры</button>');
  $('#f-active').innerHTML = act.join('');
  $$('#f-active [data-x]').forEach(b => b.onclick = () => { const x = b.dataset.x; State.set(x === 'all' ? {store: null, cat: null} : {[x]: null}); });
  const v = view();
  $('#filterbar').style.display = v === 'reports' ? 'none' : '';
  $('#f-period').style.display = v === 'recs' ? 'none' : '';
  $('#f-store').style.display = v === 'recs' ? 'none' : '';
}
const where = () => [State.s.store != null ? STORES[State.s.store].name : 'вся сеть', State.s.cat != null ? CATS[State.s.cat].name : 'все категории'].join(' · ');

/* ---------- 1. Главная ---------- */
let tStores;
function initOverview() {
  tStores = new Table('t-stores', {
    cols: [{k: 'name', label: 'Точка', t: 'text'}, {k: 'rev', label: 'Выручка', t: 'rub'}, {k: 'mg', label: 'Маржа', t: 'pct', help: HELP.mg},
      {k: 'dmg', label: 'Маржа к сети', t: 'pp', help: 'Разница маржинальности точки и сети, процентные пункты. Плюс — лучше сети.'},
      {k: 'wo', label: 'Списания', t: 'rub', help: HELP.wo}, {k: 'ws', label: 'Доля списаний', t: 'pct', help: HELP.ws},
      {k: 'dws', label: 'Списания к сети', t: 'pp', help: 'Разница доли списаний точки и сети. Плюс — хуже сети.'}, {k: 'flag', label: 'Оценка', t: 'html', help: 'Сравнение с сетью по марже и доле списаний'}],
    rows: [], page: 15, sort: 'dws', onRow: r => State.set({store: State.s.store === r.si ? null : r.si}), csv: 'stores',
  });
}
function storeRows(rg) {
  const st = {...State.s, store: null};
  const sS = aggSales(rg, (d, s) => s, st), sW = aggWo(rg, (d, s) => s, st), net = totals(rg, st);
  return {net, rows: STORES.map(s => {
    const a = sS.get(s.i); if (!a) return null;
    const m = mg(a), w = sW.get(s.i)?.cost ?? 0, ws = woShare(w, a.cogs);
    const bad = [];
    if (m < net.mg) bad.push('маржа ниже сети');
    if (ws > net.woShare) bad.push('списания выше сети');
    return {si: s.i, name: s.name, rev: a.rev, mg: m, dmg: m - net.mg, wo: w, ws, dws: ws - net.woShare,
      flag: bad.length === 2 ? '<span class="pill p-bad">Хуже по обоим</span>' : bad.length ? `<span class="pill p-warn">${bad[0] === 'маржа ниже сети' ? 'Маржа ниже' : 'Списания выше'}</span>` : '<span class="pill p-ok">Не хуже сети</span>'};
  }).filter(Boolean)};
}
function renderOverview() {
  const rg = range(), pr = prevRange(), cur = totals(rg), prev = totals(pr), n = rg[1] - rg[0] + 1;
  $('#ov-period').textContent = periodText(rg);
  $('#ov-base').textContent = pr ? `изменение — к предыдущим ${n} дн. (${periodText(pr)}); зелёный — лучше для бизнеса` : 'для всего периода нет предыдущего для сравнения';
  const dm = prev ? cur.mg - prev.mg : null;
  $('#ov-summary').innerHTML = `За ${n} дн. (${where()}) выручка <b>${F.rubc(cur.rev)}</b>${prev ? ` (${F.spct(ratio(cur.rev - prev.rev, prev.rev))})` : ''},
    валовая маржинальность <b>${F.pct(cur.mg)}</b>${dm != null ? ` (${F.pp(dm)})` : ''}. В списание ушло <b>${F.rubc(cur.wo)}</b> — ${F.pct(cur.woShare)} себестоимости выпуска.`;
  const dIdx = []; for (let d = rg[0]; d <= rg[1]; d++) dIdx.push(d);
  const daily = aggSales(rg, d => d), wday = aggWo(rg, d => d);
  const kpis = [
    {k: 'rev', l: 'Выручка', h: HELP.rev, v: F.rubc(cur.rev), d: deltaPill(cur.rev, prev?.rev), sp: dIdx.map(d => daily.get(d)?.rev ?? 0)},
    {k: 'gp', l: 'Валовая прибыль', h: HELP.gp, v: F.rubc(cur.gp), d: deltaPill(cur.gp, prev?.gp), sp: dIdx.map(d => gp(daily.get(d)) ?? 0)},
    {k: 'mg', l: 'Маржинальность', h: HELP.mg, dot: 'ok', v: F.pct(cur.mg), d: prev ? deltaPill(cur.mg, prev.mg, {kind: 'pp'}) : '', col: '--c5',
      sp: dIdx.map(d => (mg(daily.get(d)) ?? 0) * 100), act: () => Nav.go('profit')},
    {k: 'wo', l: 'Списания', h: HELP.wo, dot: 'bad', v: F.rubc(cur.wo), d: deltaPill(cur.wo, prev?.wo, {invert: true}), col: '--c3',
      sp: dIdx.map(d => wday.get(d)?.cost ?? 0), act: () => Nav.go('stock')},
    {k: 'ws', l: 'Доля списаний', h: HELP.ws, dot: 'warn', v: F.pct(cur.woShare), d: prev ? deltaPill(cur.woShare, prev.woShare, {kind: 'pp', invert: true}) : '',
      note: 'от себестоимости выпуска', act: () => Nav.go('stock')},
    {k: 'ch', l: 'Средний чек', h: HELP.check, v: cur.check ? F.rub(cur.check) : 'не считается',
      d: deltaPill(cur.check, prev?.check), note: cur.orders == null ? 'при фильтре категории' : `${F.int(cur.orders)} чеков`},
  ];
  $('#kpis').innerHTML = kpis.map(k => `<div class="card kpi ${k.act ? 'click' : ''}" data-k="${k.k}">
    <div class="eyebrow"><span class="dot ${k.dot || ''}"></span>${k.l}${tip(k.h)}</div><div class="kpi-value">${k.v}</div>
    <div class="kpi-foot">${k.d || ''}<span>${k.note || (pr ? 'к предыдущему периоду' : '')}</span></div>
    ${k.sp ? `<div class="spark" id="sp-${k.k}" aria-hidden="true"></div>` : k.act ? '<span class="go">Подробнее →</span>' : ''}</div>`).join('');
  kpis.forEach(k => {
    if (k.sp) spark('sp-' + k.k, k.sp, css(k.col || '--c1'));
    if (k.act) clickable($(`[data-k="${k.k}"]`, $('#kpis')), e => { if (!e.target.closest('.tip')) k.act(); });
  });

  // Что требует внимания — только факты, порядок: задачи высокой важности → списания → маржа
  const items = [];
  const scopeRecs = RECS.filter(r => State.s.cat == null || r.c === State.s.cat);
  const high = scopeRecs.filter(r => r.severity === 'Высокая');
  if (high.length) {
    const byRule = {}; high.forEach(r => byRule[r.rule] = (byRule[r.rule] || 0) + 1);
    items.push({lvl: 'bad', l: 'Высокая важность', t: `${high.length} задач высокой важности`,
      why: Object.entries(byRule).map(([k, v]) => `${D.rule_titles[k].toLowerCase()} — ${v}`).join('; ') + '. Задачи — по сети за последние 28 дней.',
      num: F.int(high.length), sub: 'задач', go: () => { rcSev = 'Высокая'; rcRule = null; Nav.go('recs'); renderRecs(); }});
  }
  if (prev && cur.wo > prev.wo) items.push({lvl: 'warn', l: 'Требует внимания', t: `Списания выросли на ${F.spct(ratio(cur.wo - prev.wo, prev.wo)).replace('+', '')}`,
    why: `${F.rubc(cur.wo)} против ${F.rubc(prev.wo)} за предыдущие ${n} дн. Доля списаний ${F.pct(cur.woShare)} (было ${F.pct(prev.woShare)}).`,
    num: '+' + F.rubc(cur.wo - prev.wo), sub: 'к прошлому периоду', go: () => Nav.go('stock')});
  const {net, rows} = storeRows(rg);
  if (State.s.store == null && rows.length) {
    const w = rows.slice().sort((a, b) => b.dws - a.dws)[0];
    if (w.dws > 0) items.push({lvl: 'warn', l: 'Требует внимания', t: `Самая высокая доля списаний — ${w.name}`,
      why: `${F.pct(w.ws)} при ${F.pct(net.woShare)} по сети; списано ${F.rubc(w.wo)}. Нажмите, чтобы посмотреть только эту точку.`,
      num: F.pp(w.dws), sub: 'к сети', go: () => { State.set({store: w.si}); Nav.go('stock'); }});
    const m = rows.slice().sort((a, b) => a.dmg - b.dmg)[0];
    if (m.dmg < 0) items.push({lvl: 'warn', l: 'Требует внимания', t: `Самая низкая маржа — ${m.name}`,
      why: `${F.pct(m.mg)} при ${F.pct(net.mg)} по сети. Возможные факторы — структура продаж, скидки, себестоимость; проверить на экране «Прибыльность».`,
      num: F.pp(m.dmg), sub: 'к сети', go: () => { State.set({store: m.si}); Nav.go('profit'); }});
  }
  if (State.s.cat == null) {
    const cS = aggSales(rg, (d, s, c) => c), cW = aggWo(rg, (d, s, c) => c);
    const c = CATS.map(x => ({x, ws: cS.get(x.i) ? woShare(cW.get(x.i)?.cost ?? 0, cS.get(x.i).cogs) : null, wo: cW.get(x.i)?.cost ?? 0}))
      .filter(x => x.ws != null).sort((a, b) => b.wo - a.wo)[0];
    if (c) items.push({lvl: 'info', l: 'Информация', t: `Больше всего денег в списание — категория «${c.x.name}»`,
      why: `${F.rubc(c.wo)} (${F.pct(c.ws)} себестоимости выпуска). Для свежей продукции высокая доля списаний ожидаема — сравнивайте товары внутри категории.`,
      num: F.rubc(c.wo), sub: 'списано', go: () => { State.set({cat: c.x.i}); Nav.go('stock'); }});
  }
  if (dm != null && dm < 0) items.push({lvl: 'info', l: 'Информация', t: `Маржинальность снизилась на ${F.num1(-dm * 100)} п. п.`,
    why: `${F.pct(cur.mg)} против ${F.pct(prev.mg)}. Товары, у которых прибыль падает при росте выручки, — в задачах (правило R5).`,
    num: F.pct(cur.mg), sub: `было ${F.pct(prev.mg)}`, go: () => { rcSev = null; rcRule = 'R5'; Nav.go('recs'); renderRecs(); }});
  const LV = {bad: '--bad', warn: '--warn', info: '--vio'}, LP = {bad: 'p-bad', warn: 'p-warn', info: 'p-vio'};
  $('#attn').innerHTML = items.length ? items.map((x, i) => `<button class="attn-item" data-i="${i}" style="--ac:var(${LV[x.lvl]})">
      <span class="sevc"><span class="pill ${LP[x.lvl]}">${x.l}</span></span>
      <span><span class="t">${x.t}</span><span class="why" style="display:block">${x.why}</span></span>
      <span class="num">${x.num}<small>${x.sub}</small></span><span class="arr" aria-hidden="true">→</span></button>`).join('')
    : '<div class="attn-ok">Существенных отклонений не найдено.</div>';
  $$('#attn .attn-item').forEach(b => b.onclick = () => items[+b.dataset.i].go());

  $('#trend-hint').textContent = periodText(rg);
  const revD = dIdx.map(d => daily.get(d)?.rev ?? 0), woD = dIdx.map(d => wday.get(d)?.cost ?? 0);
  Charts.set('c-trend', () => ({
    legend: {top: 0, left: 0}, grid: {left: 8, right: 8, top: 40, bottom: 4, containLabel: true}, tooltip: {trigger: 'axis'},
    xAxis: Charts.axis('category', {data: dIdx.map(d => F.dshort(DAYS[d])), splitLine: {show: false}}),
    yAxis: [Charts.axis('value', {axisLabel: {formatter: v => NF0.format(v / 1000) + ' тыс'}}),
      Charts.axis('value', {splitLine: {show: false}, axisLabel: {formatter: v => NF0.format(v / 1000) + ' тыс'}})],
    series: [
      {name: 'Выручка (левая ось)', type: 'bar', data: revD, barMaxWidth: 16, tooltip: {valueFormatter: F.rub}, itemStyle: {borderRadius: [5, 5, 0, 0], color: css('--c2')}},
      {name: 'Списания (правая ось)', type: 'line', yAxisIndex: 1, data: woD, smooth: true, symbolSize: 5, lineStyle: {width: 2.5, color: css('--c3')},
        itemStyle: {color: css('--c3')}, tooltip: {valueFormatter: F.rub}},
    ],
  }));
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
  tStores.setRows(rows);
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
  tabs('as-tabs');
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
  $('#as-eyebrow').textContent = `${periodText(rg)} · ${State.s.cat != null ? CATS[State.s.cat].name : 'все категории'}`;
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
      <b>Доказательство:</b> ${esc(r.value)}.<br><b>Проверить:</b> ${esc(r.action)}.<br><span class="hint"><b>Ограничения:</b> ${esc(r.limitations)}.</span></div>`).join('')
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
    cols: [{k: 'name', label: 'Товар', t: 'text', w: 160}, {k: 'cat', label: 'Категория', t: 'text'}, {k: 'rev', label: 'Выручка', t: 'rub'},
      {k: 'mgv', label: 'Маржа', t: 'pct'}, {k: 'base', label: 'Сеть', t: 'pct'}, {k: 'diff', label: 'Отклонение', t: 'pp'},
      {k: 'prob', label: 'Проблема', t: 'html'}, {k: 'factors', label: 'Возможные факторы', t: 'text', w: 220}, {k: 'next', label: 'Что проверить', t: 'text', w: 220}],
    rows: [], page: 12, search: ['name', 'sku'], onRow: r => productCard(r.p), csv: 'low_margin', sort: 'diff', dir: 1,
  });
}
function renderProfit() {
  const rg = range(), ps = prodSales(rg);
  const netAll = mg(aggSales(rg, null, {store: null, cat: null}).get(0));
  $('#pf-eyebrow').textContent = `${periodText(rg)} · ${where()}`;
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
      factors: rec ? rec.possible_cause : 'Рост себестоимости, скидки или промо, цена ниже рынка — не установлено',
      next: rec ? rec.action : 'Проверить себестоимость (техкарта, закупка), действующую цену и скидки'};
  }).filter(r => r.prob));
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
    cols: [{k: 'name', label: 'Товар', t: 'text', w: 170}, {k: 'cat', label: 'Категория', t: 'text'}, {k: 'write_off_cost', label: 'Списано, ₽', t: 'rub', help: HELP.wo},
      {k: 'write_off_share', label: 'Доля списаний', t: 'pct', help: HELP.ws}, {k: 'med', label: 'Медиана категории', t: 'pct', help: 'Типичная доля списаний товаров той же категории — база сравнения'},
      {k: 'dev', label: 'Отклонение', t: 'pp'}, {k: 'oos_share', label: 'Нет в продаже', t: 'pct', help: HELP.oos},
      {k: 'kind_h', label: 'Оценка', t: 'html'}],
    rows: [], page: 10, search: ['name'], onRow: r => productCard(r.p), csv: 'write_offs', sort: 'write_off_cost',
  });
  const med = {};
  CATS.forEach(c => { med[c.i] = median(PRODS.filter(p => p.c === c.i && p.is_active).map(p => p.write_off_share)); });
  tWo.base = PRODS.filter(p => p.is_active).map(p => {
    const kind = p.rules.has('R3') ? 'Высокие списания (R3)' : p.rules.has('R2') ? 'Часто нет в продаже (R2)' : 'Без отклонений';
    return {...p, med: med[p.c], dev: p.write_off_share != null && med[p.c] != null ? p.write_off_share - med[p.c] : null, kind,
      kind_h: `<span class="pill ${kind.startsWith('Высокие') ? 'p-bad' : kind.startsWith('Часто') ? 'p-warn' : 'p-ok'}">${kind}</span>`};
  });
  tWost = new Table('t-wost', {
    cols: [{k: 'name', label: 'Точка', t: 'text'}, {k: 'wo', label: 'Списано, ₽', t: 'rub'}, {k: 'ws', label: 'Доля', t: 'pct', help: HELP.ws},
      {k: 'dws', label: 'К сети', t: 'pp', help: 'Разница доли списаний точки и сети. Плюс — хуже сети.'}],
    rows: [], page: 8, sort: 'dws', onRow: r => State.set({store: State.s.store === r.si ? null : r.si}),
  });
}
function renderStock() {
  const rg = range(), cur = totals(rg), prev = totals(prevRange());
  $('#st-eyebrow').textContent = `${periodText(rg)} · ${where()}${woReason != null ? ' · причина: ' + REASONS[woReason] : ''}`;
  const byR = aggWo(rg, (d, s, c, r) => r), top = [...byR.entries()].sort((a, b) => b[1].cost - a[1].cost)[0];
  $('#st-summary').innerHTML = `За ${rg[1] - rg[0] + 1} дн. списано продукции на <b>${F.rubc(cur.wo)}</b> — <b>${F.pct(cur.woShare)}</b> себестоимости выпуска.
    ${top ? `Главная причина — «${REASONS[top[0]].toLowerCase()}» (${F.pct(ratio(top[1].cost, cur.wo))} стоимости).` : ''} Нажмите на причину, точку или категорию — графики и таблицы отфильтруются.`;
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
  $('#cnt-recs').textContent = RECS.filter(r => r.severity === 'Высокая').length;
  $('#rc-d1').textContent = F.date(D.meta.d1);
}
function renderRecs() {
  $('#rc-eyebrow').textContent = `По сети · последние 28 дней · ${State.s.cat != null ? CATS[State.s.cat].name : 'все категории'}`;
  const scope = RECS.filter(r => State.s.cat == null || r.c === State.s.cat);
  const SD = {'Высокая': 'проверить в первую очередь', 'Средняя': 'проверить в плановом порядке', 'Низкая': 'к сведению'};
  $('#rc-kpis').innerHTML = SEVS.map(s => `<div class="grp ${rcSev === s ? 'on' : ''}" data-s="${s}" style="--ac:var(${SEV[s].ac})" aria-pressed="${rcSev === s}">
    <div class="gt"><span class="pill ${SEV[s].p}">Важность: ${s.toLowerCase()}</span></div><div class="gv">${scope.filter(r => r.severity === s).length} <small>задач</small></div>
    <div class="gd">${SD[s]}</div></div>`).join('');
  $$('#rc-kpis [data-s]').forEach(c => clickable(c, () => { rcSev = rcSev === c.dataset.s ? null : c.dataset.s; rcShown = 15; renderRecs(); }));
  const s2 = scope.filter(r => !rcSev || r.severity === rcSev);
  ruleChips.update(Object.keys(D.rule_titles).map(k => ({v: k, label: `${k} · ${D.rule_titles[k]}`, n: s2.filter(r => r.rule === k).length})));
  ruleChips.set(rcRule);
  const list = s2.filter(r => !rcRule || r.rule === rcRule).sort((a, b) => SEVS.indexOf(a.severity) - SEVS.indexOf(b.severity));
  $('#rc-list').innerHTML = list.slice(0, rcShown).map((r, i) => `<article class="task" style="--ac:var(${SEV[r.severity].ac})">
    <div class="task-head"><span class="pill ${SEV[r.severity].p}">${r.severity}</span><span class="obj">${esc(r.product_name)}</span>
      <span class="hint">${esc(r.category_name)} · ${esc(r.rule)}</span><span class="sp"></span><button class="btn" data-i="${i}">Карточка товара →</button></div>
    <div class="task-grid">
      <div><b>Проблема</b>${esc(r.problem)}</div>
      <div><b>Доказательство</b>${esc(r.value)}<br><span class="hint">${esc(r.basis)}</span></div>
      <div><b>Что проверить</b>${esc(r.action)}<br><span class="hint">Возможная причина: ${esc(r.possible_cause)}</span></div>
      <div><b>Ограничения</b>${esc(r.limitations)}</div>
    </div></article>`).join('') || '<div class="empty">Нет задач для выбранных фильтров</div>';
  $$('#rc-list .task .btn').forEach(b => b.onclick = () => productCard(list[+b.dataset.i].p));
  $('#rc-more').innerHTML = `<span>Показано ${Math.min(rcShown, list.length)} из ${list.length}</span>` + (list.length > rcShown ? '<button class="btn" id="rc-btn">Показать ещё</button>' : '');
  if ($('#rc-btn')) $('#rc-btn').onclick = () => { rcShown += 15; renderRecs(); };
}

/* ---------- 6. Методика и данные ---------- */
const COL_RU = {store_id: 'ID точки', store_name: 'Точка', city: 'Город', revenue: 'Выручка, ₽', orders: 'Чеков', avg_check: 'Средний чек, ₽', revenue_share: 'Доля выручки',
  category_id: 'ID категории', category_name: 'Категория', net_qty: 'Продано, шт', product_id: 'ID товара', sku: 'Артикул', product_name: 'Товар',
  revenue_costed: 'Выручка с себестоимостью, ₽', cogs: 'Себестоимость, ₽', gross_profit: 'Валовая прибыль, ₽', gross_margin: 'Маржинальность', margin_rank: 'Место',
  diff_from_network: 'Отклонение от сети', sale_date: 'Дата', revenue_ma7: 'Среднее за 7 дней, ₽', available_days: 'Дней в продаже', days: 'Дней', interpretation: 'Вывод',
  is_fresh: 'Свежая продукция', write_off_qty: 'Списано, шт', write_off_cost: 'Списано, ₽', write_off_share: 'Доля списаний', value: 'Вклад, ₽', share: 'Доля',
  cum_before: 'Накоплено до товара', cum_share: 'Накопленная доля', abc_class: 'Класс ABC', rev_cur: 'Выручка сейчас, ₽', rev_prev: 'Выручка ранее, ₽',
  rev_change: 'Изм. выручки, ₽', rev_change_pct: 'Изм. выручки', gp_cur: 'Прибыль сейчас, ₽', gp_prev: 'Прибыль ранее, ₽', gp_change: 'Изм. прибыли, ₽',
  gp_change_pct: 'Изм. прибыли', network_rank: 'Место в сети', category_rank: 'Место в категории', category_share: 'Доля в категории'};
const colType = (c, isNum) => /share|margin|pct|cum_/.test(c) && c !== 'margin_rank' ? 'pct' : /revenue|cogs|profit|cost|check|value|rev_|gp_/.test(c) && isNum && !/rank/.test(c) ? 'rub2' : isNum ? 'num' : 'text';
function initReports() {
  tabs('rp-tabs');
  $('#rp-eyebrow').textContent = `Для аналитика · SQL-отчёты за ${F.date(D.meta.d0)} — ${F.date(D.meta.d1)}`;
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
  $('#sql-list').innerHTML = D.sql.map(q => `<details class="card sql" data-n="${q.n}"><summary><span class="num-ic">${q.n}</span>
    <span><b>${esc(q.title)}</b><br><span class="hint">строк: ${F.int(q.rows.length)}${q.note ? ' · ' + esc(q.note) : ''}</span></span><span class="chev" aria-hidden="true">›</span></summary>
    <div class="mt" id="sql-t-${q.n}"></div><details class="mt"><summary class="link">Документация и текст запроса</summary><pre>${esc(q.header)}</pre><pre>${esc(q.text)}</pre></details></details>`).join('');
  $$('#sql-list details.sql').forEach(el => el.addEventListener('toggle', () => {
    if (!el.open || el.dataset.done) return;
    el.dataset.done = 1;
    const q = D.sql.find(x => x.n === +el.dataset.n);
    new Table('sql-t-' + q.n, {cols: q.cols.map((c, i) => ({k: i, label: COL_RU[c] || c, help: `Колонка SQL: ${c}`, t: c === 'is_fresh' ? 'text' : colType(c, q.num[i])})),
      rows: q.rows.map(r => r.map((v, i) => q.cols[i] === 'is_fresh' ? (v ? 'да' : 'нет') : v)), page: 10, csv: `sql_${String(q.n).padStart(2, '0')}`}).render();
  }));
  new Table('t-dq', {cols: [{k: 0, label: 'Проверка', t: 'html'}, {k: 1, label: 'Уровень', t: 'html'}, {k: 2, label: 'Строк', t: 'int'}],
    rows: D.dq.map(([c, sev, n]) => [`${DQ[c] || esc(c)} <span class="hint">${c}</span>`,
      sev === 'CRIT' ? '<span class="pill p-bad">Исключено из расчёта</span>' : '<span class="pill p-vio">Информация</span>', n]), page: 10}).render();
}

/* ---------- Запуск ---------- */
shell();
buildFilters();
initOverview(); initAssortment(); initProfit(); initStock(); initRecs(); initReports();
$('#foot').innerHTML = `${esc(D.meta.note)} Статичная демо-версия: данные выгружены из базы проекта, собрано ${D.meta.built}.
  ABC за выбранный период пересчитывается в браузере по тому же правилу, что в Python. Настройка порогов — в полной версии (запуск через Docker, см. README).`;
function renderAll() { syncFilters(); renderOverview(); renderAssortment(); renderProfit(); renderStock(); renderRecs(); }
State.on(renderAll);
const navGo = Nav.go.bind(Nav);
Nav.go = (k, push) => { navGo(k, push); syncFilters(); };
Nav.init();
renderAll();
