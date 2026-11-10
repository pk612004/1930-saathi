// Officer console: golden-hour queue, case detail with drafts, mule-ring graph, live SSE feed.
const $ = id => document.getElementById(id);
let QUEUE = [], SELECTED = null, DETAIL = null, TAB = 'bank_freeze';

function countdownClass(ms) { return ms == null ? '' : ms < 0 ? 'late' : ms < 30 * 60000 ? 'warn' : 'ok'; }
function leftMs(deadline) { return deadline ? new Date(deadline).getTime() - serverNow() : null; }

const WINDOW_MS = 120 * 60000, LIVE_MS = 10 * 60000;
const tms = iso => iso ? new Date(iso).getTime() : null;
const hhmm = ms => new Date(ms - SERVER_OFFSET).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
function isLive(r) { return r.status === 'intake' && r.live && serverNow() - tms(r.last_activity) < LIVE_MS; }

// ---------- recoverable-money band ----------
let LAST_PULSE = null;
function renderPulse() {
  const now = serverNow();
  let open = 0, frozen = 0, lost = 0, next = null;
  const inside = new Set();
  for (const r of QUEUE) {
    if (r.status === 'closed' || r.duplicate_of) continue;
    for (const t of r.txns || []) {
      const end = tms(t.txn_time) + WINDOW_MS;
      if (!t.txn_time) continue;
      if (end <= now) { lost += t.amount; continue; }
      inside.add(r.id);
      if (r.status === 'freeze_requested') { frozen += t.amount; continue; }
      open += t.amount;
      if (!next || end < next.end) next = { end, amount: t.amount, id: r.id };
    }
  }
  const amt = $('pulseAmt');
  if (LAST_PULSE !== null && open < LAST_PULSE) { amt.classList.add('drop'); setTimeout(() => amt.classList.remove('drop'), 50); }
  LAST_PULSE = open;
  amt.textContent = inr(open);
  $('pulseCases').textContent = inside.size;
  $('pulseFrozen').textContent = inr(frozen);
  $('pulseLost').textContent = inr(lost);
  const nb = $('pulseNext');
  if (next) {
    const ms = next.end - now;
    $('pulseNextTxt').textContent = `${inr(next.amount)} in ${fmtClock(ms)}`;
    nb.disabled = false; nb.classList.toggle('warn', ms < 30 * 60000); nb.onclick = () => select(next.id);
  } else { $('pulseNextTxt').textContent = 'Nothing pending'; nb.disabled = true; nb.classList.remove('warn'); }
}

// ---------- live calls (supervisor view) ----------
const SEEN = {};   // case -> field -> {v, at}
let LIVE_HTML = '';
function renderLive() {
  const rows = QUEUE.filter(isLive);
  if (!rows.length) { $('live').innerHTML = ''; LIVE_HTML = ''; return; }
  const stat = s => s === 'confirmed' ? ' ✓' : s === 'pending_confirm' ? ' …' : '';
  const html = '<h2>On call now</h2>' + rows.map(r => {
    const L = r.live, prev = SEEN[r.id] || (SEEN[r.id] = {});
    const when = L.minutes_ago == null ? '' : L.minutes_ago < 60 ? `${L.minutes_ago} min ago` : `${Math.round(L.minutes_ago / 6) / 10} h ago`;
    const fields = [
      ['Scam', L.fraud || ''],
      ['Amount', L.amount ? inr(L.amount) : ''],
      ['When', when],
      ['UTR', L.utr ? L.utr + stat(L.utr_status) : ''],
      ['Money to', L.suspect ? L.suspect + stat(L.suspect_status) : ''],
      ['Bank', L.bank || ''],
      ['Threat', L.threat ? 'Still in contact with fraudster' : L.threat_checked ? 'No' : ''],
    ];
    const done = fields.filter(f => f[1]).length;
    const html = fields.map(([k, v]) => {
      if (v && (!prev[k] || prev[k].v !== v)) prev[k] = { v, at: Date.now() };
      const isNew = v && Date.now() - prev[k].at < 1600;
      return `<div class="f ${isNew ? 'new' : ''} ${k === 'Threat' && L.threat ? 'bad' : ''}"><span class="k">${k}</span><span class="v ${v ? '' : 'nil'}">${v ? esc(v) : 'listening…'}</span></div>`;
    }).join('');
    const last = (L.last || []).slice().reverse().find(t => t.role === 'caller');
    return `<div class="livecall" data-id="${esc(r.id)}">
      <div class="hd"><span><span class="livedot"></span><b>Live</b> <span class="muted mono" style="font-size:12px">${esc(r.id)}</span></span>
        <span class="muted" style="font-size:12px">${L.turns} answers</span></div>
      ${html}
      ${last ? `<div class="said"><b>Caller:</b> ${esc(last.text)}</div>` : ''}
      <div class="progress"><i style="width:${Math.round(done / fields.length * 100)}%"></i></div>
    </div>`;
  }).join('');
  if (html === LIVE_HTML) return;
  LIVE_HTML = html; $('live').innerHTML = html;
  $('live').querySelectorAll('.livecall').forEach(el => el.onclick = () => select(el.dataset.id));
}

