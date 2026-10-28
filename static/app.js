/* CalcWise - front end. Sends the form to the Python API, then draws the answer, chart and table. */
(() => {
  'use strict';
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const csrf = $('meta[name=csrf-token]').content;

  // ------------------------------------------------------------------ currency
  const LOCALES = JSON.parse(document.getElementById('currency')?.dataset.locales || '{}');
  const store = {
    get(k, d) { try { return localStorage.getItem(k) || d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
  };
  let currency = store.get('cw_currency', 'RWF');
  if (!LOCALES[currency]) currency = 'RWF';
  // shillings, francs etc. have no cents: use the currency's own number of decimals
  const decimals = () => { try { return new Intl.NumberFormat('en', { style: 'currency', currency }).resolvedOptions().maximumFractionDigits; } catch (e) { return 2; } };
  const fmtMoney = (v, digits = 2) => {
    if (v === null || v === undefined || isNaN(v)) return '—';
    digits = Math.min(digits, decimals());
    try {
      return new Intl.NumberFormat(LOCALES[currency] || 'en', {
        style: 'currency', currency, maximumFractionDigits: digits, minimumFractionDigits: digits,
      }).format(v);
    } catch (e) {                                   // e.g. USDT is not an ISO code
      return new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(v) + ' ' + currency;
    }
  };
  const fmtShort = v => {
    const a = Math.abs(v);
    const n = a >= 1e9 ? (v / 1e9).toFixed(1) + 'B' : a >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : a >= 1e3 ? (v / 1e3).toFixed(0) + 'K' : Math.round(v);
    return symbol() + n;
  };
  const symbol = () => {
    try {
      return (0).toLocaleString(LOCALES[currency] || 'en', { style: 'currency', currency, currencyDisplay: 'narrowSymbol', maximumFractionDigits: 0 })
        .replace(/[\d\s.,\u00a0]/g, '') || currency;
    } catch (e) { return currency; }
  };
  // inputs always use ',' for thousands and '.' for decimals, so typing is never ambiguous
  const fmtNum = v => new Intl.NumberFormat(currency === 'INR' ? 'en-IN' : 'en-US', { maximumFractionDigits: 2 }).format(v);
  const fmtDate = s => s ? new Date(s + 'T00:00').toLocaleDateString('en-GB', { month: 'short', year: 'numeric' }) : '—';

  const curSelect = $('#currency');
  curSelect.value = currency;
  curSelect.addEventListener('change', () => {
    currency = curSelect.value;
    store.set('cw_currency', currency);
    applyCurrency();
    if (window.lastResult) render(window.lastResult);
  });
  function applyCurrency() {
    $$('.cur-symbol').forEach(s => s.textContent = symbol());
    $$('.saved-item').forEach(card => {
      $$('.money', card).forEach(b => b.textContent = fmtMoney(+b.dataset.value, 0));
      $$('.pct', card).forEach(b => b.textContent = (+b.dataset.value).toFixed(2) + ' %');
    });
    $$('.money-input').forEach(i => { if (document.activeElement !== i) prettify(i); });
  }

  // ------------------------------------------------------------------ small UI helpers
  $('#menuBtn')?.addEventListener('click', () => $('#nav').classList.toggle('open'));
  const toast = msg => {
    const t = $('#toast'); if (!t) return;
    t.textContent = msg; t.classList.add('show');
    clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 2600);
  };
  const raw = v => String(v).replace(/[^\d.\-]/g, '');
  function prettify(input) {
    const v = raw(input.value);
    if (v !== '' && !isNaN(v)) input.value = fmtNum(+v);
  }

  applyCurrency();
  const form = $('#calcForm');
  if (!form) return;                        // pages without a calculator stop here

  const kind = form.dataset.kind;
  const defaults = Object.fromEntries(new FormData(form));

  $$('.money-input').forEach(i => {
    i.addEventListener('focus', () => { i.value = raw(i.value); });
    i.addEventListener('blur', () => prettify(i));
  });
  $$('.range').forEach(r => {
    const input = document.getElementById(r.dataset.for);
    r.addEventListener('input', () => { input.value = r.value; schedule(); });
    input.addEventListener('input', () => { r.value = input.value; });
  });
  $$('.presets button').forEach(b => b.addEventListener('click', () => {
    document.getElementById(b.dataset.set).value = b.dataset.value; schedule();
  }));
  $$('.unit-toggle').forEach(t => {
    const hidden = form.elements[t.dataset.unit];
    const set = v => { hidden.value = v; $$('button', t).forEach(b => b.classList.toggle('on', b.dataset.v === v)); };
    set(hidden.value || 'years');
    $$('button', t).forEach(b => b.addEventListener('click', () => {
      const input = $('input', t.parentElement);
      if (hidden.value !== b.dataset.v) {           // convert the number so the meaning stays the same
        input.value = b.dataset.v === 'months' ? input.value * 12 : Math.max(1, Math.round(input.value / 12));
      }
      set(b.dataset.v); schedule();
    }));
  });
  function conditions() {
    $$('[data-show-if]').forEach(f => {
      const [name, val] = f.dataset.showIf.split('=');
      f.hidden = (form.elements[name].value !== val);
    });
  }

  const readForm = () => {
    const data = {};
    for (const [k, v] of new FormData(form)) data[k] = form.elements[k]?.classList?.contains('money-input') ? raw(v) : v;
    return data;
  };

  // ------------------------------------------------------------------ talk to the API
  let timer, seq = 0;
  const schedule = () => { clearTimeout(timer); timer = setTimeout(calc, 250); };
  form.addEventListener('input', schedule);
  form.addEventListener('change', () => { conditions(); schedule(); });
  form.addEventListener('submit', e => { e.preventDefault(); calc(); });
  $('#resetBtn').addEventListener('click', () => {
    for (const [k, v] of Object.entries(defaults)) {
      const el = form.elements[k];
      if (el instanceof RadioNodeList) el.value = v; else if (el) el.value = v;
    }
    $$('.range').forEach(r => r.value = document.getElementById(r.dataset.for).value);
    $$('.unit-toggle button').forEach(b => b.classList.toggle('on', b.dataset.v === 'years'));
    $$('.money-input').forEach(prettify); conditions(); calc();
  });

  async function calc() {
    const my = ++seq;
    $$('.field').forEach(f => f.classList.remove('bad'));
    let r;
    try {
      r = await fetch(`/api/calc/${kind}`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify(readForm()) });
    } catch (e) { toast('No connection to the server.'); return; }
    if (my !== seq) return;                         // an older answer came late - ignore it
    const data = await r.json();
    if (!r.ok) {
      for (const [field, msg] of Object.entries(data.errors || {})) {
        const f = $(`.field[data-field="${field}"]`) || $(`.field[data-field="term"]`);
        if (f) { f.classList.add('bad'); $('.err', f).textContent = msg; }
      }
      if (data.error) toast(data.error);
      $('#results').classList.add('stale');
      return;
    }
    $('#results').classList.remove('stale');
    window.lastResult = data;
    render(data);
  }

  // ------------------------------------------------------------------ what each calculator shows
  // interest is orange, except on the loan page where orange is already the page colour
  const C1 = 'var(--accent)', C2 = kind === 'loan' ? '#6366f1' : '#f59e0b', C3 = '#94a3b8', C4 = '#0f172a';
  const CONFIG = {
    investment: {
      big: 'final_value', label: 'Final value',
      kpis: s => [
        ['Total deposited', fmtMoney(s.total_deposited)], ['Interest earned', fmtMoney(s.total_interest), 'good'],
        ['Worth in today\'s money', fmtMoney(s.real_value), '', 'After inflation'],
        ['Effective yearly rate', s.effective_rate + ' %'], ['Money multiplied by', '×' + s.growth_multiple],
        s.other_type ? [`With ${s.other_type.type} interest`, fmtMoney(s.other_type.final_value), '',
          (s.final_value - s.other_type.final_value >= 0 ? '+' : '') + fmtMoney(s.final_value - s.other_type.final_value) + ' difference'] : null,
      ],
      chart: d => ({
        title: 'Growth year by year', labels: d.schedule.map(r => 'Y' + r.year),
        series: [{ name: 'Deposits', color: C1, values: d.schedule.map(r => r.deposited) },
                 { name: 'Interest', color: C2, values: d.schedule.map(r => r.interest) }],
        line: { name: 'Value in today\'s money', color: C4, values: d.schedule.map(r => r.real_value) },
      }),
      table: d => ({ title: 'Year-by-year growth', cols: [['year', 'Year'], ['deposited', 'Deposited', 'm'], ['interest', 'Interest', 'm'], ['balance', 'Balance', 'm'], ['real_value', "Today's money", 'm']], rows: d.schedule }),
    },
    bond: {
      big: 'monthly_payment', label: 'Monthly repayment',
      kpis: s => [
        ['Loan amount', fmtMoney(s.loan_amount), '', s.deposit_percent + ' % deposit'],
        s.monthly_total !== s.monthly_payment ? ['Total monthly cost', fmtMoney(s.monthly_total), '', 'incl. extra, tax, insurance'] : null,
        ['Total interest', fmtMoney(s.total_interest), 'bad'], ['Total repaid', fmtMoney(s.total_paid)],
        ['Loan paid off', fmtDate(s.payoff_date), '', Math.floor(s.payoff_months / 12) + ' y ' + (s.payoff_months % 12) + ' m'],
        s.months_saved ? ['Saved with extra payments', fmtMoney(s.interest_saved), 'good', s.months_saved + ' months earlier'] : null,
        s.income_ratio !== null ? ['Share of your income', s.income_ratio + ' %', { good: 'good', stretch: 'warn', risky: 'bad' }[s.affordability]] : null,
      ],
      alert: s => s.affordability === 'risky' ? ['bad', `The home costs ${s.income_ratio} % of your income. Above 36 % is risky - try a bigger deposit or a longer period.`]
        : s.affordability === 'stretch' ? ['warn', `The home costs ${s.income_ratio} % of your income - affordable but tight. 28 % or less is comfortable.`]
        : s.affordability === 'good' ? ['good', `Good: the home costs ${s.income_ratio} % of your income (28 % or less is comfortable).`] : null,
      chart: d => ({
        title: 'What you pay each year', labels: d.yearly.map(r => 'Y' + r.year),
        series: [{ name: 'Capital (loan) repaid', color: C1, values: d.yearly.map(r => r.principal) },
                 { name: 'Interest', color: C2, values: d.yearly.map(r => r.interest) }],
        line: { name: 'Loan balance', color: C4, values: d.yearly.map(r => r.balance), ownScale: true },
      }),
      table: d => loanTable(d),
    },
    loan: {
      big: 'monthly_payment', label: 'Monthly EMI',
      kpis: s => [
        ['Total interest', fmtMoney(s.total_interest), 'bad'], ['Processing fee', fmtMoney(s.fee)],
        ['Total you repay', fmtMoney(s.total_paid)], ['Real rate (APR)', s.apr + ' %', 'warn', 'incl. the fee'],
        ['Interest share of repayments', s.interest_share + ' %'],
      ],
      chart: d => ({ title: 'Where your money goes', donut: [
        { name: 'Loan amount', color: C1, value: d.schedule.reduce((a, r) => a + r.principal, 0) },
        { name: 'Interest', color: C2, value: d.summary.total_interest },
        { name: 'Fee', color: C3, value: d.summary.fee }] }),
      table: d => loanTable(d),
    },
    'savings-goal': {
      big: 'monthly_saving', label: 'Save every month',
      kpis: s => [
        ['Per week', fmtMoney(s.weekly_saving)], ['Your total deposits', fmtMoney(s.total_deposits)],
        ['Interest earned', fmtMoney(s.interest_earned), 'good'], ['Goal reached', fmtDate(s.goal_date), '', s.months + ' months'],
      ],
      alert: s => s.already_reached ? ['good', 'Great news: your current savings already reach the goal with interest.'] : null,
      chart: d => ({
        title: 'Your savings over time', labels: d.schedule.map(r => d.summary.months <= 36 ? 'M' + r.month : r.month % 12 ? r.year + 'y' : 'Y' + r.month / 12),
        series: [{ name: 'Deposits', color: C1, values: d.schedule.map(r => r.deposited) },
                 { name: 'Interest', color: C2, values: d.schedule.map(r => Math.max(r.balance - r.deposited, 0)) }],
      }),
      table: d => ({ title: 'Progress', cols: [['month', 'Month'], ['deposited', 'Deposited', 'm'], ['balance', 'Savings', 'm']], rows: d.schedule }),
    },
    retirement: {
      big: 'at_retirement', label: 'Savings at retirement',
      kpis: s => [
        ['Monthly income it can pay', fmtMoney(s.monthly_income), 'good'], ['…in today\'s money', fmtMoney(s.monthly_income_today)],
        s.needed_pot !== null ? ['Savings needed', fmtMoney(s.needed_pot), '', 'for the income you want'] : null,
        s.gap !== null ? (s.gap > 0 ? ['Shortfall', fmtMoney(s.gap), 'bad', `save ${fmtMoney(s.extra_monthly)} more a month`] : ['Surplus', fmtMoney(-s.gap), 'good']) : null,
        ['Years of saving · retired', s.years_saving + ' · ' + s.years_retired],
      ],
      alert: s => s.on_track === null ? null : s.on_track ? ['good', 'You are on track: your savings can pay the income you want for the whole plan.']
        : ['bad', `Not enough: at this income the money runs out at age ${s.money_lasts_until}. Save ${fmtMoney(s.extra_monthly)} more every month, retire later or plan a smaller income.`],
      chart: d => ({
        title: 'Your savings by age', labels: d.schedule.map(r => r.age),
        series: [{ name: 'Saving years', color: C1, values: d.schedule.map(r => r.phase === 'saving' ? r.balance : 0) },
                 { name: 'Retired (spending)', color: C2, values: d.schedule.map(r => r.phase === 'retired' ? r.balance : 0) }],
      }),
      table: d => ({ title: 'Savings at each age', cols: [['age', 'Age'], ['phase', 'Phase'], ['balance', 'Savings at year end', 'm']], rows: d.schedule }),
    },
  };

  let tableMode = 'year';
  function loanTable(d) {
    $('#tableMode').hidden = false;
    return tableMode === 'year'
      ? { title: 'Repayment schedule (yearly)', cols: [['year', 'Year'], ['paid', 'Paid', 'm'], ['principal', 'Capital', 'm'], ['interest', 'Interest', 'm'], ['balance', 'Balance left', 'm']], rows: d.yearly }
      : { title: 'Repayment schedule (monthly)', cols: [['month', '#'], ['date', 'Month', 'd'], ['payment', 'Payment', 'm'], ['principal', 'Capital', 'm'], ['interest', 'Interest', 'm'], ['balance', 'Balance left', 'm']], rows: d.schedule };
  }
  $$('#tableMode button').forEach(b => b.addEventListener('click', () => {
    tableMode = b.dataset.mode;
    $$('#tableMode button').forEach(x => x.classList.toggle('on', x === b));
    render(window.lastResult);
  }));

  // ------------------------------------------------------------------ render
  let currentTable;
  function render(d) {
    const cfg = CONFIG[kind], s = d.summary, inputs = readForm();
    $('#answerLabel').textContent = cfg.label;
    $('#answerBig').textContent = fmtMoney(s[cfg.big]);
    showFx(s[cfg.big]);
    $('#answerText').textContent = d.sentence.replace(/\{(\w+)\}/g, (_, k) =>
      k in s ? (typeof s[k] === 'number' && !/rate|apr|age/.test(k) ? fmtMoney(s[k]) : k === 'apr' ? s[k] + ' %' : s[k])
        : k === 'extra' ? fmtMoney(d.extra) : (inputs[k] ?? ''));
    const kp = cfg.kpis(s).filter(Boolean);
    $('#kpis').innerHTML = kp.map(([label, value, tone = '', note = '']) =>
      `<div class="kpi ${tone}"><small>${label}</small><b>${value}</b>${note ? `<em>${note}</em>` : ''}</div>`).join('');
    const al = cfg.alert ? cfg.alert(s) : null, box = $('#alertBox');
    box.className = 'alert' + (al ? ' ' + al[0] : ' hidden'); box.textContent = al ? al[1] : '';

    const ch = cfg.chart(d);
    $('#chartTitle').textContent = ch.title;
    if (ch.donut) donut($('#chart'), ch.donut); else bars($('#chart'), ch);
    const legendItems = ch.donut || [...ch.series, ...(ch.line ? [{ ...ch.line, isLine: true }] : [])];
    $('#legend').innerHTML = legendItems.map(x => `<span><i class="${x.isLine ? 'ln' : ''}" style="background:${x.color}"></i>${x.name}</span>`).join('');

    currentTable = cfg.table(d);
    $('#tableTitle').textContent = currentTable.title;
    const cell = (v, t) => t === 'm' ? fmtMoney(v) : t === 'd' ? fmtDate(v) : v;
    $('#table').innerHTML = `<thead><tr>${currentTable.cols.map(c => `<th>${c[1]}</th>`).join('')}</tr></thead><tbody>` +
      currentTable.rows.map(r => `<tr>${currentTable.cols.map(c => `<td class="${c[2] === 'm' ? 'num' : ''}">${cell(r[c[0]], c[2])}</td>`).join('')}</tr>`).join('') + '</tbody>';
  }

  // ------------------------------------------------------------------ the answer in a second currency (live rate)
  let fxRates = null, fxLoading = null;
  const fxTo = $('#fxTo');
  if (fxTo) {
    fxTo.value = store.get('cw_fx_to', currency === 'USD' ? 'EUR' : 'USD');
    fxTo.addEventListener('change', () => { store.set('cw_fx_to', fxTo.value); if (window.lastResult) render(window.lastResult); });
  }
  function showFx(value) {
    if (!fxTo) return;
    if (!fxRates) {
      fxLoading = fxLoading || fetch('/api/rates').then(r => r.ok ? r.json() : null).then(d => { fxRates = d; return d; }).catch(() => null);
      fxLoading.then(d => { if (d) showFx(value); });
      return;
    }
    const a = fxRates.rates[currency], b = fxRates.rates[fxTo.value];
    if (!a || !b || fxTo.value === currency) { $('#fxLine').hidden = true; return; }
    const v = value * b / a, saved = currency;
    currency = fxTo.value;                 // format in the second currency
    $('#fxValue').textContent = fmtMoney(v);
    currency = saved;
    $('#fxLine').hidden = false;
  }

  // ------------------------------------------------------------------ SVG charts (no library)
  const NS = 'http://www.w3.org/2000/svg';
  function svgEl(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (parent) parent.appendChild(e);
    return e;
  }
  function niceMax(v) {
    if (v <= 0) return 1;
    const p = 10 ** Math.floor(Math.log10(v)), n = v / p;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
  }
  function bars(box, ch) {
    box.innerHTML = '';
    const W = 720, H = 300, L = 64, R = ch.line?.ownScale ? 64 : 14, T = 14, B = 34;
    const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': ch.title }, box);
    const totals = ch.labels.map((_, i) => ch.series.reduce((a, s) => a + s.values[i], 0));
    const lineMax = ch.line ? Math.max(...ch.line.values) : 0;
    const max = niceMax(Math.max(...totals, ch.line && !ch.line.ownScale ? lineMax : 0));
    const lmax = ch.line?.ownScale ? niceMax(lineMax) : max;
    const y = v => T + (H - T - B) * (1 - v / max), yl = v => T + (H - T - B) * (1 - v / lmax);
    for (let k = 0; k <= 4; k++) {
      const v = max * k / 4;
      svgEl('line', { x1: L, x2: W - R, y1: y(v), y2: y(v), class: 'grid' }, svg);
      svgEl('text', { x: L - 8, y: y(v) + 4, class: 'axis', 'text-anchor': 'end' }, svg).textContent = fmtShort(v);
      if (ch.line?.ownScale) svgEl('text', { x: W - R + 8, y: yl(lmax * k / 4) + 4, class: 'axis' }, svg).textContent = fmtShort(lmax * k / 4);
    }
    const n = ch.labels.length, step = (W - L - R) / n, bw = Math.max(2, Math.min(34, step * 0.66));
    const every = Math.ceil(n / 14);
    ch.labels.forEach((lab, i) => {
      let acc = 0;
      const x = L + step * i + (step - bw) / 2;
      ch.series.forEach(s => {
        const v = s.values[i];
        if (v > 0) {
          const r = svgEl('rect', { x, y: y(acc + v), width: bw, height: Math.max(0, y(acc) - y(acc + v)), rx: Math.min(4, bw / 4), fill: s.color, class: 'bar' }, svg);
          svgEl('title', {}, r).textContent = `${lab} · ${s.name}: ${fmtMoney(v)}`;
        }
        acc += v;
      });
      if (i % every === 0 || i === n - 1) svgEl('text', { x: x + bw / 2, y: H - 12, class: 'axis', 'text-anchor': 'middle' }, svg).textContent = lab;
    });
    if (ch.line) {
      const pts = ch.line.values.map((v, i) => `${L + step * i + step / 2},${yl(v)}`).join(' ');
      svgEl('polyline', { points: pts, fill: 'none', stroke: ch.line.color, 'stroke-width': 2.5, 'stroke-linejoin': 'round', 'stroke-dasharray': '6 4' }, svg);
      ch.line.values.forEach((v, i) => {
        const c = svgEl('circle', { cx: L + step * i + step / 2, cy: yl(v), r: n > 30 ? 0 : 3, fill: ch.line.color }, svg);
        svgEl('title', {}, c).textContent = `${ch.labels[i]} · ${ch.line.name}: ${fmtMoney(v)}`;
      });
    }
  }
  function donut(box, parts) {
    box.innerHTML = '';
    const total = parts.reduce((a, p) => a + p.value, 0) || 1;
    const svg = svgEl('svg', { viewBox: '0 0 720 300', role: 'img' }, box);
    const cx = 190, cy = 150, r = 110, w = 38;
    let a0 = -Math.PI / 2;
    parts.filter(p => p.value > 0).forEach(p => {
      const a1 = a0 + p.value / total * Math.PI * 2 - 0.0001;
      const large = a1 - a0 > Math.PI ? 1 : 0;
      const pt = a => `${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`;
      const path = svgEl('path', { d: `M${pt(a0)} A${r},${r} 0 ${large} 1 ${pt(a1)}`, fill: 'none', stroke: p.color, 'stroke-width': w }, svg);
      svgEl('title', {}, path).textContent = `${p.name}: ${fmtMoney(p.value)}`;
      a0 = a1 + 0.0001;
    });
    svgEl('text', { x: cx, y: cy - 4, class: 'donut-big', 'text-anchor': 'middle' }, svg).textContent = fmtShort(total);
    svgEl('text', { x: cx, y: cy + 20, class: 'axis', 'text-anchor': 'middle' }, svg).textContent = 'total repaid';
    parts.forEach((p, i) => {
      const yy = 80 + i * 62;
      svgEl('rect', { x: 380, y: yy - 14, width: 16, height: 16, rx: 4, fill: p.color }, svg);
      svgEl('text', { x: 406, y: yy, class: 'dl' }, svg).textContent = p.name;
      svgEl('text', { x: 406, y: yy + 24, class: 'dv' }, svg).textContent = `${fmtMoney(p.value)}  ·  ${(p.value / total * 100).toFixed(1)} %`;
    });
  }

  // ------------------------------------------------------------------ CSV, share, save
  $('#csvBtn').addEventListener('click', () => {
    if (!currentTable) return;
    const esc = v => `"${String(v).replace(/"/g, '""')}"`;
    const lines = [currentTable.cols.map(c => esc(c[1] + (c[2] === 'm' ? ` (${currency})` : ''))).join(',')]
      .concat(currentTable.rows.map(r => currentTable.cols.map(c => esc(r[c[0]])).join(',')));
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob(['﻿' + lines.join('\n')], { type: 'text/csv' }));
    a.download = `calcwise_${kind}_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
  });
  $('#shareBtn').addEventListener('click', async () => {
    const url = location.origin + location.pathname + '?' + new URLSearchParams(readForm());
    try { await navigator.clipboard.writeText(url); toast('Share link copied.'); }
    catch (e) { prompt('Copy this link:', url); }
  });
  const dlg = $('#saveDialog'), savedId = form.dataset.savedId;
  $('#saveBtn').addEventListener('click', () => {
    $('#saveName').value = form.dataset.savedName || '';
    $('#saveAsNewWrap').hidden = !savedId;
    dlg.showModal(); $('#saveName').focus();
  });
  dlg.addEventListener('close', async () => {
    if (dlg.returnValue !== 'ok') return;
    const body = { kind, name: $('#saveName').value, inputs: readForm(), currency };
    if (savedId && !$('#saveAsNew').checked) body.id = savedId;
    const r = await fetch('/api/saved', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify(body) });
    const data = await r.json();
    if (!r.ok) { toast(data.error || Object.values(data.errors || {})[0] || 'Could not save.'); return; }
    toast(data.updated ? `Updated “${data.name}”.` : `Saved as “${data.name}”. See My calculations.`);
    if (!data.updated) setTimeout(() => location.href = `${location.pathname}?saved=${data.id}`, 900);
  });

  conditions();
  $$('.money-input').forEach(prettify);
  calc();
})();
