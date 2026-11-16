import { $, $$, esc, api, header, toast, money, mmss, ago, statusPill, MODE } from './common.js';

document.querySelector('#page').before(header('library'));
let all = [];
const WORK = ['scripting', 'review', 'voicing', 'timing', 'coding', 'rendering', 'publishing'];

let lastData = '', lastHtml = '';
async function load() {
  const data = await api('/videos');
  const key = JSON.stringify(data);
  if (key !== lastData) { all = data; lastData = key; render(); }   // nothing changed: leave the cards alone
  if (all.some((v) => WORK.includes(v.status) && v.status !== 'review')) setTimeout(load, 5000);
}
function render() {
  const q = $('#q').value.trim().toLowerCase(), f = $('input[name=f]:checked').value;
  const list = all.filter((v) => (f === 'all' || (f === 'work' ? WORK.includes(v.status) : v.status === f))
    && (!q || [v.title, v.model, v.target?.chapter, v.target?.label, v.target?.subject].join(' ').toLowerCase().includes(q)));
  if (!list.length) {
    $('#lib').innerHTML = `<div class="empty" style="grid-column:1/-1"><img src="/studio/static/nce/assets/bk-calm.png" alt=""><p>${all.length ? 'No video matches.' : 'No videos yet. Make your first one!'}</p><a class="btn primary" href="/studio/">+ New video</a></div>`;
    return;
  }
  const html = list.map((v) => {
    const ready = (v.variants || []).filter((x) => x.status === 'done'), first = ready[0];
    const thumb = first ? `<img src="/studio/media/${v.id}/${first.mode}/poster.jpg" alt="" loading="lazy">` : `<span class="ph">${esc((v.settings?.aspect) || '16:9')}</span>`;
    const pair = v.compare_id ? all.filter((x) => x.compare_id === v.compare_id) : [];
    return `<article class="vcard">
      <a class="thumb" href="${first ? `/studio/watch/${v.id}` : `/studio/?v=${v.id}`}" aria-label="${esc(v.title)}">${thumb}<span class="st">${statusPill(v.status)}</span>${v.duration_s ? `<span class="dur">${mmss(v.duration_s)}</span>` : ''}</a>
      <div class="meta"><strong>${esc(v.title || v.target?.label || 'Untitled')}</strong>
        <small>${esc([v.target?.grade && `Class ${v.target.grade}`, v.target?.subject, v.target?.chapter].filter(Boolean).join(' · ') || 'Pasted material')}</small>
        <div class="row"><span class="pill info">${esc(v.model.split('/').pop())}</span>${(v.variants?.length ? v.variants.map((x) => x.mode) : [v.settings?.mode]).map((m) => `<span class="pill badge">${esc(MODE[m] || (m === 'both' ? 'Both' : m))}</span>`).join('')}<span class="pill cost">${money(v.cost_usd)}</span></div>
        <small>${ago(v.created_at)}</small></div>
      <div class="acts">${first ? `<a class="btn small primary" href="/studio/watch/${v.id}">Watch</a>` : ''}<a class="btn small" href="/studio/?v=${v.id}">${v.status === 'review' ? 'Review script' : 'Open'}</a>
        ${ready.length > 1 ? `<a class="btn small" href="/studio/compare?v=${v.id}">Compare modes</a>` : ''}${pair.length > 1 ? `<a class="btn small" href="/studio/compare?group=${v.compare_id}">Compare models</a>` : ''}
        <button class="btn small ghost danger" type="button" data-del="${v.id}">Delete</button></div></article>`;
  }).join('');
  if (html === lastHtml) return;
  lastHtml = html;
  $('#lib').innerHTML = html;
  requestAnimationFrame(() => $('#lib').classList.add('ready'));   // fade cards in once, not on every refresh
}
$('#q').oninput = render;
$$('input[name=f]').forEach((r) => r.onchange = render);
$('#lib').onclick = async (e) => {
  const b = e.target.closest('[data-del]'); if (!b) return;
  if (!confirm('Delete this video from the library?')) return;
  await api('/videos/' + b.dataset.del, { method: 'DELETE' }); toast('Deleted.'); load();
};
load();
