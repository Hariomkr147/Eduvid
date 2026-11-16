// Builder: new-video form (cards 1-4) → script review (card 5) → build progress (card 6) → finished card.
import { $, $$, esc, api, header, toast, money, inr, mmss, statusPill, MODE, drawer } from './common.js';

const LS = 'eduvid:studio:v1';
const state = { books: [], chapters: [], sections: [], picked: new Map(), models: [], voices: [], m1: null, m2: null, m3: null };
const ACTIVE = ['scripting', 'voicing', 'timing', 'coding', 'rendering', 'publishing'];
const KIND_LBL = { title: 'Title', concept: 'Concept', board: 'Board', figure: 'Figure', example: 'Example', check: 'Pause-and-try', summary: 'Summary' };
const SAMPLE = { hinglish: 'नमस्ते दोस्तों! आज हम सिलेंडर का सरफेस एरिया समझेंगे।', hindi: 'नमस्ते बच्चों! आज हम बेलन का पृष्ठीय क्षेत्रफल समझेंगे।', english: 'Hello friends! Today we will learn the surface area of a cylinder.' };

document.querySelector('#page').before(header('new'));
const radio = (name) => $(`input[name=${name}]:checked`)?.value;
const setRadio = (name, v) => { const el = $(`input[name=${name}][value="${v}"]`); if (el) el.checked = true; };
const tip = (s) => { $('#bkTip').textContent = s; };

// ---------------- health ----------------
async function health() {
  try {
    const s = await api('/status');
    const chip = (ok, good, bad) => `<span class="pill ${ok ? 'ok' : 'warn'}">${ok ? '✓ ' + good : '! ' + bad}</span>`;
    const bal = s.balance_usd, low = bal != null && bal < 0.5;
    $('#health').innerHTML = chip(s.openrouter, 'OpenRouter connected', 'Add OPENROUTER_API_KEY to .env')
      + (bal != null ? `<span class="pill ${low ? 'bad' : 'ok'}">${low ? '! ' : ''}OpenRouter balance ${money(Math.max(0, bal))}${low ? ': add credits or use a :free model' : ''}</span>` : '')
      + chip(s.ncert, 'NCERT library', 'NCERT database unreachable') + chip(s.voices, 'Voices online', 'Speech API down');
    if (!s.openrouter) $('#goCap').textContent = 'Add OPENROUTER_API_KEY to /srv/eduvid/app/.env and restart studio to write scripts.';
  } catch (e) { /* login redirect handled in api() */ }
}