function verTag(v) {
  return v === 'otp_verified' ? '<span class="badge ok">Caller verified</span>'
    : v.startsWith('caller_id') ? '<span class="badge info">Caller ID</span>'
    : v === 'otp_pending' ? '<span class="badge">OTP pending</span>' : '';
}
function countText(ms) { return ms == null ? 'Time unknown' : ms >= 0 ? fmtClock(ms) + ' left' : 'Golden window passed'; }

function renderQueue() {
  if (!QUEUE.length) {
    $('queue').innerHTML = '<div class="empty">No complaints yet. Make a call from the caller page, or load demo complaints.</div>';
    return;
  }
  renderLive();
  const rows = QUEUE.filter(r => !isLive(r));
  if (!rows.length) { $('queue').innerHTML = '<div class="empty">No other complaints.</div>'; return; }
  $('queue').innerHTML = rows.map(r => {
    const ms = leftMs(r.golden_deadline);
    const badges = [
      r.live_threat ? '<span class="badge danger">Live threat</span>' : '',
      r.duplicate_of ? '<span class="badge warn">Possible duplicate</span>' : '',
      r.cluster_id ? `<span class="badge ring">${esc(r.cluster_id)}, ${r.cluster_size} victims</span>` : '',
      r.channel && r.channel !== 'web' ? `<span class="badge info">${esc(r.channel)}</span>` : '',
      (r.llm_fields || []).length ? '<span class="badge purple">Evon</span>' : '',
      r.status === 'intake' ? '<span class="badge">Call ended early</span>'
        : r.status !== 'filed' ? `<span class="badge">${esc(r.status.replace('_', ' '))}</span>` : '',
    ].join('');
    return `<div class="qcard ${r.id === SELECTED ? 'sel' : ''} ${r.status === 'closed' ? 'closed' : ''} ${r.duplicate_of ? 'dup' : ''}" data-id="${esc(r.id)}" tabindex="0">
      <div class="top"><span class="amt">${inr(r.total_amount)}</span><span class="count ${countdownClass(ms)}" data-deadline="${esc(r.golden_deadline || '')}">${countText(ms)}</span></div>
      <div class="label" title="${esc(r.fraud_label)}">${esc(r.fraud_label)}</div>
      ${badges ? `<div class="badges">${badges}</div>` : ''}
    </div>`;
  }).join('');
  $('queue').querySelectorAll('.qcard').forEach(el => {
    el.onclick = () => select(el.dataset.id);
    el.onkeydown = e => { if (e.key === 'Enter') select(el.dataset.id); };
  });
}

let TL_TICK = 0;
function tick() {
  renderPulse();
  if (DETAIL && ++TL_TICK % 15 === 0) { const el = document.getElementById('tl'); if (el) el.outerHTML = timelineHTML(DETAIL); }
  document.querySelectorAll('.count[data-deadline]').forEach(el => {
    const d = el.dataset.deadline; if (!d) return;
    const ms = leftMs(d);
    el.classList.remove('ok', 'warn', 'late'); const cc = countdownClass(ms); if (cc) el.classList.add(cc);
    el.textContent = el.classList.contains('bare') ? (ms >= 0 ? fmtClock(ms) : 'Passed') : countText(ms);
  });
}

async function loadQueue() {
  try {
    const q = await api('/api/queue');
    syncClock(q.now);
    QUEUE = q.queue;
    renderQueue();
    renderPulse();
    if (SELECTED && !QUEUE.find(r => r.id === SELECTED)) SELECTED = null;
    if (!SELECTED && QUEUE.length) select((QUEUE.find(r => !isLive(r)) || QUEUE[0]).id);
    if (SELECTED && QUEUE.find(r => r.id === SELECTED && isLive(r))) select(SELECTED);
  } catch (e) { /* server restarting */ }
}

