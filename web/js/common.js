// Shared helpers for the 1930 Saathi web UI.
async function api(path, body) {
  const opt = body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
  };
  const r = await fetch(path, opt);
  const data = await r.json().catch(() => ({}));
  if (r.status === 401 && location.pathname === '/console.html') {
    location.href = '/login.html?next=/console.html';
    throw new Error('login required');
  }
  if (!r.ok) throw new Error(data.error || ('HTTP ' + r.status));
  return data;
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function inr(n) {
  if (n === null || n === undefined) return '—';
  return '₹' + Number(n).toLocaleString('en-IN');
}

function fmtClock(ms) {
  const neg = ms < 0; ms = Math.abs(ms);
  const s = Math.floor(ms / 1000), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const t = (h ? h + ':' : '') + String(m).padStart(h ? 2 : 1, '0') + ':' + String(sec).padStart(2, '0');
  return (neg ? '−' : '') + t;
}

// server timestamps are naive local ISO strings; keep a clock offset so countdowns use server time
let SERVER_OFFSET = 0;
function syncClock(serverIso) {
  if (!serverIso) return;
  SERVER_OFFSET = new Date(serverIso).getTime() - Date.now();
}
function serverNow() { return Date.now() + SERVER_OFFSET; }

async function showModes(el) {
  try {
    const h = await api('/api/health');
    syncClock(h.time);
    const b = (txt, cls) => `<span class="badge ${cls}">${esc(txt)}</span>`;
    el.innerHTML = [
      b('STT: ' + h.stt, h.stt === 'mock' ? 'mock' : 'live'),
      b('TTS: ' + h.tts, h.tts === 'mock' ? 'mock' : 'live'),
      b('LLM: ' + h.llm, h.llm === 'rules' ? '' : 'live'),
      b('SMS: ' + (h.sms || '?'), ''),
      b('synthetic data', ''),
    ].join('');
    return h;
  } catch (e) {
    el.innerHTML = '<span class="badge danger">server offline</span>';
  }
}

function speakFallback(text, lang) {
  // Mock-mode preview only: the browser's own voice, clearly not Gnani Timbre.
  return new Promise(resolve => {
    if (!('speechSynthesis' in window)) return resolve();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang === 'en' ? 'en-IN' : 'hi-IN';
    u.rate = 1.05;
    u.onend = resolve; u.onerror = resolve;
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
  });
}

function playWav(b64) {
  return new Promise(resolve => {
    const a = new Audio('data:audio/wav;base64,' + b64);
    a.onended = resolve; a.onerror = resolve;
    a.play().catch(resolve);
  });
}
