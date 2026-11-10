// Caller simulator: talks to /api/calls, plays Gnani Timbre audio (or a labelled browser voice in mock mode).
const $ = id => document.getElementById(id);
let callId = null, lang = 'hi', busy = false, health = null, callStart = 0, timerInt = null, goldenDeadline = null;
const rec = new WavRecorder();

const SCENARIOS = {
  'Digital arrest, still on video call (Hinglish)': [
    'CBI wale video call pe hain, bol rahe hain mere naam pe parcel mein drugs mile, abhi bhi video call chal raha hai',
    'do lakh rupaye bhej diye',
    'aadha ghanta pehle',
    'net banking se',
    'chaar ek do teen paanch chhe saat aath nau shunya ek do',
    'haan',
    'account number 5 0 1 0 0 2 3 4 5 6 7 8 9 hai',
    'haan',
    'punjab national bank',
    'nahi',
    'haan sahi hai',
  ],
  'KYC call, UTR said with a missing digit (validator demo)': [
    'bank wala bankar call aaya, KYC update ke liye OTP manga, maine bata diya',
    'nahi, call kat gaya',
    'pachpan hazaar',
    'bees minute pehle',
    'phonepe se',
    '7 7 1 2 0 4 5 5 3 9 0',
    '7 7 1 2, 0 4 5 5, 3 9 0 7',
    'haan sahi',
    'kycupdate dot help at the rate ybl',
    'haan',
    'SBI',
    'nahi',
    'haan',
  ],
  'Read-back correction: caller fixes the fraudster ID': [
    'OLX pe QR code scan karwaya, paise receive karne ke bahane',
    'saade teen hazaar',
    'das minute pehle',
    '9 0 0 1 2 3 4 5 6 7 8 8',
    'haan',
    'uska number 99999 00001 hai',
    'nahi, number 99999 00002 hai',
    'haan',
    'punjab and sind bank',
    'nahi',
    'haan',
  ],
  'Punjabi caller (Gurmukhi), spelled UPI name': [
    'ਬੈਂਕ ਵਾਲਾ ਬਣਕੇ ਕਾਲ ਆਈ, ਕੇਵਾਈਸੀ ਲਈ ਓਟੀਪੀ ਮੰਗਿਆ',
    'ਨਹੀਂ',
    'ਪੰਤਾਲੀ ਹਜ਼ਾਰ',
    'ਵੀਹ ਮਿੰਟ ਪਹਿਲਾਂ',
    'ਯੂਪੀਆਈ',
    'ਚਾਰ ਇੱਕ ਦੋ ਤਿੰਨ ਪੰਜ ਛੇ ਸੱਤ ਅੱਠ ਨੌਂ ਸਿਫ਼ਰ ਇੱਕ ਦੋ',
    'ਹਾਂ ਜੀ',
    'ਗੁਰਪ੍ਰੀਤ ਐਟ ਦ ਰੇਟ ਪੇਟੀਐਮ',
    'ਨਹੀਂ',
    'ਜੀ, ਯੂ, ਆਰ, ਪੀ, ਆਰ, ਈ, ਈ, ਟੀ',
    'ਹਾਂ ਜੀ',
    'ਪੰਜਾਬ ਨੈਸ਼ਨਲ ਬੈਂਕ',
    'ਨਹੀਂ',
    'ਹਾਂ ਜੀ ਸਹੀ ਹੈ',
  ],
  'Tamil caller (Tamil script)': [
    'பேங்க்ல இருந்து கால் பண்ணாங்க, கேஒய்சி அப்டேட்னு ஓடிபி கேட்டாங்க',
    'இல்லை',
    'நாற்பது ஆயிரம்',
    '20 நிமிஷம் முன்னாடி',
    'ஜிபே',
    'நான்கு ஒன்று இரண்டு மூன்று ஐந்து ஆறு ஏழு எட்டு ஒன்பது பூஜ்யம் ஒன்று இரண்டு',
    'ஆமா',
    'ஆர் கே அட் த ரேட் ஓகேஆக்சிஸ்',
    'ஆமா',
    'இந்தியன் ஓவர்சீஸ் பேங்க்',
    'இல்லை',
    'ஆமா சரி',
  ],
  'English caller, fake customer care': [
    'I searched customer care number on Google for a refund and they made me pay',
    'forty five thousand rupees',
    'about 40 minutes ago',
    'UPI',
    '4 1 2 3 5 6 7 8 9 0 1 2',
    'yes',
    'refund dot desk at the rate okaxis',
    'yes',
    'HDFC',
    'no',
    'yes',
  ],
};

function addBubble(cls, text, meta) {
  const d = document.createElement('div');
  d.className = 'bubble ' + cls;
  d.innerHTML = esc(text) + (meta ? `<span class="meta">${esc(meta)}</span>` : '');
  $('chat').appendChild(d);
  $('chat').scrollTop = $('chat').scrollHeight;
}