async function select(id) {
  SELECTED = id;
  renderQueue();
  try { DETAIL = await api('/api/cases/' + id); renderDetail(); }
  catch (e) {
    // the case is gone (e.g. the database was reset): fall back to the top of the queue
    SELECTED = null; DETAIL = null;
    const first = QUEUE.find(r => r.id !== id);
    if (first) return select(first.id);
    $('detail').innerHTML = '<div class="empty">Select a complaint from the queue.</div>';
  }
}

function timelineHTML(c) {
  const now = serverNow();
  const debits = c.transactions.filter(t => t.txn_time).map(t => ({ t: tms(t.txn_time), a: t.amount }));
  const call = tms(c.call_started_at), filed = tms(c.filed_at), end = tms(c.golden_deadline);
  const fz = (c.audit || []).find(a => /freeze/.test(a.action || ''));
  const freeze = fz ? tms(fz.ts) : null;
  if (!debits.length || !end) return '<div class="muted" style="font-size:13px;margin:0 0 22px">Timeline appears once the caller says when the money left.</div>';
  const t0 = Math.min(...debits.map(d => d.t), call || Infinity);
  const t1 = Math.max(end, now + 5 * 60000);
  const span = t1 - t0, pad = .03;
  const x = t => (pad + (1 - 2 * pad) * (t - t0) / span) * 100;
  const left = end - now, nowX = x(Math.min(now, t1));
  const marks = [];
  debits.forEach(d => marks.push(`<i class="tl-m debit" style="left:${x(d.t)}%" title="${inr(d.a)} debited"></i>`));
  if (call) marks.push(`<i class="tl-m call" style="left:${x(call)}%" title="Called 1930"></i>`);
  if (filed) marks.push(`<i class="tl-m filed" style="left:${x(filed)}%" title="Filed"></i>`);
  if (freeze) marks.push(`<i class="tl-m freeze" style="left:${x(freeze)}%" title="Freeze requested"></i>`);
  const legend = [];
  debits.forEach((d, i) => legend.push(['debit', d.t, `${inr(d.a)} debited`]));
  if (call) legend.push(['call', call, 'Called 1930']);
  if (filed) legend.push(['filed', filed, 'Filed']);
  if (freeze) legend.push(['freeze', freeze, 'Freeze requested']);
  legend.push(['end', end, left > 0 ? 'Window closes' : 'Window closed']);
  legend.sort((a, b) => a[1] - b[1]);
  const lab = legend.map(([k, t, txt]) => `<span><i class="${k}"></i>${esc(txt)} <b>${hhmm(t)}</b></span>`).join('');
  return `<div class="tl" id="tl"><div class="tl-track">
      <div class="tl-bar"></div>
      <div class="tl-gone" style="width:${nowX}%"></div>
      ${left > 0 ? `<div class="tl-left ${left < 30 * 60000 ? 'warn' : ''}" style="left:${nowX}%;width:${x(end) - nowX}%"></div>` : ''}
      <div class="tl-end" style="left:${x(end)}%"></div>
      ${marks.join('')}
      <div class="tl-now" style="left:${nowX}%"></div>
    </div><div class="tl-legend">${lab}</div></div>`;
}