// ---------------- NCERT cascade ----------------
async function loadBooks() {
  try { state.books = await api('/ncert/books'); } catch (e) { $('#unitsCap').innerHTML = `<span class="err">${esc(e.message)}</span>`; return; }
  const grades = [...new Set(state.books.map((b) => b.grade))].sort((a, b) => a - b);
  $('#grade').innerHTML = '<option value="">Choose a class</option>' + grades.map((g) => `<option value="${g}">Class ${g}</option>`).join('');
  $('#pgrade').innerHTML = grades.map((g) => `<option value="${g}">Class ${g}</option>`).join('');
  const saved = load();
  if (saved.grade) { $('#grade').value = saved.grade; await onGrade(saved.book, saved.chapter); }
}
async function onGrade(bookId, chapterId) {
  const g = +$('#grade').value, books = state.books.filter((b) => b.grade === g);
  $('#book').innerHTML = '<option value="">Choose a book</option>' + books.map((b) => `<option value="${b.id}">${esc(b.subject)} · ${esc(b.title)}</option>`).join('');
  $('#book').disabled = !g; $('#chapter').disabled = true; $('#chapter').innerHTML = ''; $('#units').innerHTML = '';
  if (bookId && books.some((b) => b.id === bookId)) { $('#book').value = bookId; await onBook(chapterId); }
  summary();
}
async function onBook(chapterId) {
  const id = $('#book').value; $('#units').innerHTML = '';
  if (!id) { $('#chapter').disabled = true; return; }
  state.chapters = await api('/ncert/chapters?book=' + id);
  $('#chapter').innerHTML = '<option value="">Choose a chapter</option>' + state.chapters.map((c) => `<option value="${c.id}">Chapter ${c.number}: ${esc(c.title)} (${c.units} units)</option>`).join('');
  $('#chapter').disabled = false;
  if (chapterId && state.chapters.some((c) => c.id === chapterId)) { $('#chapter').value = chapterId; await onChapter(); }
  summary();
}
async function onChapter() {
  const id = $('#chapter').value; if (!id) { $('#units').innerHTML = ''; return; }
  $('#units').innerHTML = '<p class="cap">Loading teaching units…</p>';
  state.sections = await api('/ncert/sections?chapter=' + id);
  const tone = { easy: 'ok', medium: 'gold', hard: 'bad' };
  $('#units').innerHTML = state.sections.filter((s) => s.units.length).map((s) => `
    <div class="sec"><header><span class="mono">${esc(s.code || '')}</span> ${esc(s.name || '')}<span class="sp"></span>
      <button class="btn small ghost" type="button" data-all="${s.id}">Select all</button></header>
      ${s.units.map((u) => `<label class="unit"><input type="checkbox" value="${u.id}" ${state.picked.has(u.id) ? 'checked' : ''}>
        <span class="tx"><b>${esc(u.name)}</b><small>${esc(u.description || '')}</small>
        <span class="tags">${u.bloom ? `<span class="pill info">${esc(u.bloom)}</span>` : ''}${u.difficulty ? `<span class="pill ${tone[(u.difficulty || '').toLowerCase()] || 'mute'}">${esc(u.difficulty)}</span>` : ''}<span class="pill mute">${Math.round((u.context_chars || 0) / 1000)}k chars</span></span></span>
        <button class="btn small ghost" type="button" data-prev="${u.id}" aria-label="Read the NCERT text of ${esc(u.name)}">Read</button></label>`).join('')}
    </div>`).join('') || '<p class="cap">This chapter has no teaching units yet.</p>';
  tip('Tick the teaching units this video should teach. One to three units makes a 2–5 minute video.');
  summary();
}
$('#grade').onchange = () => onGrade(); $('#book').onchange = () => onBook(); $('#chapter').onchange = onChapter;
$('#units').addEventListener('change', (e) => {
  if (e.target.type !== 'checkbox') return;
  const u = state.sections.flatMap((s) => s.units).find((x) => x.id === e.target.value);
  if (e.target.checked) state.picked.set(u.id, u); else state.picked.delete(u.id);
  renderPicked();
});
$('#units').addEventListener('click', async (e) => {
  const all = e.target.closest('[data-all]'), pv = e.target.closest('[data-prev]');
  if (all) { e.preventDefault(); const s = state.sections.find((x) => x.id === all.dataset.all); s.units.forEach((u) => state.picked.set(u.id, u)); $$('#units input').forEach((i) => { i.checked = state.picked.has(i.value); }); renderPicked(); }
  if (pv) { e.preventDefault(); const u = await api('/ncert/unit/' + pv.dataset.prev); drawer(u.name, `<p class="cap">Class ${u.grade} · ${esc(u.subject)} · Chapter ${u.chapter_number}: ${esc(u.chapter)} · ${esc(u.section_code || '')} ${esc(u.section_name || '')}</p><pre>${esc(u.context)}</pre>`); }
});
function renderPicked() {
  $('#picked').innerHTML = [...state.picked.values()].map((u) => `<span>${esc(u.name)}<button type="button" data-rm="${u.id}" aria-label="Remove ${esc(u.name)}">×</button></span>`).join('');
  summary();
}
$('#picked').onclick = (e) => { const b = e.target.closest('[data-rm]'); if (!b) return; state.picked.delete(b.dataset.rm); $$('#units input').forEach((i) => { i.checked = state.picked.has(i.value); }); renderPicked(); };
$$('input[name=source]').forEach((r) => r.onchange = () => { const t = radio('source') === 'text'; $('#srcText').hidden = !t; $('#srcNcert').hidden = t; summary(); });