function addEvent(text, cls = '') {
  const box = $('events');
  if (box.querySelector('.muted')) box.innerHTML = '';
  const d = document.createElement('div');
  d.className = 'ev ' + cls;
  d.innerHTML = `<span class="t">${fmtClock(Date.now() - callStart)}</span>${esc(text)}`;
  box.prepend(d);
}

function setEnabled(on) {
  ['micBtn', 'textIn', 'sendBtn', 'hangBtn'].forEach(id => $(id).disabled = !on);
  $('callBtn').disabled = on;
  $('status').classList.toggle('on', on);
  $('statusText').textContent = on ? 'On call with 1930 Saathi' : 'Not connected';
}

async function speak(res) {
  if (!$('voiceOn').checked) return;
  if (res.audio_b64) return playWav(res.audio_b64);
  return speakFallback(res.reply, lang);
}

function renderSlots(c) {
  if (!c) return;
  lang = c.lang || lang;
  $('caseId').textContent = c.id;
  const known = c.fraud_type && c.fraud_type !== 'other';
  $('caseTitle').textContent = known ? c.fraud_label : 'New complaint';
  const st = s => ({ confirmed: ['ok', 'Read back'], captured: ['ok', 'Captured'], pending_confirm: ['warn', 'Confirming'],
    unknown: ['purple', 'Caller doesn’t know'], missing: ['', 'Waiting'] }[s] || ['', s]);
  const tx = c.transactions[c.transactions.length - 1];
  const sus = c.suspect.upi || c.suspect.mobile || c.suspect.account;
  const when = tx.minutes_ago == null ? '' : tx.minutes_ago < 60 ? `${tx.minutes_ago} min ago` : `${Math.round(tx.minutes_ago / 6) / 10} h ago`;
  const cells = [
    ['Fraud pattern', known ? c.fraud_label : '', known ? 'captured' : 'missing'],
    ['Amount' + (c.transactions.length > 1 ? ` (payment ${c.transactions.length})` : ''), tx.amount ? inr(tx.amount) : '', tx.amount_status],
    ['When', when, tx.time_status],
    ['Payment mode', tx.mode || '', tx.mode_status],
    ['UTR / reference', tx.utr || '', tx.utr_status, true],
    ['Money went to', sus || '', c.suspect.status, true],
    ['Victim’s bank', c.victim_bank || '', c.bank_status],
    ['Scam still going on?', c.live_threat ? 'Yes, safety advice given first' : (c.threat_checked ? 'No' : ''),
      c.threat_checked || c.live_threat ? 'captured' : 'missing'],
  ];
  $('slots').innerHTML = cells.map(([k, v, s, mono]) => {
    const [cls, lab] = st(s);
    const danger = k.startsWith('Scam') && c.live_threat;
    return `<div class="k">${esc(k)}</div><div class="v">${v ? `<span class="${mono ? 'mono' : ''}">${esc(v)}</span>` : '<span class="nil">Empty</span>'}
      <span class="badge ${danger ? 'danger' : cls}">${esc(danger ? 'Live threat' : lab)}</span></div>`;
  }).join('');
  if (c.golden_deadline) {
    goldenDeadline = new Date(c.golden_deadline).getTime();
    $('goldenNote').textContent = 'Golden window left';
  }
}

function tickGolden() {
  if (!goldenDeadline) return;
  const left = goldenDeadline - serverNow();
  const el = $('goldenClock');
  el.textContent = fmtClock(left);
  el.className = 'clock ' + (left < 0 ? 'late' : left < 30 * 60000 ? 'warn' : '');
}

function handleEvents(evs) {
  for (const e of evs || []) {
    if (e.type === 'live_threat') addEvent('Scam still in progress (' + (e.cues || []).join(', ') + '). Gave safety instructions before any questions.', 'danger');
    else if (e.type === 'validator_reprompt') addEvent(`Heard ${e.heard_digits} digits for the UTR, a UTR has 12. Asked again.`, 'warn');
    else if (e.type === 'readback_correction') addEvent(`Read-back caught a wrong ${e.field.toUpperCase()}. Caller corrected it.`, 'warn');
    else if (e.type === 'summary_correction') addEvent(`Caller corrected ${e.field} in the final summary.`, 'warn');
    else if (e.type === 'new_transaction') addEvent(`Added payment ${e.index}.`, '');
    else if (e.type === 'case_filed') addEvent('Complaint filed. Sent to the officer queue with a bank freeze draft and an SMS.', '');
    else if (e.type === 'spelled_upi') addEvent('Caller spelled the UPI name letter by letter: ' + e.value, 'warn');
    else if (e.type === 'llm_fallback') addEvent('Evon filled ' + e.field + ' where the rules could not. Checked in code.', '');
  }
}