function renderDetail() {
  const c = DETAIL; if (!c) return;
  const s = c.score;
  const sus = c.suspect;
  const susList = [sus.upi && ['UPI', sus.upi], sus.mobile && ['Mobile', sus.mobile], sus.account && ['Account', sus.account]].filter(Boolean);
  const rows = c.transactions.map((t, i) => `<tr><td>${i + 1}</td><td>${inr(t.amount)}</td>
      <td>${esc(t.txn_time ? t.txn_time.replace('T', ' ').slice(0, 16) : '—')}</td><td>${esc(t.mode || '—')}</td>
      <td><span class="mono">${esc(t.utr || '—')}</span> ${t.utr_status === 'confirmed' ? '<span class="badge ok">Read back</span>' : t.utr_status === 'unknown' ? '<span class="badge">Not known</span>' : ''}</td></tr>`).join('');
  const drafts = { bank_freeze: c.drafts.bank_freeze, ncrp: JSON.stringify(c.drafts.ncrp, null, 2), sms: c.drafts.sms };
  const parts = Object.entries(s.parts).filter(([, v]) => v).map(([k, v]) => `${k.replace('_', ' ')} +${v}`).join(', ');
  const prop = (k, v) => `<div class="k">${k}</div><div class="v">${v}</div>`;
  const TABS = [['bank_freeze', 'Bank freeze request'], ['ncrp', 'Portal complaint'], ['sms', 'SMS to caller'], ['transcript', 'Transcript'], ['audit', 'Audit trail']];
  $('detail').innerHTML = `
    <div class="crumb">Complaints / <span class="mono">${esc(c.id)}</span></div>
    <div class="casehead">
      <div style="flex:1;min-width:0"><h1>${esc(c.fraud_label)}</h1>
        <div class="sub"><b style="color:var(--text)">${inr(c.total_amount)}</b> lost in ${c.transactions.length} payment${c.transactions.length > 1 ? 's' : ''}. ${esc(c.caller_label)}, call in ${esc({ hi: 'Hindi', en: 'English', pa: 'Punjabi', ta: 'Tamil' }[c.lang] || c.lang)}.</div></div>
      <div class="clockbox"><div class="lbl">Golden window left</div><div class="clock count bare" data-deadline="${esc(c.golden_deadline || '')}">—</div></div>
    </div>
    ${timelineHTML(c)}
    ${c.live_threat ? '<div class="callout red"><span class="ic">⚠</span><div><b>Scam was still in progress when the caller rang.</b> Saathi gave safety instructions first. Call the victim back if the line drops.</div></div>' : ''}
    ${c.duplicate_of ? `<div class="callout yellow"><span class="ic">⧉</span><div>Same UTR as <a href="#" data-goto="${esc(c.duplicate_of)}">${esc(c.duplicate_of)}</a>. Probably the same debit reported again, so it is not counted as a new victim.</div></div>` : ''}
    <div class="props">
      ${prop('Status', `<span class="badge ${c.status === 'closed' ? '' : c.status === 'filed' ? 'info' : 'ok'}">${esc(c.status.replace('_', ' '))}</span>`)}
      ${prop('Priority', `<b>${s.score}</b> <span class="muted" style="font-size:13px">${esc(parts)}</span>`)}
      ${prop('Money went to', susList.length ? susList.map(([k, v]) => `<span class="muted">${k}</span> <span class="mono">${esc(v)}</span>`).join('&nbsp;&nbsp;') +
        (sus.status === 'confirmed' ? ' <span class="badge ok">Read back</span>' : '') +
        (sus.spell_check ? ' <span class="badge danger">Spelling unconfirmed</span>' : sus.spelled_by_caller ? ' <span class="badge ok">Spelled by caller</span>' : '') : '<span class="nil">Empty</span>')}
      ${prop('Mule ring', c.cluster && c.cluster.is_ring ? `<span class="badge ring">${esc(c.cluster.cluster_id)}</span> ${c.cluster.size} victims, ${inr(c.cluster.total_amount)} in total` : '<span class="nil">Not linked</span>')}
      ${prop('Victim’s bank', esc(c.victim_bank || '—'))}
      ${prop('Portal category', esc(c.ncrp_subcategory))}
      ${prop('Caller', `${c.caller_number ? `<span class="mono">${esc(c.caller_number)}</span>` : ''} ${verTag(c.verification) || '<span class="nil">Unverified</span>'}`)}
    </div>
    <div class="callout"><span class="ic">✎</span><div>${esc(c.summary || c.narrative || '—')} <span class="muted" style="font-size:12.5px">Summary by ${esc(c.summary_source === 'rules' ? 'rules' : c.summary_source)}</span></div></div>
    <h2>Payments</h2>
    <table class="tx"><tr><th>#</th><th>Amount</th><th>Debited at</th><th>Mode</th><th>UTR / RRN</th></tr>${rows}</table>
    <div class="actions">
      <button class="btn primary" id="actFreeze">Mark freeze request sent</button>
      <button class="btn" id="actCopy">Copy draft</button>
      <button class="btn ghost" id="actClose">Close case</button>
    </div>
    <div class="tabs" role="tablist">${TABS.map(([k, l]) => `<div class="tab ${TAB === k ? 'on' : ''}" data-t="${k}" role="tab" tabindex="0">${l}</div>`).join('')}</div>
    ${TAB === 'transcript'
      ? `<div class="transcript">${c.transcript.map(t => `<div class="t ${t.role}"><b>${t.role === 'caller' ? 'Caller' : 'Saathi'}</b>${esc(t.text)}</div>`).join('')}</div>`
      : TAB === 'audit'
      ? `<pre class="draft">${esc((c.audit || []).map(a => `${a.ts}  ${a.actor.padEnd(10)}  ${a.action}  ${a.detail || ''}`).join('\n') || 'No entries')}</pre>`
      : `<pre class="draft" id="draft">${esc(drafts[TAB])}</pre>`}
  `;
  $('detail').querySelectorAll('.tab').forEach(t => { t.onclick = () => { TAB = t.dataset.t; renderDetail(); }; t.onkeydown = e => { if (e.key === 'Enter') t.click(); }; });
  $('detail').querySelectorAll('[data-goto]').forEach(a => a.onclick = e => { e.preventDefault(); select(a.dataset.goto); });
  $('actFreeze').onclick = () => act('freeze_requested');
  $('actClose').onclick = () => act('closed');
  $('actCopy').onclick = () => { navigator.clipboard && navigator.clipboard.writeText(TAB === 'transcript' ? '' : drafts[TAB]); $('actCopy').textContent = 'Copied'; };
  tick();
}