// ---------------- model pickers ----------------
const fmtP = (m) => `$${m.in_per_m.toFixed(2)} / $${m.out_per_m.toFixed(2)}`;
function picker(n, onPick) {
  const q = $('#mq' + n), list = $('#ml' + n);
  let hl = 0, shown = [];
  const render = () => {
    const s = q.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    shown = state.models.filter((m) => s.every((w) => (m.id + ' ' + m.name).toLowerCase().includes(w))).slice(0, 40);
    list.innerHTML = shown.map((m, i) => `<button type="button" role="option" class="opt ${i === hl ? 'hl' : ''}" data-i="${i}"><b>${esc(m.name)}</b><small>${esc(m.id)} · ${Math.round(m.context / 1000)}k context</small><span class="pr">${fmtP(m)}<br><small>per M tokens</small></span></button>`).join('') || '<p class="cap" style="padding:8px">No model matches.</p>';
    list.hidden = false; q.setAttribute('aria-expanded', 'true');
  };
  const choose = (m) => { list.hidden = true; q.setAttribute('aria-expanded', 'false'); q.value = ''; onPick(m); };
  q.addEventListener('focus', () => { hl = 0; render(); });
  q.addEventListener('input', () => { hl = 0; render(); });
  q.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { hl = Math.min(shown.length - 1, hl + 1); render(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { hl = Math.max(0, hl - 1); render(); e.preventDefault(); }
    else if (e.key === 'Enter') { if (shown[hl]) choose(shown[hl]); e.preventDefault(); }
    else if (e.key === 'Escape') { list.hidden = true; }
  });
  list.addEventListener('mousedown', (e) => { const b = e.target.closest('[data-i]'); if (b) { e.preventDefault(); choose(shown[+b.dataset.i]); } });
  q.addEventListener('blur', () => setTimeout(() => { list.hidden = true; q.setAttribute('aria-expanded', 'false'); }, 120));
}
function showChosen(n, m) {
  $('#mc' + n).innerHTML = m ? `<span class="pill info">${esc(m.name)}</span><span class="cap">${fmtP(m)} per M tokens · ${Math.round(m.context / 1000)}k context</span>${n > 1 ? `<button class="btn small ghost" type="button" data-clear="${n}">Clear</button>` : ''}` : '';
}
document.addEventListener('click', (e) => { const c = e.target.closest('[data-clear]'); if (c) { state['m' + c.dataset.clear] = null; showChosen(+c.dataset.clear, null); summary(); } });
async function loadModels() {
  try { state.models = await api('/models'); } catch (e) { $('#mc1').innerHTML = `<span class="err">${esc(e.message)}</span>`; return; }
  const saved = load(), byId = (id) => state.models.find((m) => m.id === id);
  const fams = ['anthropic/claude-opus', 'anthropic/claude-sonnet', 'openai/gpt', 'google/gemini', 'deepseek/', 'qwen/', 'x-ai/grok', 'moonshotai/'];
  const quick = fams.map((f) => state.models.find((m) => m.id.startsWith(f) && !/:free|vision|image|audio|embed/i.test(m.id))).filter(Boolean);
  $('#quick1').innerHTML = quick.map((m) => `<button type="button" data-q="${m.id}">${esc(m.name.replace(/^[^:]+:\s*/, ''))}</button>`).join('');
  $('#quick1').onclick = (e) => { const b = e.target.closest('[data-q]'); if (b) { state.m1 = byId(b.dataset.q); showChosen(1, state.m1); summary(); } };
  state.m1 = byId(saved.m1) || quick[0] || state.models[0];
  state.m2 = byId(saved.m2) || null; state.m3 = byId(saved.m3) || null;
  showChosen(1, state.m1); showChosen(2, state.m2); showChosen(3, state.m3);
  summary();
}
picker(1, (m) => { state.m1 = m; showChosen(1, m); summary(); });
picker(2, (m) => { state.m2 = m; showChosen(2, m); summary(); });
picker(3, (m) => { state.m3 = m; showChosen(3, m); summary(); });
$('#cmpModel').onchange = () => { $('#mp2').hidden = !$('#cmpModel').checked; summary(); };
$$('input[name=mode]').forEach((r) => r.onchange = () => { $('#mp3').hidden = radio('mode') === 'template'; summary(); });

// ---------------- voices ----------------
const VOICE_NOTE = { indicf5: 'IndicF5 (MIT) · best Hindi score', omnivoice: 'OmniVoice · non-commercial licence', kokoro: 'Kokoro (Apache-2.0)' };
async function loadVoices() {
  try { state.voices = (await api('/voices')).data || []; } catch { state.voices = []; }
  fillVoices();
}
function fillVoices() {
  const lang = radio('lang');
  const ok = (v) => (lang === 'english' ? v.language === 'en' || v.model === 'omnivoice' : v.language !== 'en' || v.model === 'omnivoice');
  const vs = state.voices.filter(ok).sort((a, b) => (a.model === 'indicf5' ? -1 : 0) - (b.model === 'indicf5' ? -1 : 0));
  const def = lang === 'english' ? 'kokoro:am_michael' : 'indicf5:ref-female';
  $('#voice').innerHTML = vs.map((v) => `<option value="${v.model}:${v.id}">${esc(v.model)} · ${esc(v.id)}</option>`).join('') || `<option value="${def}">${def}</option>`;
  const saved = load().voice;
  $('#voice').value = vs.some((v) => `${v.model}:${v.id}` === saved) ? saved : def;
  if (!$('#voice').value && vs[0]) $('#voice').value = `${vs[0].model}:${vs[0].id}`;
  voiceCap(); summary();
}
function voiceCap() { const m = ($('#voice').value || '').split(':')[0]; $('#voiceCap').textContent = VOICE_NOTE[m] || ''; }
$('#voice').onchange = () => { voiceCap(); summary(); };
$$('input[name=lang]').forEach((r) => r.onchange = () => { if (radio('lang') === 'hindi') setRadio('screen', 'hi'); fillVoices(); });
let audio;
$('#prev').onclick = async () => {
  const b = $('#prev'); b.disabled = true; b.textContent = '…';
  try { const r = await api('/voice-preview', { body: { voice: $('#voice').value, text: SAMPLE[radio('lang')] } }); const url = URL.createObjectURL(await r.blob()); audio?.pause(); audio = new Audio(url); await audio.play(); }
  catch (e) { toast('Voice preview failed: ' + e.message); }
  b.disabled = false; b.textContent = '▶';
};

// ---------------- settings + estimate ----------------
$('#temp').oninput = () => { $('#tempV').textContent = $('#temp').value; };
$('#minutes').oninput = () => { $('#minV').textContent = $('#minutes').value; summary(); };
$$('.stepper button').forEach((b) => b.onclick = () => { const o = $('#checks'); o.textContent = Math.max(0, Math.min(5, +o.textContent + +b.dataset.d)); summary(); });
$$('#newForm input, #newForm select').forEach((el) => el.addEventListener('change', () => summary()));