async function startCall() {
  busy = true;
  try {
    const res = await api('/api/calls', { lang: $('langSel').value || null, caller_number: $('callerNo').value || null });
    callId = res.call_id; goldenDeadline = null; $('goldenClock').textContent = '—'; $('goldenNote').textContent = 'Golden window starts when the caller says when money left';
    $('chat').innerHTML = ''; $('events').innerHTML = '<div class="muted">Waiting for the caller…</div>';
    setEnabled(true);
    callStart = Date.now();
    clearInterval(timerInt);
    timerInt = setInterval(() => { $('callTimer').textContent = fmtClock(Date.now() - callStart); tickGolden(); }, 500);
    addBubble('agent', res.reply, res.tts_provider === 'mock' ? 'Browser preview voice (mock mode)' : 'Gnani Timbre');
    $('caseId').textContent = callId;
    renderSlots(res.case);
    await speak(res);
  } catch (e) { addBubble('alert', 'Could not start the call: ' + e.message); }
  busy = false;
}

async function sendTurn(payload, shownText) {
  if (!callId || busy) return;
  busy = true;
  if (shownText) addBubble('caller', shownText, payload.audio_b64 ? 'voice' : 'typed');
  try {
    const res = await api(`/api/calls/${callId}/turn`, payload);
    if (payload.audio_b64) {
      if (res.stt_error && !res.reply) {
        addBubble('alert', res.stt_error);
        busy = false; return;
      }
      addBubble('caller', res.heard || '(nothing heard)', `${res.stt_provider}, ${res.stt_ms} ms`);
    }
    if (res.reply) {
      const meta = (res.tts_provider === 'mock' ? 'Browser preview voice (mock mode)' : `Gnani Timbre, ${res.tts_ms} ms`) + `, engine ${res.nlu_ms} ms`;
      addBubble('agent', res.reply, meta);
    }
    handleEvents(res.events);
    renderSlots(res.case);
    await speak(res);
    if (res.done) {
      addBubble('system', 'Call complete. The case is now in the officer console.');
      if (res.case && res.case.caller_number) {
        const d = document.createElement('div'); d.className = 'bubble system';
        d.innerHTML = `An SMS with a confirmation code went to the caller (see the console's SMS outbox). <a href="/verify.html?case=${esc(res.case.id)}" target="_blank">Confirm complaint</a>`;
        $('chat').appendChild(d);
      }
      setEnabled(false); clearInterval(timerInt);
    }
  } catch (e) { addBubble('alert', 'Error: ' + e.message); }
  busy = false;
}

$('callBtn').onclick = startCall;
$('hangBtn').onclick = () => { setEnabled(false); clearInterval(timerInt); addBubble('system', 'Caller hung up.'); callId = null; };
$('sendBtn').onclick = () => { const t = $('textIn').value.trim(); if (!t) return; $('textIn').value = ''; sendTurn({ text: t }, t); };
$('textIn').addEventListener('keydown', e => { if (e.key === 'Enter') $('sendBtn').click(); });

const startRec = async e => {
  e.preventDefault();
  if (!callId || busy || rec.recording) return;
  try { await rec.start(); $('micBtn').classList.add('rec'); }
  catch (err) { addBubble('alert', 'Microphone not available: ' + err.message); }
};
const stopRec = async e => {
  e.preventDefault();
  if (!rec.recording) return;
  $('micBtn').classList.remove('rec');
  const { b64, seconds } = await rec.stop($('phoneMode').checked ? 8000 : 16000);
  if (seconds < 0.4) return;
  if (health && health.mock) {
    addBubble('alert', 'Mock mode: no speech recognition without a Gnani API key. Type the words instead, or add GNANI_API_KEY to .env.');
    return;
  }
  sendTurn({ audio_b64: b64 }, null);
};
$('micBtn').addEventListener('pointerdown', startRec);
$('micBtn').addEventListener('pointerup', stopRec);
$('micBtn').addEventListener('pointerleave', stopRec);

// demo scripts
const sel = $('scenario');
Object.keys(SCENARIOS).forEach(k => { const o = document.createElement('option'); o.textContent = k; sel.appendChild(o); });
function renderChips() {
  $('chips').innerHTML = SCENARIOS[sel.value].map((l, i) => `<button class="chip" data-i="${i}">${esc(l)}</button>`).join('');
  $('chips').querySelectorAll('.chip').forEach(b => b.onclick = () => { if (callId) sendTurn({ text: b.textContent }, b.textContent); });
}
sel.onchange = renderChips; renderChips();

$('autoBtn').onclick = async () => {
  $('autoBtn').disabled = true; $('autoBtn').textContent = 'Playing…';
  await startCall();
  for (const line of SCENARIOS[sel.value]) {
    if (!callId) break;
    await new Promise(r => setTimeout(r, 700));
    while (busy) await new Promise(r => setTimeout(r, 100));
    await sendTurn({ text: line }, line);
  }
  $('autoBtn').disabled = false; $('autoBtn').textContent = 'Play script';
};

showModes($('modes')).then(h => { health = h; });