async function act(action) {
  DETAIL = await api(`/api/cases/${SELECTED}/action`, { action });
  renderDetail(); loadQueue();
}

async function loadRings() {
  const { clusters } = await api('/api/clusters');
  const rings = clusters.filter(c => c.is_ring);
  $('rings').innerHTML = rings.length ? rings.map(r => `<div class="ringrow"><span class="badge ring">${esc(r.cluster_id)}</span>
     <b>${r.size} victims</b>${r.reports > r.size ? ` <span class="muted">(${r.reports} reports)</span>` : ''}, ${inr(r.total_amount)}${r.live_threat ? ' <span class="badge danger">Live threat</span>' : ''}
     <div class="id">${esc(r.identifiers.join(', '))}</div></div>`).join('')
    : '<div class="muted" style="font-size:13.5px">No shared fraudster identifiers yet.</div>';
  drawGraph(clusters);
}

function drawGraph(clusters) {
  const svg = $('graph'); const W = 320, H = 220;
  const ORANGE = '#d9730d', LINE = 'rgba(55,53,47,.18)', GREY = '#9b9a97', DARK = '#37352f';
  const nodes = [], links = [];
  clusters.slice(0, 6).forEach((cl, ci) => {
    const cx = 56 + (ci % 3) * 104, cy = 62 + Math.floor(ci / 3) * 100;
    cl.identifiers.forEach((idn, k) => nodes.push({ id: idn, x: cx + (k * 16), y: cy, kind: 'id', ring: cl.is_ring, label: idn.split(':')[1] }));
    cl.cases.forEach((cid, k) => {
      const ang = (2 * Math.PI * k) / Math.max(cl.cases.length, 1) - Math.PI / 2;
      const r = cl.cases.length > 1 ? 36 : 26;
      nodes.push({ id: cid, x: cx + r * Math.cos(ang), y: cy + r * Math.sin(ang), kind: 'case', ring: cl.is_ring, sel: cid === SELECTED });
      cl.identifiers.forEach(idn => links.push([cid, idn, cl.is_ring]));
    });
  });
  const pos = Object.fromEntries(nodes.map(n => [n.id, n]));
  svg.innerHTML = links.map(([a, b, ring]) => `<line x1="${pos[a].x}" y1="${pos[a].y}" x2="${pos[b].x}" y2="${pos[b].y}" stroke="${ring ? ORANGE : LINE}" stroke-width="${ring ? 1.5 : 1}"/>`).join('') +
    nodes.map(n => n.kind === 'id'
      ? `<rect x="${n.x - 6}" y="${n.y - 6}" width="12" height="12" rx="2" fill="${n.ring ? ORANGE : GREY}"><title>${esc(n.label)}</title></rect>`
      : `<circle cx="${n.x}" cy="${n.y}" r="${n.sel ? 7.5 : 6}" fill="${n.sel ? DARK : '#fff'}" stroke="${DARK}" stroke-width="1.5" style="cursor:pointer" data-id="${esc(n.id)}"><title>${esc(n.id)}</title></circle>`).join('') +
    (nodes.length ? '' : `<text x="${W / 2}" y="${H / 2}" fill="${GREY}" font-size="12" text-anchor="middle">No complaints yet</text>`) +
    `<text x="10" y="${H - 10}" fill="${GREY}" font-size="10.5">○ complaint   ■ fraudster UPI, mobile or account</text>`;
  svg.querySelectorAll('circle[data-id]').forEach(c => c.onclick = () => select(c.dataset.id));
}