function settings() {
  return {
    language: radio('lang'), screen_lang: radio('screen'), voice: $('#voice').value, mode: radio('mode'), aspect: radio('aspect'),
    minutes: +$('#minutes').value, kinds: $$('#kinds input:checked').map((i) => i.value), checks: +$('#checks').textContent,
    quality: radio('quality'), bk: $('#bk').checked, grid: $('#grid').checked, burn_captions: $('#burn').checked, sfx: $('#sfx').checked, chrome: $('#chrome').checked,
    music: 'none', temperature: +$('#temp').value, cap_usd: +$('#cap').value || 0, instructions: $('#instr').value.trim(),
    code_model: state.m3?.id || null,
  };
}
function estimate(m, s, chars) {
  if (!m) return null;
  const pin = chars / 3.2 + 4500, pout = s.minutes * 2200;
  let usd = (pin * m.in_per_m + pout * m.out_per_m) / 1e6;
  if (s.mode !== 'template') { const cm = state.m3 || m, scenes = Math.ceil(s.minutes * 2.3); usd += scenes * (4200 * cm.in_per_m + 3000 * cm.out_per_m) / 1e6; }
  return usd;
}
function summary() {
  const s = settings(), src = radio('source');
  const chars = src === 'text' ? $('#ptext').value.length : [...state.picked.values()].reduce((a, u) => a + Math.min(14000, u.context_chars || 0), 0);
  const ch = state.chapters.find((c) => c.id === $('#chapter').value), bk = state.books.find((b) => b.id === $('#book').value);
  let usd = estimate(state.m1, s, chars);
  if ($('#cmpModel').checked && state.m2) usd = (usd || 0) + (estimate(state.m2, s, chars) || 0);
  $('#costChip').textContent = usd == null ? '—' : `~${money(usd)} / ${inr(usd)}`;
  $('#railCost').textContent = usd == null ? '—' : '~' + money(usd); $('#railInr').textContent = usd == null ? '' : `about ${inr(usd)}`;
  const target = src === 'text' ? ($('#ptitle').value || 'Pasted material') : (state.picked.size ? `${state.picked.size} teaching unit${state.picked.size > 1 ? 's' : ''}` : 'not picked yet');
  $('#facts').innerHTML = [
    ['Source', src === 'text' ? 'Your material' : (bk ? `Class ${bk.grade} ${bk.subject}` : '—')],
    ['Chapter', src === 'text' ? '—' : (ch ? `${ch.number}. ${ch.title}` : '—')], ['Teaches', target],
    ['Model', (state.m1?.name || '—') + ($('#cmpModel').checked && state.m2 ? ` vs ${state.m2.name}` : '')],
    ['Visuals', s.mode === 'both' ? 'Templates + LLM' : MODE[s.mode]], ['Format', `${s.aspect} · ~${s.minutes} min · ${s.quality}`],
    ['Voice', `${s.language} · ${s.voice}`],
  ].map(([a, b]) => `<dt>${a}</dt><dd>${esc(b)}</dd>`).join('');
  save();
}
const load = () => { try { return JSON.parse(localStorage.getItem(LS) || '{}'); } catch { return {}; } };
function save() {
  try { localStorage.setItem(LS, JSON.stringify({ ...load(), grade: $('#grade').value, book: $('#book').value, chapter: $('#chapter').value, m1: state.m1?.id, m2: state.m2?.id, m3: state.m3?.id, voice: $('#voice').value, s: settings() })); } catch {}
}
function restoreSettings() {
  const s = load().s; if (!s) return;
  ['lang:language', 'screen:screen_lang', 'mode:mode', 'aspect:aspect', 'quality:quality'].forEach((p) => { const [r, k] = p.split(':'); if (s[k]) setRadio(r, s[k]); });
  if (s.minutes) { $('#minutes').value = s.minutes; $('#minV').textContent = s.minutes; }
  if (s.checks != null) $('#checks').textContent = s.checks;
  if (s.kinds) $$('#kinds input').forEach((i) => { i.checked = s.kinds.includes(i.value); });
  ['bk', 'grid', 'sfx', 'chrome'].forEach((k) => { if (k in s) $('#' + k).checked = s[k]; }); if ('burn_captions' in s) $('#burn').checked = s.burn_captions;
  if (s.temperature) { $('#temp').value = s.temperature; $('#tempV').textContent = s.temperature; }
  if (s.cap_usd != null) $('#cap').value = s.cap_usd;
  $('#mp3').hidden = radio('mode') === 'template';
}

