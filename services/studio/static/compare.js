import { $, esc, api, header, money, mmss, MODE } from './common.js';

document.querySelector('#page').before(header('compare'));
const qs = new URLSearchParams(location.search);
let opts = [];

async function init() {
  const vids = (await api('/videos')).filter((v) => (v.variants || []).some((x) => x.status === 'done'));
  opts = vids.flatMap((v) => v.variants.filter((x) => x.status === 'done').map((x) => ({ key: `${v.id}|${x.mode}`, v, mode: x.mode,
    label: `${v.title || 'Untitled'} · ${MODE[x.mode]} · ${v.model.split('/').pop()}` })));
  const html = opts.map((o) => `<option value="${o.key}">${esc(o.label)}</option>`).join('');
  $('#a').innerHTML = html; $('#b').innerHTML = html;
  let a = opts[0]?.key, b = opts[1]?.key;
  if (qs.get('v')) { const m = opts.filter((o) => o.v.id === qs.get('v')); if (m[0]) a = m[0].key; if (m[1]) b = m[1].key; }
  if (qs.get('group')) { const m = opts.filter((o) => o.v.compare_id === qs.get('group')); if (m[0]) a = m[0].key; const o2 = m.find((o) => o.v.id !== m[0]?.v.id); if (o2) b = o2.key; }
  if (a) $('#a').value = a; if (b) $('#b').value = b;
  render();
}
function side(o, i) {
  if (!o) return '<div class="empty">Nothing to compare yet.</div>';
  const v = o.v;
  return `<div><div class="figure"><video id="v${i}" src="/studio/media/${v.id}/${o.mode}/video.mp4" poster="/studio/media/${v.id}/${o.mode}/poster.jpg" playsinline preload="metadata" ${i ? 'muted' : ''}></video></div>
    <dl class="facts" style="margin-top:12px"><dt>Visuals</dt><dd>${esc(MODE[o.mode])}</dd><dt>Model</dt><dd>${esc(v.model)}</dd><dt>Length</dt><dd>${mmss(v.duration_s)}</dd><dt>AI cost</dt><dd>${money(v.cost_usd)}</dd></dl>
    <div class="actions"><button class="btn small" type="button" data-snd="${i}">🔊 Sound from this side</button><a class="btn small ghost" href="/studio/watch/${v.id}?mode=${o.mode}">Open in player</a></div></div>`;
}
function render() {
  const A = opts.find((o) => o.key === $('#a').value), B = opts.find((o) => o.key === $('#b').value);
  $('#cmp').innerHTML = side(A, 0) + side(B, 1);
  const [v0, v1] = [$('#v0'), $('#v1')];
  if (!v0 || !v1) return;
  let lock = false;
  const sync = (src, dst) => { if (lock) return; lock = true; if (Math.abs(dst.currentTime - src.currentTime) > 0.25) dst.currentTime = src.currentTime; lock = false; };
  v0.addEventListener('seeked', () => sync(v0, v1)); v1.addEventListener('seeked', () => sync(v1, v0));
  v0.addEventListener('play', () => v1.play().catch(() => {})); v0.addEventListener('pause', () => v1.pause());
  v1.addEventListener('play', () => v0.play().catch(() => {})); v1.addEventListener('pause', () => v0.pause());
  $('#cmp').onclick = (e) => { const b = e.target.closest('[data-snd]'); if (!b) return; v0.muted = b.dataset.snd !== '0'; v1.muted = b.dataset.snd !== '1'; };
}
$('#a').onchange = render; $('#b').onchange = render;
$('#pp').onclick = () => { const v0 = $('#v0'); if (!v0) return; if (v0.paused) { v0.play(); $('#pp').textContent = '❚❚ Pause both'; } else { v0.pause(); $('#pp').textContent = '▶ Play both'; } };
$('#rw').onclick = () => { ['#v0', '#v1'].forEach((s) => { const v = $(s); if (v) v.currentTime = 0; }); };
init();
