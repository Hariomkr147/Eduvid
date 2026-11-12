// Shared bits for the studio pages: API calls, the NCE header, toasts, small formatters.
export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export async function api(path, opts = {}) {
  const r = await fetch('/studio/api' + path, {
    method: opts.method || (opts.body ? 'POST' : 'GET'),
    headers: opts.body ? { 'Content-Type': 'application/json' } : {},
    body: opts.body ? JSON.stringify(opts.body) : undefined, credentials: 'same-origin',
  });
  if (r.status === 401 && !path.startsWith('/login')) { location.href = '/studio/login?next=' + encodeURIComponent(location.pathname + location.search); throw new Error('login required'); }
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail || j); } catch {}
    const e = new Error(msg); e.status = r.status; throw e;
  }
  const ct = r.headers.get('content-type') || '';
  return ct.includes('json') ? r.json() : r;
}

export function header(active) {
  const wrap = document.createElement('div');
  wrap.className = 'hwrap' + (active === 'new' ? '' : ' wide');
  const el = document.createElement('header');
  el.className = 'top';
  wrap.append(el);
  el.innerHTML = `
    <div class="brand">
      <a class="logo" href="/studio/" aria-label="EduVid Studio home">EV</a>
      <h1>EduVid Studio</h1><span class="pill badge">Video Factory</span>
    </div>
    <nav class="links" aria-label="Studio">
      <a href="/studio/" ${active === 'new' ? 'aria-current="page"' : ''}>New video</a>
      <a href="/studio/library" ${active === 'library' ? 'aria-current="page"' : ''}>Library</a>
      <a href="/studio/compare" ${active === 'compare' ? 'aria-current="page"' : ''}>Compare</a>
      <span class="sp"></span>
      <button class="linkish" id="logout" type="button">Log out</button>
    </nav>`;
  el.querySelector('#logout').onclick = async () => { await api('/logout', { body: {} }); location.href = '/studio/login'; };
  return wrap;
}

let toastT;
export function toast(msg) {
  let t = $('.toast');
  if (!t) { t = document.createElement('div'); t.className = 'toast'; t.setAttribute('role', 'status'); document.body.append(t); }
  t.textContent = msg; t.hidden = false;
  clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, 3200);
}

export const money = (x) => (x == null ? '—' : x < 0.01 && x > 0 ? '<$0.01' : '$' + x.toFixed(x < 1 ? 3 : 2));
export const inr = (x) => '₹' + Math.round(x * 85).toLocaleString('en-IN');
export const mmss = (s) => { s = Math.max(0, Math.round(s || 0)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
export const ago = (iso) => { const d = (Date.now() - new Date(iso)) / 1000; if (d < 60) return 'just now'; if (d < 3600) return `${Math.floor(d / 60)} min ago`; if (d < 86400) return `${Math.floor(d / 3600)} h ago`; return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }); };

export const STATUS = {
  scripting: ['Writing script', 'info'], review: ['Script ready for review', 'gold'], voicing: ['Recording voice', 'info'],
  timing: ['Timing words', 'info'], coding: ['Writing animation', 'info'], rendering: ['Rendering', 'info'],
  publishing: ['Publishing', 'info'], done: ['Ready', 'ok'], failed: ['Failed', 'bad'],
};
export const statusPill = (s) => { const [t, c] = STATUS[s] || [s, 'mute']; return `<span class="pill ${c}">${esc(t)}</span>`; };
export const MODE = { template: 'Design templates', llm: 'LLM animation' };

export function drawer(title, html) {
  let d = $('dialog.drawer');
  if (!d) {
    d = document.createElement('dialog'); d.className = 'drawer';
    d.innerHTML = '<div class="dhead"><strong></strong><button class="btn small" type="button">Close</button></div><div class="dbody"></div>';
    d.querySelector('button').onclick = () => d.close();
    d.addEventListener('click', (e) => { if (e.target === d) d.close(); });
    document.body.append(d);
  }
  d.querySelector('strong').textContent = title;
  d.querySelector('.dbody').innerHTML = html;
  d.showModal();
  return d;
}