// ---------------- create ----------------
$('#newForm').onsubmit = async (e) => {
  e.preventDefault(); $('#newErr').hidden = true;
  const src = radio('source'), s = settings();
  let target;
  if (src === 'text') {
    if (!$('#ptext').value.trim()) return showErr('Paste some material first.');
    target = { label: $('#ptitle').value.trim() || 'Pasted material', text: $('#ptext').value, grade: +$('#pgrade').value };
  } else {
    if (!state.picked.size) return showErr('Pick at least one teaching unit.');
    const ch = state.chapters.find((c) => c.id === $('#chapter').value), bk = state.books.find((b) => b.id === $('#book').value);
    const units = [...state.picked.values()];
    target = { unit_ids: units.map((u) => u.id), units: units.map((u) => u.name), chapter: ch?.title, chapter_id: ch?.id, chapter_number: ch?.number,
      book: bk?.title, subject: bk?.subject, grade: bk?.grade, label: units.length === 1 ? units[0].name : `${ch?.title || 'Lesson'}: ${units.length} units` };
  }
  if (!state.m1) return showErr('Choose a model.');
  if (!s.kinds.length) return showErr('Turn on at least one scene type.');
  $('#go').disabled = true; $('#go').textContent = 'Starting…';
  try {
    const r = await api('/videos', { body: { target, settings: s, model: state.m1.id, compare_model: $('#cmpModel').checked && state.m2 ? state.m2.id : null } });
    if (r.ids.length > 1) toast('Two scripts are being written. The second one is in the Library.');
    location.href = '/studio/?v=' + r.ids[0];
  } catch (err) { showErr(err.message); $('#go').disabled = false; $('#go').textContent = 'Write the script'; }
};
function showErr(m) { $('#newErr').textContent = m; $('#newErr').hidden = false; }

// =================================================================
// one video: review, build, done
// =================================================================
let V = null, lastEvent = 0, events = [], dirty = false, pollT = null, speak = [];
const STEPS = [['script', 'Write the script'], ['voice', 'Record the voice (with a speech check)'], ['words', 'Time every word'], ['code', 'Write the animations'], ['render', 'Render on the GPU'], ['publish', 'Publish to the player']];

async function openVideo(id) {
  $('#newForm').hidden = true; $('#video').hidden = false; $('#go2').hidden = true;
  V = await api('/videos/' + id);
  speak = V.stage?.speakable || [];
  events = []; lastEvent = 0;
  await poll();
}
async function poll() {
  clearTimeout(pollT);
  try {
    const r = await api(`/videos/${V.id}/events?after=${lastEvent}`);
    if (r.events.length) { events.push(...r.events); lastEvent = r.events[r.events.length - 1].id; }
    const changed = r.status !== V.status;
    Object.assign(V, { status: r.status, cost_usd: r.cost_usd, variants: r.variants, error: r.error });
    if (changed && (r.status === 'review' || r.status === 'done')) V = await api('/videos/' + V.id);
    renderVideo(changed);
  } catch (e) { /* transient */ }
  if (ACTIVE.includes(V.status)) pollT = setTimeout(poll, 2500);
}

function stepState(step) {
  const evs = events.filter((e) => e.step === step);
  if (step === 'code' && !V.variants?.some((x) => x.mode === 'llm') && V.settings.mode === 'template') return ['skipped', 'Not needed for design templates'];
  if (!evs.length) return [V.status === 'failed' ? 'skipped' : 'waiting', ''];
  const last = evs[evs.length - 1], first = evs.find((e) => e.status === 'running');
  const st = evs.some((e) => e.status === 'failed') ? 'failed' : evs.some((e) => e.status === 'done') ? 'done' : 'running';
  return [st, (st === 'done' ? evs.filter((e) => e.status === 'done').pop() : last).message || first?.message || ''];
}

