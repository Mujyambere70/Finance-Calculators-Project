/* CalcWise scientific calculator - keypad, keyboard, live preview, memory, history.
   The maths is done safely in Python (scientific.py) through /api/scientific. */
(() => {
  'use strict';
  const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
  const csrf = $('meta[name=csrf-token]').content;
  const input = $('#expr'), result = $('#result'), extra = $('#extra');
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };
  const MODES = ['DEG', 'RAD', 'GRAD'];
  let mode = store.get('sci_mode', 'DEG'), second = false, hyp = false;
  let ans = store.get('sci_ans', 0), memory = store.get('sci_mem', 0), history = store.get('sci_history', []);
  let lastValue = null, justEvaluated = false;

  const toast = msg => { const t = $('#toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 2200); };

  function status() {
    $('#modeBadge').textContent = $('#modeBtn').textContent = mode;
    $('#secondBadge').hidden = !second; $('#hypBadge').hidden = !hyp; $('#memBadge').hidden = !memory;
    $('#ansBadge').textContent = 'Ans = ' + short(ans);
    $$('[data-act=second]').forEach(b => b.classList.toggle('on', second));
    $$('[data-act=hyp]').forEach(b => b.classList.toggle('on', hyp));
    $$('.keys button').forEach(b => {                                   // show the second / hyp labels
      if (!b.dataset.base) b.dataset.base = b.textContent;
      let label = b.dataset.base;
      if (b.dataset.h && hyp) label = b.dataset.base + 'h';
      if (second && (b.dataset[2] || b.dataset.secondAct)) label = b.dataset.label2 || b.dataset.secondLabel || (b.dataset.base + (hyp && b.dataset.h ? 'h' : '') + '⁻¹');
      b.innerHTML = label.replace('⁻¹', '<sup>-1</sup>');
    });
  }
  const short = v => Math.abs(v) >= 1e9 || (Math.abs(v) < 1e-4 && v !== 0) ? Number(v).toExponential(4) : String(+Number(v).toPrecision(10));

  // ---------------------------------------------------------------- editing
  function insert(text) {
    if (justEvaluated) {                       // after "=": a number starts fresh, an operator continues with Ans
      input.value = /^(\^|!|%| mod |[+−×÷*/])/.test(text) ? 'Ans' : '';
      justEvaluated = false;
    }
    const s = input.selectionStart ?? input.value.length, e = input.selectionEnd ?? s;
    input.value = input.value.slice(0, s) + text + input.value.slice(e);
    const pos = s + text.length;
    input.setSelectionRange(pos, pos);
    input.focus();
    preview();
  }
  function act(name) {
    switch (name) {
      case 'second': second = !second; break;
      case 'hyp': hyp = !hyp; break;
      case 'mode': mode = MODES[(MODES.indexOf(mode) + 1) % 3]; store.set('sci_mode', mode); preview(); break;
      case 'clear': input.value = ''; result.textContent = '0'; extra.innerHTML = '&nbsp;'; result.classList.remove('err'); justEvaluated = false; break;
      case 'back': {
        const s = input.selectionStart, e = input.selectionEnd;
        if (s !== e) input.value = input.value.slice(0, s) + input.value.slice(e);
        else if (s > 0) { input.value = input.value.slice(0, s - 1) + input.value.slice(s); input.setSelectionRange(s - 1, s - 1); }
        justEvaluated = false; preview(); break;
      }
      case 'neg': input.value = input.value ? `-(${input.value})` : '-'; justEvaluated = false; preview(); break;
      case 'exp': insert('E'); break;
      case 'equals': equals(); break;
      case 'copy': navigator.clipboard?.writeText(result.textContent).then(() => toast('Result copied')); break;
      case 'mc': memory = 0; store.set('sci_mem', 0); toast('Memory cleared'); break;
      case 'mr': insert(String(memory)); break;
      case 'mplus': case 'mminus':
        if (lastValue === null) { toast('Calculate something first'); break; }
        memory += name === 'mplus' ? lastValue : -lastValue; store.set('sci_mem', memory);
        toast(`Memory = ${short(memory)}`); break;
    }
    status();
  }
  $$('.keys button').forEach(b => b.addEventListener('click', () => {
    if (b.dataset.act) {
      const a = second && b.dataset.secondAct ? b.dataset.secondAct : b.dataset.act;
      if (second && !['second', 'hyp'].includes(a)) second = false;
      act(a);
      return;
    }
    let text = b.dataset.ins;
    if (hyp && b.dataset.h) text = second ? b.dataset.h2 : b.dataset.h;
    else if (second && b.dataset[2]) text = b.dataset[2];
    second = false; hyp = false; status();
    insert(text);
  }));

  // ---------------------------------------------------------------- talk to Python
  let timer, seq = 0;
  const api = expr => fetch('/api/scientific', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: JSON.stringify({ expr, angle: mode, ans, memory }),
  }).then(async r => ({ ok: r.ok, data: await r.json() }));

  function preview() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const expr = input.value.trim(), my = ++seq;
      if (!expr) { result.textContent = '0'; result.classList.remove('err'); extra.innerHTML = '&nbsp;'; return; }
      const { ok, data } = await api(expr);
      if (my !== seq) return;
      result.classList.toggle('err', false);
      result.classList.toggle('preview', true);
      if (ok) { show(data); } else { result.textContent = '…'; extra.textContent = data.error; }
    }, 180);
  }
  function show(data) {
    result.innerHTML = data.display.replace(/×10\^(-?\d+)/, '×10<sup>$1</sup>');
    const parts = Object.entries(data.extras || {}).map(([k, v]) => `<span><b>${k}</b> ${v}</span>`);
    extra.innerHTML = parts.join('') || '&nbsp;';
  }
  async function equals() {
    const expr = input.value.trim();
    if (!expr) return;
    clearTimeout(timer);
    const { ok, data } = await api(expr);
    result.classList.remove('preview');
    if (!ok) { result.textContent = 'Error'; result.classList.add('err'); extra.textContent = data.error; return; }
    show(data);
    ans = lastValue = data.value; store.set('sci_ans', ans);
    history.unshift({ expr, display: data.display, mode });
    history = history.slice(0, 50); store.set('sci_history', history);
    renderHistory();
    justEvaluated = true;
    status();
    $('#sci').classList.remove('flash'); void $('#sci').offsetWidth; $('#sci').classList.add('flash');
  }

  function renderHistory() {
    const ol = $('#history');
    if (!history.length) { ol.innerHTML = '<li class="muted">Your calculations will appear here. Click one to use it again.</li>'; return; }
    ol.innerHTML = '';
    history.forEach(h => {
      const li = document.createElement('li');
      li.innerHTML = `<span class="h-expr"></span><b class="h-res"></b><small>${h.mode}</small>`;
      li.querySelector('.h-expr').textContent = h.expr;
      li.querySelector('.h-res').textContent = '= ' + h.display;
      li.title = 'Click to use this expression again';
      li.addEventListener('click', () => { input.value = h.expr; justEvaluated = false; input.focus(); preview(); });
      ol.appendChild(li);
    });
  }
  $('#clearHistory').addEventListener('click', () => { history = []; store.set('sci_history', []); renderHistory(); });

  // ---------------------------------------------------------------- keyboard
  input.addEventListener('input', () => { justEvaluated = false; preview(); });
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' || (e.key === '=' && !e.shiftKey)) { e.preventDefault(); equals(); }
    else if (e.key === 'Escape') { e.preventDefault(); act('clear'); }
    else if (justEvaluated && e.key.length === 1) {
      if (/[+\-*/^!%×÷]/.test(e.key)) { input.value = 'Ans'; input.setSelectionRange(3, 3); }
      else if (/[\w.(]/.test(e.key)) input.value = '';
      justEvaluated = false;
    }
  });
  document.addEventListener('keydown', e => {           // typing anywhere goes into the display
    if (document.activeElement !== input && !e.ctrlKey && !e.metaKey && e.key.length === 1 && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) {
      input.focus();
    }
  });

  status();
  renderHistory();
  input.focus();
})();
