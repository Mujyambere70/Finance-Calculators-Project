/* CalcWise currency converter: live rates from /api/rates (refreshed automatically), history chart,
   favourites and a table of every currency. */
(() => {
  'use strict';
  const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
  const INFO = JSON.parse($('#currencyData').textContent);
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };
  const POLL_MS = 5 * 60 * 1000;
  let data = null, histDays = 30, histReq = 0;
  const amountEl = $('#amount'), fromEl = $('#from'), toEl = $('#to');

  // restore the last pair, or use ?from=&to=&amount= from a link
  const q = new URLSearchParams(location.search);
  const saved = store.get('fx_pair', null);
  fromEl.value = q.get('from') || saved?.from || 'USD';
  toEl.value = q.get('to') || saved?.to || 'RWF';
  amountEl.value = q.get('amount') || saved?.amount || '1000';
  let favs = store.get('fx_favs', ['USD', 'EUR', 'RWF', 'KES', 'UGX', 'TZS', 'BIF', 'ETB', 'GBP', 'RUB', 'CNY', 'INR']);

  const toast = m => { const t = $('#toast'); t.textContent = m; t.classList.add('show'); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 2600); };

  // ---------------------------------------------------------------- formatting
  function money(v, code, extra = 0) {
    const c = INFO[code] || { decimals: 2, locale: 'en-US', symbol: code };
    const digits = Math.min(Math.max(c.decimals, Math.abs(v) < 1 && v !== 0 ? 4 + extra : 0), 8);
    try {
      if (code.length !== 3) throw new Error('not ISO');
      return new Intl.NumberFormat(c.locale, { style: 'currency', currency: code, minimumFractionDigits: Math.min(c.decimals, digits), maximumFractionDigits: digits }).format(v);
    } catch (e) {
      return new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(v) + ' ' + (c.symbol || code);
    }
  }
  const rateText = v => v >= 100 ? v.toLocaleString('en-US', { maximumFractionDigits: 2 })
    : v >= 1 ? v.toLocaleString('en-US', { maximumFractionDigits: 4 }) : Number(v.toPrecision(5)).toString();
  const amount = () => { const v = parseFloat(String(amountEl.value).replace(/[^\d.\-]/g, '')); return isFinite(v) ? v : 0; };
  const rate = (a, b) => data && data.rates[a] && data.rates[b] ? data.rates[b] / data.rates[a] : null;
  const ago = iso => {
    if (!iso) return '';
    const s = (Date.now() - new Date(iso)) / 1000;
    return s < 90 ? 'just now' : s < 3600 ? Math.round(s / 60) + ' min ago' : s < 86400 ? Math.round(s / 3600) + ' h ago' : Math.round(s / 86400) + ' days ago';
  };
  const when = iso => iso ? new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' }) : '—';

  // ---------------------------------------------------------------- live rates
  async function loadRates(silent) {
    try {
      const r = await fetch('/api/rates', { cache: 'no-store' });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || 'Rates not available');
      const changed = data && data.updated_at !== d.updated_at;
      data = d;
      $('#fxError').classList.add('hidden');
      if (changed && silent) toast('New exchange rates loaded');
      liveBadge();
      render();
    } catch (e) {
      if (!data) {
        $('#fxError').textContent = '⚠ ' + e.message + ' The converter will start working as soon as the rates load - this page tries again every few minutes.';
        $('#fxError').classList.remove('hidden');
        $('#liveText').textContent = 'Offline';
        $('#liveBadge').className = 'live off';
      }
    }
  }
  function liveBadge() {
    const b = $('#liveBadge');
    b.className = 'live' + (data.stale ? ' stale' : '');
    $('#liveText').innerHTML = (data.stale ? 'Offline - last saved rates' : 'Live rates') +
      ` · updated ${when(data.updated_at)}` + (data.next_update && !data.stale ? ` · next ${when(data.next_update)}` : '') +
      ` · checked ${ago(data.fetched_at)}`;
    $('#liveBadge').title = 'Sources: ' + data.sources.map(s => s.name).join(', ');
  }
  setInterval(() => loadRates(true), POLL_MS);
  setInterval(() => data && liveBadge(), 30 * 1000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) loadRates(true); });

  // ---------------------------------------------------------------- main conversion
  function render() {
    if (!data) return;
    const a = fromEl.value, b = toEl.value, amt = amount(), r = rate(a, b);
    store.set('fx_pair', { from: a, to: b, amount: amountEl.value });
    if (r === null) {
      $('#crTo').textContent = '—';
      $('#crRates').textContent = `No live rate for ${!data.rates[a] ? a : b} right now.`;
      return;
    }
    $('#crFrom').textContent = `${money(amt, a)} ${INFO[a].name} =`;
    $('#crTo').innerHTML = `${money(amt * r, b, 2)} <small>${INFO[b].name}</small>`;
    $('#crRates').innerHTML = `<span>${INFO[a].flag} 1 ${a} = <b>${rateText(r)}</b> ${b}</span><span>${INFO[b].flag} 1 ${b} = <b>${rateText(1 / r)}</b> ${a}</span>`;
    renderFavs();
    renderTable();
  }
  amountEl.addEventListener('input', render);
  [fromEl, toEl].forEach(el => el.addEventListener('change', () => { render(); history(); }));
  $('#swap').addEventListener('click', () => { [fromEl.value, toEl.value] = [toEl.value, fromEl.value]; render(); history(); });
  $$('#pairs button').forEach(b => b.addEventListener('click', () => { fromEl.value = b.dataset.from; toEl.value = b.dataset.to; render(); history(); }));

  // ---------------------------------------------------------------- favourites
  function renderFavs() {
    const a = fromEl.value, amt = amount();
    $('#favs').innerHTML = favs.filter(c => c !== a && INFO[c]).map(c => {
      const r = rate(a, c);
      return `<li><span class="fl">${INFO[c].flag}</span><span class="fc"><b>${c}</b><small>${INFO[c].name}</small></span>
        <span class="fv">${r === null ? '—' : money(amt * r, c, 2)}</span>
        <button data-use="${c}" title="Convert to ${c}">→</button><button data-del="${c}" title="Remove">×</button></li>`;
    }).join('');
    $$('#favs [data-del]').forEach(b => b.onclick = () => { favs = favs.filter(x => x !== b.dataset.del); store.set('fx_favs', favs); renderFavs(); });
    $$('#favs [data-use]').forEach(b => b.onclick = () => { toEl.value = b.dataset.use; render(); history(); scrollTo({ top: 0, behavior: 'smooth' }); });
  }
  $('#addFavBtn').addEventListener('click', () => {
    const c = $('#addFav').value;
    if (!favs.includes(c)) { favs.push(c); store.set('fx_favs', favs); renderFavs(); toast(`${c} added`); }
  });

  // ---------------------------------------------------------------- all currencies table
  let region = '';
  function renderTable() {
    const a = fromEl.value, term = $('#search').value.trim().toLowerCase();
    const rows = Object.values(INFO).filter(c => (!region || c.region === region) &&
      (!term || (c.code + ' ' + c.name + ' ' + c.countries.join(' ')).toLowerCase().includes(term)));
    $('#allTable').innerHTML = `<thead><tr><th>Currency</th><th>Used in</th><th>1 ${a} =</th><th>= 1 ${a}</th><th></th></tr></thead><tbody>` +
      rows.map(c => {
        const r = rate(a, c.code);
        return `<tr><td><span class="fl">${c.flag}</span> <b>${c.code}</b> ${c.name}</td><td class="cty">${c.countries.slice(0, 3).join(', ')}${c.countries.length > 3 ? ' +' + (c.countries.length - 3) : ''}</td>
          <td class="num">${r === null ? '<span class="muted">n/a</span>' : rateText(r) + ' ' + c.code}</td>
          <td class="num">${r === null ? '' : rateText(1 / r) + ' ' + a}</td>
          <td><button class="mini" data-pick="${c.code}">Convert</button></td></tr>`;
      }).join('') + '</tbody>';
    $$('#allTable [data-pick]').forEach(b => b.onclick = () => { toEl.value = b.dataset.pick; render(); history(); scrollTo({ top: 0, behavior: 'smooth' }); });
  }
  $('#search').addEventListener('input', renderTable);
  $$('#regions button').forEach(b => b.addEventListener('click', () => {
    region = b.dataset.region; $$('#regions button').forEach(x => x.classList.toggle('on', x === b)); renderTable();
  }));

  // ---------------------------------------------------------------- history chart (SVG)
  async function history() {
    const a = fromEl.value, b = toEl.value, my = ++histReq;
    $('#histTitle').textContent = `${a} → ${b} history`;
    $('#histChart').innerHTML = '<p class="muted small">Loading history…</p>';
    $('#histStats').innerHTML = '';
    try {
      const r = await fetch(`/api/rates/history?from=${a}&to=${b}&days=${histDays}`);
      const d = await r.json();
      if (my !== histReq) return;
      if (!r.ok || !d.points.length) throw new Error(d.error || 'No history');
      drawLine(d.points, a, b);
    } catch (e) {
      if (my === histReq) $('#histChart').innerHTML = `<p class="muted small">History is not available right now (${e.message}).</p>`;
    }
  }
  $$('#range button').forEach(btn => btn.addEventListener('click', () => {
    histDays = +btn.dataset.days; $$('#range button').forEach(x => x.classList.toggle('on', x === btn)); history();
  }));
  function drawLine(points, a, b) {
    const vals = points.map(p => p[1]), min = Math.min(...vals), max = Math.max(...vals);
    const first = vals[0], last = vals[vals.length - 1], change = (last - first) / first * 100;
    $('#histStats').innerHTML = `<span>Low <b>${rateText(min)}</b></span><span>High <b>${rateText(max)}</b></span>` +
      `<span>Change <b class="${change >= 0 ? 'up' : 'down'}">${change >= 0 ? '▲' : '▼'} ${Math.abs(change).toFixed(2)} %</b></span>`;
    const W = 640, H = 240, L = 56, R = 12, T = 12, B = 28, pad = (max - min) * 0.1 || max * 0.01;
    const lo = min - pad, hi = max + pad;
    const x = i => L + (W - L - R) * i / Math.max(points.length - 1, 1), y = v => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
    const line = points.map((p, i) => `${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join(' ');
    let grid = '';
    const dec = Math.min(10, Math.max(0, Math.ceil(-Math.log10((hi - lo) / 4)) + 1));   // enough digits to tell the lines apart
    for (let k = 0; k <= 4; k++) {
      const v = lo + (hi - lo) * k / 4;
      grid += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="grid"/><text x="${L - 6}" y="${y(v) + 4}" class="axis" text-anchor="end">${v.toFixed(dec)}</text>`;
    }
    const labelsAt = [0, Math.floor(points.length / 2), points.length - 1];
    const labels = labelsAt.map(i => `<text x="${x(i)}" y="${H - 8}" class="axis" text-anchor="${i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'}">${new Date(points[i][0]).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}</text>`).join('');
    const dots = points.map((p, i) => `<circle cx="${x(i)}" cy="${y(p[1])}" r="${points.length > 40 ? 0 : 2.5}" class="dot"><title>${p[0]}: 1 ${a} = ${rateText(p[1])} ${b}</title></circle>`).join('');
    $('#histChart').innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${a} to ${b} rate history">${grid}
      <polygon points="${L},${H - B} ${line} ${W - R},${H - B}" class="area"/><polyline points="${line}" class="line"/>${dots}${labels}</svg>`;
  }

  loadRates(false).then(history);
})();