// The page is polled every 2.5 s while a video builds. Replacing the cards on every poll replayed their fade-in
// (and reloaded Bal Krishna's image), so the page flickered. Now the card shells stay in place and each part is
// written only when its HTML actually changed; the script editor is never redrawn under the teacher's cursor.
const shown = { head: null, body: null, facts: null, tip: null, cost: null };
function setIfChanged(el, key, html) {
  if (!el || shown[key] === html) return false;
  el.innerHTML = html; shown[key] = html; return true;
}
function renderVideo(changed) {
  const v = V, s = v.settings || {};
  const title = (v.title || 'Video') + ' · EduVid Studio';
  if (document.title !== title) document.title = title;
  const head = `<h2><span class="grow">${esc(v.title || v.target?.label || 'Untitled')}</span>${statusPill(v.status)}</h2>
    <dl class="facts"><dt>Teaches</dt><dd>${esc((v.target?.units || []).join(', ') || v.target?.label || '')}</dd>
    <dt>Model</dt><dd>${esc(v.model)}</dd><dt>Visuals</dt><dd>${esc(s.mode === 'both' ? 'Templates + LLM animation' : MODE[s.mode] || s.mode)}</dd>
    <dt>Format</dt><dd>${esc(`${s.aspect} · ${s.language} · ${s.voice}`)}</dd><dt>AI cost so far</dt><dd>${money(v.cost_usd)} <span class="cap">(${inr(v.cost_usd)})</span></dd></dl>
    <ol class="steps">${STEPS.map(([k, label]) => { const [st, msg] = stepState(k); return `<li class="${st}"><span class="ico">${st === 'done' ? '✓' : st === 'failed' ? '✕' : ''}</span><span class="t">${label}${msg ? `<small>${esc(msg)}</small>` : ''}</span></li>`; }).join('')}</ol>
    ${v.error ? `<div class="err">${esc(v.error)}</div>` : ''}
    <div class="actions">${v.status === 'failed' ? '<button class="btn primary" id="retry" type="button">Try again</button>' : ''}
      <button class="btn small" id="log" type="button">Activity log</button>
      ${v.variants?.length ? v.variants.map((x) => `<button class="btn small" type="button" data-rlog="${x.mode}">Render log: ${esc(x.mode)}</button>`).join('') : ''}
      <a class="btn small ghost" href="/studio/">+ New video</a></div>`;
  let body = '';
  if (v.status === 'scripting') body = `<section class="card"><div class="bk-row"><img src="/studio/static/nce/assets/bk-calm.png" alt=""><div class="bubble">I'm reading the NCERT pages and writing your script with ${esc(v.model)}. This usually takes 1–3 minutes.</div></div></section>`;
  if (v.status === 'review' && v.script) body = reviewCard();
  if (v.status === 'done') body = doneCard();
  if (!$('#vhead')) {                       // first render: build the two shells once
    $('#video').innerHTML = '<section class="card" id="vhead"></section><div id="vbody"></div>';
    shown.head = shown.body = null;
  }
  let touched = setIfChanged($('#vhead'), 'head', head);
  // the review editor holds unsaved edits: only rebuild it when the video's status changed
  if (v.status !== 'review' || changed || shown.body === null || !shown.body.includes('id="saveBtn"')) {
    touched = setIfChanged($('#vbody'), 'body', body) || touched;
  }
  if (touched) wireVideo();
  const tipText = { scripting: 'Writing your script…', review: 'Read it through. Red lines can’t be spoken yet: fix them, then Build.', voicing: 'Recording each sentence, and checking it with speech recognition.', timing: 'Matching every word to the audio.', coding: 'The model is drawing each scene.', rendering: 'Rendering frames on the GPU.', publishing: 'Almost there!', done: 'Your video is ready. Shabash!', failed: 'Something went wrong. Check the log, then try again.' }[v.status] || '';
  if (shown.tip !== tipText) { tip(tipText); shown.tip = tipText; }
  const cost = `${money(v.cost_usd)}|${inr(v.cost_usd)}`;
  if (shown.cost !== cost) {
    $('#costLbl').textContent = 'AI cost so far'; $('#railCost').textContent = money(v.cost_usd); $('#railInr').textContent = inr(v.cost_usd);
    shown.cost = cost;
  }
  setIfChanged($('#facts'), 'facts', [['Status', (v.status)], ['Scenes', v.script ? v.script.scenes.length : '—'], ['Length', v.duration_s ? mmss(v.duration_s) : '—']].map(([a, b]) => `<dt>${a}</dt><dd>${esc(b)}</dd>`).join(''));
}

