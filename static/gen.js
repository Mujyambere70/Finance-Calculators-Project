/* CalcWise generators: OTP / authenticator, password, email, phone, passport */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const csrf = $('meta[name=csrf-token]').content;
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const toast = m => { const t = $('#toast'); t.textContent = m; t.classList.add('show'); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 2200); };
  const store = {
    get: (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
  };
  const api = async (tool, body) => {
    const r = await fetch('/api/generate/' + tool, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({ error: 'Server error.' }));
    if (!r.ok) throw Object.assign(new Error(data.error || 'Error'), { field: data.field });
    return data;
  };
  async function copy(text, what = 'Copied') {
    try { await navigator.clipboard.writeText(text); }
    catch {
      const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); } catch { /* ignore */ } ta.remove();
    }
    toast(what);
  }

  // ---------------------------------------------------------------- tabs (no page reload)
  let tool = $('#genTabs a.on').dataset.tool;
  function showTab(t, push) {
    tool = t;
    $$('#genTabs a').forEach(a => a.classList.toggle('on', a.dataset.tool === t));
    $$('.gen-panel').forEach(p => { p.hidden = p.dataset.panel !== t; });
    $('#results').hidden = true;
    if (push) history.pushState({ t }, '', '/generators/' + t);
    document.title = $(`#genTabs a[data-tool="${t}"]`).textContent.trim().replace(/^\S+\s*/, '') + ' generator · CalcWise';
    if (t === 'otp') refreshTotp();
    const f = $(`.gen-form[data-tool="${t}"]`);
    if (f) run(f);
  }
  $$('#genTabs a').forEach(a => a.addEventListener('click', e => { e.preventDefault(); showTab(a.dataset.tool, true); }));
  addEventListener('popstate', () => showTab(location.pathname.split('/')[2] || 'otp', false));

  // ---------------------------------------------------------------- form helpers
  function formData(form) {
    const o = {};
    $$('input, select', form).forEach(el => {
      if (!el.name || el.closest('[hidden]')) return;
      if (el.type === 'checkbox') o[el.name] = el.checked;
      else if (el.type === 'radio') { if (el.checked) o[el.name] = el.value; }
      else o[el.name] = el.value;
    });
    return o;
  }
  function showError(form, err) {
    $$('.field', form).forEach(f => f.classList.remove('bad'));
    const input = err.field && $(`[name="${err.field}"]`, form);
    const field = input && input.closest('.field');
    if (field && $('.err', field)) { field.classList.add('bad'); $('.err', field).textContent = err.message; }
    else toast(err.message);
  }
  $$('.range').forEach(r => {
    const out = $(`.out[data-for="${r.name}"]`, r.closest('form'));
    const upd = () => { if (out) out.textContent = r.value; };
    r.addEventListener('input', upd); upd();
  });

  // password form: show the fields of the chosen mode
  const pwForm = $('.gen-form[data-tool="password"]');
  function pwMode() {
    const mode = $('input[name=mode]:checked', pwForm).value;
    $$('[data-modes]', pwForm).forEach(el => { el.hidden = !el.dataset.modes.split(' ').includes(mode); });
    const len = $('input[name=length]', pwForm);
    if (mode === 'pin') { len.min = 4; len.max = 12; if (+len.value > 12 || len.dataset.mode !== 'pin') len.value = 6; }
    else { len.min = 4; len.max = 64; if (len.dataset.mode === 'pin') len.value = 16; }
    len.dataset.mode = mode;
    len.dispatchEvent(new Event('input'));
  }
  $$('input[name=mode]', pwForm).forEach(r => r.addEventListener('change', () => { pwMode(); run(pwForm); }));
  pwMode();

  // email form: custom domain field
  const src = $('#domainSource');
  function domainUi() {
    $('#customDomain').hidden = src.value !== 'custom';
    $('#domainHelp').textContent = {
      safe: 'Reserved for testing - mail to them never reaches a real person.',
      providers: 'Looks real, but these addresses may belong to real people: never send them mail.',
      custom: 'Use a domain you own, e.g. your test company.',
    }[src.value];
    $('#domainHelp').classList.toggle('warn-text', src.value === 'providers');
  }
  src.addEventListener('change', domainUi);

  // phone form: the fictional option only where it exists
  const phoneForm = $('.gen-form[data-tool="phone"]');
  const SAFE = ['US', 'CA', 'GB', 'AG', 'AI', 'AS', 'BB', 'BM', 'BS', 'DM', 'DO', 'GD', 'GU', 'JM', 'KN', 'KY', 'LC', 'MP', 'MS', 'PR', 'SX', 'TC', 'TT', 'VC', 'VG', 'VI'];
  function phoneSafe() {
    const c = $('select[name=country]', phoneForm).value, ok = SAFE.includes(c);
    $('#safeWrap').classList.toggle('disabled', !ok);
    $('input[name=safe]', phoneForm).disabled = !ok;
    if (!ok) $('input[name=safe]', phoneForm).checked = false;
  }
  $('select[name=country]', phoneForm).addEventListener('change', () => { phoneSafe(); run(phoneForm); });
  phoneSafe();

  // ---------------------------------------------------------------- generate + results table
  const COLS = {
    otp: [['Code', 'value', 'mono big']],
    password: [['Password', 'value', 'mono'], ['Strength', 'strength'], ['Time to crack*', 'crack', 'muted']],
    email: [['Email address', 'value', 'mono'], ['Type', 'type', 'muted'], ['Name', 'name']],
    phone: [['Country', 'country'], ['International', 'value', 'mono'], ['National', 'national', 'mono'], ['E.164', 'e164', 'mono muted'], ['Note', 'quality', 'muted']],
    passport: [['Country', 'country'], ['Passport number', 'value', 'mono big'], ['Format', 'format', 'muted'], ['Format source', 'quality', 'muted']],
  };
  const TITLES = { otp: 'One-time codes', password: 'Passwords', email: 'Email addresses', phone: 'Phone numbers', passport: 'Passport numbers (test data)' };
  let last = null;

  function cell(item, key, cls) {
    if (key === 'strength') return `<td><span class="sbadge s-${item.label.replace(/\s/g, '').toLowerCase()}">${esc(item.label)}</span> <small class="muted">${item.bits} bits</small></td>`;
    if (key === 'country') return `<td><span class="fl">${item.flag}</span> ${esc(item.country)} <small class="muted">${esc(item.dial || '')}</small></td>`;
    if (key === 'quality') {
      const q = item.quality, c = { known: 'good', exact: 'good', 'real prefixes': 'good', 'fictional (safe)': 'good' }[q] || 'warn';
      return `<td><span class="qbadge ${c}">${esc(q)}</span>${item.operator ? ` <small>${esc(item.operator)}</small>` : ''}</td>`;
    }
    return `<td class="${cls || ''}">${esc(item[key])}</td>`;
  }
  function render(t, data) {
    last = { t, data };
    const cols = COLS[t];
    $('#resTitle').textContent = `${TITLES[t]} · ${data.items.length}`;
    $('#resTable').innerHTML = `<thead><tr>${cols.map(c => `<th>${c[0]}</th>`).join('')}<th></th></tr></thead><tbody>` +
      data.items.map((it, i) => `<tr>${cols.map(c => cell(it, c[1], c[2])).join('')}<td class="cp"><button class="mini" data-i="${i}">Copy</button></td></tr>`).join('') + '</tbody>';
    $$('#resTable [data-i]').forEach(b => b.onclick = () => copy(data.items[b.dataset.i].raw || data.items[b.dataset.i].value));
    const info = $('#resInfo');
    let msg = '', cls = 'good';
    if (t === 'otp') msg = `Each code is one of ${data.info.combinations} possible codes - a guess is right 1 time in ${data.info.combinations}. Make them expire after ${data.info.valid_minutes} min and allow only a few tries.`;
    if (t === 'password') msg = '*Average time for an attacker with a fast computer (10 billion guesses per second) to guess it offline. PINs are protected by the try limit of the card or phone, not by length.';
    if (t === 'email' && data.info.domains[0] === 'gmail.com') { msg = 'These look like real addresses - they may belong to real people. Use them only as fake form input; never send mail to them.'; cls = 'warn'; }
    if (t === 'phone' && !data.info.library) msg = 'Formats follow each country\'s numbering plan. "approximate" = right calling code and length, usual prefixes.';
    if (t === 'passport') { msg = 'Number formats for testing forms only - not a document, not valid for travel.'; cls = 'warn'; }
    info.className = 'alert ' + cls + (msg ? '' : ' hidden');
    info.textContent = msg;
    $('#results').hidden = false;
  }
  async function run(form) {
    const t = form.dataset.tool;
    try {
      $$('.field', form).forEach(f => f.classList.remove('bad'));
      const data = await api(t, formData(form));
      render(t, data);
      store.set('gen_' + t, formData(form));
    } catch (e) { showError(form, e); }
  }
  $$('.gen-form').forEach(f => {
    f.addEventListener('submit', e => { e.preventDefault(); run(f); if (innerWidth < 1020) $('#results').scrollIntoView({ behavior: 'smooth' }); });
    $$('select, input[type=checkbox]', f).forEach(el => el.addEventListener('change', () => { if (el.name !== 'mode' && el.name !== 'country') run(f); }));
    $$('.range', f).forEach(el => el.addEventListener('change', () => run(f)));
  });
  $('#regen').addEventListener('click', () => run($(`.gen-form[data-tool="${last.t}"]`)));
  $('#copyAll').addEventListener('click', () => last && copy(last.data.items.map(i => i.raw || i.value).join('\n'), `${last.data.items.length} copied`));
  $('#csv').addEventListener('click', () => {
    if (!last) return;
    const cols = COLS[last.t].filter(c => c[1] !== 'strength');
    const q = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const rows = [cols.map(c => q(c[0]))].concat(last.data.items.map(it => cols.map(c => q(it[c[1]]))));
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob(['﻿' + rows.map(r => r.join(',')).join('\r\n')], { type: 'text/csv' }));
    a.download = `calcwise-${last.t}-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
  });

  // ---------------------------------------------------------------- authenticator (TOTP / HOTP)
  const tf = $('#totpForm');
  let otpMode = 'totp', state = null, timer = null, refreshing = false;
  const savedSecret = store.get('gen_totp_secret', '');
  if (savedSecret) $('#secret').value = savedSecret;

  function drawQr(uri) {
    const box = $('#qr');
    if (!window.qrcode) { box.innerHTML = '<span class="muted small">QR code needs internet - type the setup key in your app instead.</span>'; return; }
    const qr = window.qrcode(0, 'M'); qr.addData(uri); qr.make();
    box.innerHTML = qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
  }
  async function refreshTotp() {
    if (refreshing) return;
    refreshing = true;
    try {
      const opts = formData(tf); opts.mode = otpMode;
      state = await api('totp', opts);
      $$('.field', tf).forEach(f => f.classList.remove('bad'));
      if ($('#secret').value.replace(/\s/g, '').toUpperCase() !== state.secret) $('#secret').value = state.secret_grouped;
      store.set('gen_totp_secret', state.secret);
      const pretty = c => c.length === 6 ? c.slice(0, 3) + ' ' + c.slice(3) : c.slice(0, 4) + ' ' + c.slice(4);
      $('#totpCode').textContent = pretty(state.code);
      $('#uri').textContent = state.uri;
      if (state.mode === 'totp') {
        $('#totpNb').innerHTML = `<div><small>Previous</small><b class="mono">${pretty(state.previous)}</b></div><div><small>Next</small><b class="mono">${pretty(state.next)}</b></div>`;
        state.until = Date.now() + state.remaining * 1000;
      } else {
        $('#totpNb').innerHTML = '<small>Next codes</small>' + state.next_codes.slice(1).map(c => `<div><small>#${c.counter}</small><b class="mono">${pretty(c.code)}</b></div>`).join('');
        $('#totpLeft').textContent = `counter ${state.counter}`;
        $('#ring').style.strokeDashoffset = 0;
      }
      drawQr(state.uri);
      tick();
    } catch (e) { showError(tf, e); }
    finally { refreshing = false; }
  }
  function tick() {
    clearTimeout(timer);
    if (!state || state.mode !== 'totp' || tool !== 'otp') return;
    const left = Math.max(0, (state.until - Date.now()) / 1000);
    $('#totpLeft').textContent = `${Math.ceil(left)} s left`;
    const C = 2 * Math.PI * 54;
    $('#ring').style.strokeDasharray = C;
    $('#ring').style.strokeDashoffset = C * (1 - left / state.period);
    $('#totp').classList.toggle('ending', left <= 5);
    if (left <= 0) { refreshTotp(); return; }
    timer = setTimeout(tick, 250);
  }
  $$('#otpMode button').forEach(b => b.addEventListener('click', () => {
    otpMode = b.dataset.mode;
    $$('#otpMode button').forEach(x => x.classList.toggle('on', x === b));
    $$('[data-totp-only]', tf).forEach(el => { el.hidden = otpMode !== 'totp'; });
    $$('[data-hotp-only]', tf).forEach(el => { el.hidden = otpMode !== 'hotp'; });
    $('#verifyMsg').classList.add('hidden');
    refreshTotp();
  }));
  $('#newSecret').addEventListener('click', () => { $('#secret').value = ''; $('input[name=counter]', tf).value = 0; refreshTotp(); toast('New secret - add it to your app again'); });
  let deb;
  $$('input, select', tf).forEach(el => el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', () => { clearTimeout(deb); deb = setTimeout(refreshTotp, 350); }));
  $$('[data-copy-from]').forEach(b => b.addEventListener('click', () => {
    const el = $('#' + b.dataset.copyFrom);
    copy((el.value ?? el.textContent).replace(b.dataset.copyFrom === 'secret' ? /\s/g : /^$/, ''), 'Copied');
  }));
  $('#totpCode').addEventListener('click', () => state && copy(state.code, 'Code copied'));
  $('#verifyForm').addEventListener('submit', async e => {
    e.preventDefault();
    const msg = $('#verifyMsg');
    try {
      const opts = formData(tf); opts.mode = otpMode; opts.code = $('#verifyCode').value;
      const r = await api('totp-verify', opts);
      msg.className = 'alert ' + (r.valid ? 'good' : 'bad');
      msg.textContent = (r.valid ? '✓ ' : '✗ ') + r.message;
      if (r.valid && otpMode === 'hotp') { $('input[name=counter]', tf).value = r.counter + 1; refreshTotp(); }
    } catch (err) { msg.className = 'alert bad'; msg.textContent = err.message; }
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && tool === 'otp' && otpMode === 'totp') refreshTotp(); });

  // ---------------------------------------------------------------- password strength checker (browser only)
  const COMMON = ['password', '123456', 'qwerty', 'admin', 'welcome', 'letmein', 'iloveyou', 'monkey', 'dragon', 'football',
    'abc123', 'master', 'login', 'princess', 'sunshine', 'shadow', 'azerty', 'passw0rd', '111111', '000000', 'qwertyuiop', 'parol'];
  function checkPw(pw) {
    let pool = 0;
    const has = { lower: /[a-z]/.test(pw), upper: /[A-Z]/.test(pw), digit: /\d/.test(pw), symbol: /[^a-zA-Z0-9]/.test(pw) };
    if (has.lower) pool += 26; if (has.upper) pool += 26; if (has.digit) pool += 10; if (has.symbol) pool += 33;
    let bits = pw.length * Math.log2(pool || 1);
    const tips = [];
    const low = pw.toLowerCase().replace(/[@4]/g, 'a').replace(/0/g, 'o').replace(/[1!]/g, 'i').replace(/3/g, 'e').replace(/\$/g, 's');
    if (COMMON.some(w => low.includes(w))) { bits = Math.min(bits, 12); tips.push('Contains a very common password'); }
    if (/(.)\1{2,}/.test(pw)) { bits -= 8; tips.push('Repeated characters (aaa)'); }
    if (/(0123|1234|2345|3456|4567|5678|6789|abcd|bcde|qwer|asdf|zxcv)/i.test(pw)) { bits -= 10; tips.push('Keyboard or number sequence'); }
    if (/(19|20)\d{2}/.test(pw)) { bits -= 6; tips.push('Looks like a year'); }
    if (pw.length < 12) tips.push('Use 12 characters or more');
    if (!has.symbol && !has.digit) tips.push('Add numbers or symbols');
    return { bits: Math.max(0, bits), has, tips };
  }
  function crackText(bits) {
    const s = Math.pow(2, bits - 1) / 1e10;
    const units = [['centuries', 3.15e9], ['years', 3.15e7], ['days', 86400], ['hours', 3600], ['minutes', 60]];
    for (const [u, size] of units) if (s >= size) return s / size > 1e6 && u === 'centuries' ? 'millions of centuries' : `${Math.round(s / size).toLocaleString()} ${u}`;
    return s >= 1 ? 'less than a minute' : 'instantly';
  }
  $('#pwCheck').addEventListener('input', e => {
    const pw = e.target.value;
    if (!pw) { $('#pwBar').style.width = 0; $('#pwFacts').innerHTML = '<li class="muted">Start typing…</li>'; return; }
    const r = checkPw(pw);
    const label = r.bits < 28 ? 'Very weak' : r.bits < 40 ? 'Weak' : r.bits < 60 ? 'Fair' : r.bits < 80 ? 'Strong' : 'Very strong';
    const color = { 'Very weak': '#dc2626', Weak: '#f97316', Fair: '#eab308', Strong: '#22c55e', 'Very strong': '#059669' }[label];
    $('#pwBar').style.width = Math.min(100, r.bits / 100 * 100) + '%';
    $('#pwBar').style.background = color;
    $('#pwFacts').innerHTML = `<li><b style="color:${color}">${label}</b> · ${Math.round(r.bits)} bits · cracked in about <b>${crackText(r.bits)}</b></li>` +
      `<li>${pw.length} characters · ${['lower', 'upper', 'digit', 'symbol'].map(k => (r.has[k] ? '✓ ' : '✗ ') + k).join(' · ')}</li>` +
      r.tips.map(t => `<li class="tip">⚠ ${esc(t)}</li>`).join('');
  });
  $('#pwShow').addEventListener('click', () => {
    const i = $('#pwCheck'); i.type = i.type === 'password' ? 'text' : 'password'; $('#pwShow').textContent = i.type === 'password' ? 'Show' : 'Hide';
  });

  // ---------------------------------------------------------------- start
  $$('.gen-form').forEach(f => {               // remember the last options of each generator
    const saved = store.get('gen_' + f.dataset.tool, null);
    if (!saved) return;
    Object.entries(saved).forEach(([k, v]) => {
      $$(`[name="${k}"]`, f).forEach(el => {
        if (el.type === 'checkbox') el.checked = !!v;
        else if (el.type === 'radio') el.checked = el.value === v;
        else el.value = v;
      });
    });
    $$('.range', f).forEach(r => r.dispatchEvent(new Event('input')));
  });
  pwMode(); phoneSafe(); domainUi();
  showTab(tool, false);
})();