function feed(text, cls = '') {
  const box = $('feed');
  if (box.querySelector('.muted')) box.innerHTML = '';
  const d = document.createElement('div'); d.className = 'ev ' + cls;
  d.innerHTML = `<span class="t">${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>${esc(text)}`; box.prepend(d);
}

function toast(text, cls = '') {
  const t = $('toast'); t.textContent = text; t.className = 'toast ' + cls; t.style.display = 'block';
  clearTimeout(t._h); t._h = setTimeout(() => t.style.display = 'none', 6000);
}

function connect() {
  const es = new EventSource('/api/events');
  es.addEventListener('call_started', e => { feed('Incoming call ' + JSON.parse(e.data).case_id); loadQueue(); });
  es.addEventListener('live_threat', e => { const d = JSON.parse(e.data); feed('Live threat on ' + d.case_id, 'danger'); toast('Live threat: caller is still in contact with the fraudster (' + d.case_id + ')', 'danger'); loadQueue(); });
  es.addEventListener('case_filed', e => { const d = JSON.parse(e.data); feed('Complaint filed ' + d.case_id); loadQueue(); loadRings(); loadSide(); if (d.case_id === SELECTED) select(SELECTED); });
  es.addEventListener('mule_ring', e => { const d = JSON.parse(e.data); feed(`${d.cluster.cluster_id}: ${d.cluster.size} victims share ${d.cluster.identifiers.join(', ')}`, 'ring'); if (SELECTED && d.cluster.cases.includes(SELECTED)) select(SELECTED); toast(`${d.cluster.cluster_id} now has ${d.cluster.size} victims, ${inr(d.cluster.total_amount)} in total`, 'ring'); });
  es.addEventListener('readback_correction', e => feed('Read-back corrected ' + JSON.parse(e.data).field + ' on ' + JSON.parse(e.data).case_id, 'warn'));
  es.addEventListener('validator_reprompt', e => feed('UTR re-asked on ' + JSON.parse(e.data).case_id + ' (wrong digit count)', 'warn'));
  es.addEventListener('call_turn', () => loadQueue());
  es.addEventListener('case_updated', () => loadQueue());
  es.addEventListener('seeded', e => { feed('Loaded ' + JSON.parse(e.data).count + ' demo complaints'); loadQueue(); loadRings(); if (SELECTED) select(SELECTED); });
  es.onerror = () => { es.close(); setTimeout(connect, 3000); };
}

$('seedBtn').onclick = async () => { $('seedBtn').disabled = true; await api('/api/demo/seed', {}); $('seedBtn').disabled = false; };
$('logoutBtn').onclick = async () => { await api('/api/logout', {}); location.href = '/login.html'; };

async function loadSide() {
  try {
    const ob = await api('/api/outbox');
    $('outbox').innerHTML = ob.outbox.length ? ob.outbox.map(m => `<div class="ev"><span class="mono" style="font-size:12px">${esc(m.to_number || '—')}</span> <span class="muted" style="font-size:12px">${esc(m.case_id || '')}</span><div>${esc(m.body)}</div></div>`).join('')
      : '<div class="muted">No messages yet.</div>';
    const fb = await api('/api/feedback');
    const roles = Object.entries(fb.by_role).map(([r, v]) => `${esc(r)}: ${v.avg_rating}★ from ${v.count}`).join(', ');
    $('feedback').innerHTML = roles ? roles + '<br>' + fb.recent.slice(0, 5).map(f => `“${esc(f.comment || '')}” ${f.rating}★`).join('<br>') : 'No feedback yet.';
  } catch (e) { /* ignore */ }
}
api('/api/me').then(m => { $('who').textContent = m.user ? m.user.username : ''; }).catch(() => {});
loadSide(); setInterval(loadSide, 10000);

showModes($('modes'));
loadQueue(); loadRings(); connect();
setInterval(tick, 1000);
setInterval(loadQueue, 15000);