// ---------- review ----------
function sceneData(sc) { const o = {}; for (const [k, val] of Object.entries(sc)) if (!['lines', 'id', 'kind', 'title', 'custom_code'].includes(k) && val != null && !(Array.isArray(val) && !val.length) && !(typeof val === 'object' && !Array.isArray(val) && !val.en && !val.hi) && val !== '') o[k] = val; return o; }
const T = (bi) => (bi?.en || bi?.hi || '');
function preview(sc) {
  if (sc.kind === 'check') return `<div class="preview"><b>${esc(T(sc.question))}</b>${(sc.options || []).map((o, i) => `<span class="opt ${i === sc.correct ? 'ok' : ''}"><i>${'ABCD'[i]}</i>${esc(T(o))}</span>`).join('')}<span class="cap">Hint: ${esc(T(sc.hint))}</span></div>`;
  const items = [...(sc.points || []).map((p) => T(p.text) + (p.tex ? `  [${p.tex}]` : '')), ...(sc.steps || []).map((s) => s.tex || T(s.text)), ...(sc.shapes || []).map((s) => `${s.type}${s.label ? ' “' + s.label + '”' : ''}`), ...(sc.objectives || []).map(T)];
  const q = sc.question && T(sc.question) ? `<b>${esc(T(sc.question))}</b>` : '';
  return `<div class="preview">${q}${items.slice(0, 10).map((x) => `<span>• ${esc(x)}</span>`).join('')}${sc.answer && T(sc.answer) ? `<span><b>Answer:</b> ${esc(T(sc.answer))}</span>` : ''}</div>`;
}
function reviewCard() {
  const sc = V.script.scenes, bad = new Set(speak.map((p) => p.split(':')[0]));
  return `<section class="card"><h2><span class="n">5</span><span class="grow">Review the script</span><span class="pill info">${sc.length} scenes · ${sc.reduce((a, s) => a + s.lines.length, 0)} lines</span></h2>
    <p class="cap">Edit anything. <b>say</b> is what the voice speaks (${V.script.language === 'english' ? 'plain English, maths spelt out' : 'Devanagari only: no digits, Latin letters or symbols'}); <b>caption</b> is shown in the player.</p>
    ${speak.length ? `<div class="note">${speak.length} line(s) can’t be spoken as written: ${esc(speak.slice(0, 3).join(' · '))}${speak.length > 3 ? ' …' : ''}</div>` : ''}
    <div class="field" style="margin-top:12px"><label for="vtitle">Video title</label><input type="text" id="vtitle" value="${esc(V.script.title.en || '')}"></div>
    ${sc.map((s, i) => `<article class="scene" data-s="${i}">
      <header><span class="num">${i + 1}</span><span class="pill badge">${KIND_LBL[s.kind] || s.kind}</span><strong><input type="text" data-f="title" value="${esc(s.title.en || '')}" aria-label="Scene ${i + 1} title" style="padding:6px 10px"></strong>
        <button class="btn small ghost" type="button" data-act="up" aria-label="Move up" ${i ? '' : 'disabled'}>↑</button><button class="btn small ghost" type="button" data-act="down" aria-label="Move down" ${i < sc.length - 1 ? '' : 'disabled'}>↓</button>
        <button class="btn small ghost" type="button" data-act="regen">Rewrite…</button><button class="btn small ghost danger" type="button" data-act="del" aria-label="Delete scene">✕</button></header>
      <div class="body">${preview(s)}
        ${s.lines.map((ln, j) => `<div class="ln ${bad.has(`${s.id} line ${j}`) ? 'bad' : ''}"><span class="i">${j + 1}</span><div>
          <textarea class="say" rows="2" data-l="${j}" data-f="say" lang="${V.script.language === 'english' ? 'en' : 'hi'}" aria-label="Scene ${i + 1} line ${j + 1}: spoken text">${esc(ln.say)}</textarea>
          <div class="pair"><input type="text" data-l="${j}" data-f="caps" value="${esc(ln.caps || '')}" placeholder="caption" aria-label="caption"><input type="text" data-l="${j}" data-f="en" value="${esc(ln.en || '')}" placeholder="English caption" aria-label="English caption"></div></div></div>`).join('')}
        <details><summary>Edit scene content (JSON)</summary><textarea data-f="json" spellcheck="false">${esc(JSON.stringify(sceneData(s), null, 1))}</textarea></details>
      </div></article>`).join('')}
    <div class="grid" style="margin-top:16px">
      <div class="field"><div class="label">Visuals</div><div class="seg" role="radiogroup" aria-label="Visual mode">
        ${['template', 'llm', 'both'].map((m) => `<label><input type="radio" name="vmode" value="${m}" ${V.settings.mode === m ? 'checked' : ''}>${m === 'both' ? 'Both' : MODE[m]}</label>`).join('')}</div></div>
      <div class="field"><div class="label">Quality</div><div class="seg" role="radiogroup" aria-label="Quality">
        ${['draft', 'final'].map((m) => `<label><input type="radio" name="vq" value="${m}" ${V.settings.quality === m ? 'checked' : ''}>${m === 'draft' ? 'Draft' : 'Final'}</label>`).join('')}</div></div>
    </div>
    <div class="sticky-bar"><span class="cap" id="saveState" style="margin-right:auto;align-self:center"></span><button class="btn" type="button" id="saveBtn">Save</button><button class="btn primary" type="button" id="build">Build the video</button></div>
  </section>`;
}
function readEdits() {
  const sc = V.script;
  sc.title.en = $('#vtitle')?.value ?? sc.title.en;
  $$('.scene').forEach((el) => {
    const s = sc.scenes[+el.dataset.s];
    s.title.en = el.querySelector('[data-f=title]').value;
    el.querySelectorAll('[data-l]').forEach((f) => { s.lines[+f.dataset.l][f.dataset.f] = f.value; });
    const j = el.querySelector('[data-f=json]');
    try { Object.assign(s, JSON.parse(j.value)); j.style.borderColor = ''; } catch { j.style.borderColor = 'var(--bad)'; throw new Error(`Scene ${+el.dataset.s + 1}: the content JSON is not valid`); }
  });
}
async function saveScript(quiet) {
  readEdits();
  const r = await api(`/videos/${V.id}/script`, { method: 'PUT', body: { script: V.script } });
  V.script = r.script; speak = r.speakable; dirty = false;
  if (!quiet) { shown.body = null; setIfChanged($('#vbody'), 'body', reviewCard()); wireVideo(); toast(speak.length ? `Saved. ${speak.length} line(s) still need fixing.` : 'Saved.'); }
  return r;
}
function wireVideo() {
  $('#retry')?.addEventListener('click', async () => { await api(`/videos/${V.id}/retry`, { body: {} }); V = await api('/videos/' + V.id); events = []; lastEvent = 0; poll(); });
  $('#log')?.addEventListener('click', () => drawer('Activity', `<pre>${esc(events.map((e) => `${e.ts.slice(11, 19)}  ${e.step.padEnd(7)} ${e.status.padEnd(7)} ${e.message}`).join('\n'))}</pre>`));
  $$('[data-rlog]').forEach((b) => b.onclick = async () => { try { const r = await api(`/videos/${V.id}/${b.dataset.rlog}/log`); drawer('Render log: ' + b.dataset.rlog, `<pre>${esc(await r.text())}</pre>`); } catch (e) { toast(e.message); } });
  if (V.status !== 'review') return;
  $('#vbody').oninput = () => { dirty = true; $('#saveState').textContent = 'Unsaved changes'; };
  $('#saveBtn').onclick = () => saveScript().catch((e) => toast(e.message));
  $$('input[name=vmode], input[name=vq]').forEach((r) => r.onchange = async () => { V.settings = await api(`/videos/${V.id}/settings`, { method: 'PATCH', body: { mode: radio('vmode'), quality: radio('vq') } }); });
  $('#vbody').onclick = async (e) => {
    const b = e.target.closest('[data-act]'); if (!b) return;
    const i = +b.closest('.scene').dataset.s, sc = V.script.scenes;
    try { readEdits(); } catch (err) { return toast(err.message); }
    if (b.dataset.act === 'up' || b.dataset.act === 'down') { const j = b.dataset.act === 'up' ? i - 1 : i + 1; [sc[i], sc[j]] = [sc[j], sc[i]]; await saveScript(); }
    if (b.dataset.act === 'del') { if (!confirm(`Delete scene ${i + 1}?`)) return; sc.splice(i, 1); await saveScript(); }
    if (b.dataset.act === 'regen') {
      const note = prompt('What should change in this scene?', 'Make it clearer, with a simpler everyday example'); if (note == null) return;
      b.disabled = true; b.textContent = 'Rewriting…';
      try { if (dirty) await saveScript(true); const r = await api(`/videos/${V.id}/scenes/${i}/regenerate`, { body: { note } }); V.script = r.script; speak = r.speakable; shown.body = null; setIfChanged($('#vbody'), 'body', reviewCard()); wireVideo(); toast(`Scene ${i + 1} rewritten.`); }
      catch (err) { toast(err.message); b.disabled = false; b.textContent = 'Rewrite…'; }
    }
  };
  $('#build').onclick = async () => {
    const b = $('#build'); b.disabled = true; b.textContent = 'Starting…';
    try {
      await saveScript(true);
      if (speak.length) { shown.body = null; setIfChanged($('#vbody'), 'body', reviewCard()); wireVideo(); return toast('Fix the red lines first.'); }
      await api(`/videos/${V.id}/approve`, { body: {} });
      V = await api('/videos/' + V.id); renderVideo(true); poll();
    } catch (e) { toast(e.message); b.disabled = false; b.textContent = 'Build the video'; }
  };
}

// ---------- done ----------
function doneCard() {
  const ok = V.variants.filter((x) => x.status === 'done');
  return `<section class="card done-card"><h2><span class="n">✓</span><span class="grow">Your video is ready</span><span class="pill ok">${mmss(V.duration_s)}</span></h2>
    <div class="cmp" style="grid-template-columns:repeat(${Math.min(2, ok.length)},1fr)">${ok.map((x) => `<div>
      <a class="figure" href="/studio/watch/${V.id}?mode=${x.mode}" style="display:block"><img src="/studio/media/${V.id}/${x.mode}/poster.jpg" alt="${esc(MODE[x.mode])} poster" style="display:block;width:100%;border-radius:11px;background:var(--paper)"></a>
      <div class="actions"><span class="pill badge">${esc(MODE[x.mode])}</span><a class="btn primary small" href="/studio/watch/${V.id}?mode=${x.mode}">Watch</a>
      <a class="btn small" href="/studio/media/${V.id}/${x.mode}/video.mp4" download>Download MP4</a><a class="btn small ghost" href="/studio/media/${V.id}/${x.mode}/sheet.jpg" target="_blank" rel="noopener">Contact sheet</a></div></div>`).join('')}</div>
    ${ok.length > 1 ? `<div class="actions"><a class="btn" href="/studio/compare?v=${V.id}">Compare side by side</a></div>` : ''}
    ${V.compare_id ? `<div class="actions"><a class="btn" href="/studio/compare?group=${V.compare_id}">Compare the two models</a></div>` : ''}
    <p class="cap">The watch link is public (anyone with it can watch, no login), so you can share it with students.</p>
    <div class="actions"><button class="btn small" type="button" id="copyLink">Copy watch link</button></div></section>`;
}
document.addEventListener('click', (e) => { if (e.target.id === 'copyLink') { navigator.clipboard?.writeText(`${location.origin}/studio/watch/${V.id}`); toast('Link copied.'); } });
window.addEventListener('beforeunload', (e) => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });

// ---------------- start ----------------
const vid = new URLSearchParams(location.search).get('v');
health();
if (vid) openVideo(vid).catch((e) => { $('#video').innerHTML = `<div class="err">${esc(e.message)}</div>`; });
else { restoreSettings(); loadBooks(); loadModels(); loadVoices(); summary(); }
