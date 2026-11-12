// NCE video player: the lesson video inside the NCE app frame (design_ref §11).
import { I } from '/studio/static/nce/player/icons.js';

// video icons drawn in the kit's style (24 grid, stroke 2.2, round caps); added beside the kit set, not mixed with a library
const V = {
  play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13a1 1 0 001.5.86l10.4-6.5a1 1 0 000-1.72L9.5 4.64A1 1 0 008 5.5z"/></svg>',
  pause: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M8.5 5.5v13M15.5 5.5v13"/></svg>',
  back10: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12a8 8 0 108-8H8"/><path d="M10.5 1.5L8 4l2.5 2.5"/><text x="12" y="15.6" font-size="7.5" font-weight="700" text-anchor="middle" fill="currentColor" stroke="none" font-family="sans-serif">10</text></svg>',
  replay: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12a8 8 0 108-8H8"/><path d="M10.5 1.5L8 4l2.5 2.5"/></svg>',
  full: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>',
  chapters: I.menu,
};
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const mmss = (s) => { s = Math.max(0, Math.floor(s || 0)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
const STR = {
  en: { part: (a, b) => `Part ${a} of ${b}`, play: 'Play', pause: 'Pause', back: 'Back 10s', check: 'Check', pick: 'Pick an answer', cont: 'Continue', skip: 'Skip',
    try: 'Pause and try', hint: 'Need a hint?', right: 'Right!', notq: 'Not quite', tryagain: 'Try once more.', answer: 'The answer is', again: 'Watch again',
    close: 'Close', chapters: 'Chapters', watched: 'watched', rightL: 'right first time', pts: 'points', done: 'Well done!', cheer: 'Shabash! You finished the video.',
    voiceOff: 'Voice off', voiceOn: 'Voice on', fin: (n) => `${n} part${n === 1 ? '' : 's'} · all done`, notReady: 'This video is not ready yet. Try again in a few minutes.', mode: { template: 'Design', llm: 'Animated' } },
  hi: { part: (a, b) => `भाग ${a} / ${b}`, play: 'चलाएँ', pause: 'रोकें', back: '10 सेकंड पीछे', check: 'जाँचें', pick: 'एक उत्तर चुनें', cont: 'आगे बढ़ें', skip: 'छोड़ें',
    try: 'रुककर सोचो', hint: 'संकेत चाहिए?', right: 'सही!', notq: 'पूरा सही नहीं', tryagain: 'एक बार और कोशिश करो।', answer: 'सही उत्तर है', again: 'फिर से देखें',
    close: 'बंद करें', chapters: 'भाग', watched: 'देखा', rightL: 'पहली बार में सही', pts: 'अंक', done: 'बहुत बढ़िया!', cheer: 'शाबाश! तुमने वीडियो पूरा कर लिया।',
    voiceOff: 'आवाज़ बंद', voiceOn: 'आवाज़ चालू', fin: (n) => `${n} भाग · सब पूरा`, notReady: 'यह वीडियो अभी तैयार नहीं है। थोड़ी देर बाद देखें।', mode: { template: 'डिज़ाइन', llm: 'एनिमेशन' } },
};
const vid = location.pathname.split('/').pop(), qs = new URLSearchParams(location.search);
const video = $('#v');
let M = null, lang = 'en', ccOn = true, muted = false, xp = 0, rightFirst = 0, asked = 0, done = new Set(), active = null, attempts = 0, sel = null, speedI = 1, wrong = new Set(), solved = false;
const SPEEDS = [0.75, 1, 1.25, 1.5];
try { lang = localStorage.getItem('nce:v1:lang') || 'en'; muted = localStorage.getItem('nce:v1:voice') === 'off'; ccOn = localStorage.getItem('eduvid:cc') !== 'off'; } catch {}
const S = () => STR[lang];
const T = (bi) => (bi ? (bi[lang] || bi.en || bi.hi || '') : '');

// ---------- boot ----------
$('#menuBtn').innerHTML = V.chapters; $('#closeBtn').innerHTML = I.close; $('#xpIco').innerHTML = I.flame; $('#fsBtn').innerHTML = V.full; $('#bigplay').innerHTML = V.play;
(async () => {
  try {
    const r = await fetch(`/studio/api/watch/${vid}${qs.get('mode') ? '?mode=' + encodeURIComponent(qs.get('mode')) : ''}`);
    if (!r.ok) throw new Error(r.status === 404 ? 'notReady' : 'HTTP ' + r.status);
    M = await r.json();
  } catch (e) { $('#watch').hidden = true; $('#err').hidden = false; $('#err').textContent = S().notReady; return; }
  video.src = M.video_url; if (M.poster_url) video.poster = M.poster_url;
  if (M.settings?.aspect === '9:16') { $('.vpaper').classList.add('portrait'); $('#watch').classList.add('portrait'); }
  if ((M.modes || []).length > 1) { $('#modeBtn').hidden = false; }
  $('#ticks').innerHTML = M.chapters.slice(1).map((c) => `<span style="left:${(c.t / M.duration) * 100}%"></span>`).join('');
  video.muted = muted;
  if (M.settings?.burn_captions) ccOn = false;           // captions are already in the picture
  applyLang(); tick();
})();

// ---------- language (whole screen switches at once; remembered per device) ----------
function applyLang() {
  document.documentElement.lang = lang;
  document.querySelectorAll('.langsw button').forEach((b) => b.classList.toggle('on', b.dataset.l === lang));
  document.title = T(M?.title) || 'Lesson video';
  $('#backBtn').innerHTML = `${V.back10}<span>${S().back}</span>`;
  $('#muteBtn').innerHTML = muted ? I.mute : I.speaker; $('#muteBtn').setAttribute('aria-label', muted ? S().voiceOn : S().voiceOff);
  $('#qTag').textContent = S().try; $('#hintBtn').textContent = S().hint; $('#sheetH').textContent = S().chapters;
  $('#ccBtn').setAttribute('aria-pressed', String(ccOn));
  if (M) { $('#modeBtn').textContent = S().mode[M.mode] || M.mode; $('#vmetaTxt').textContent = [M.target?.subject && `Class ${M.target.grade} · ${M.target.subject}`, M.target?.chapter].filter(Boolean).join(' · '); }
  renderChapters(); renderMain(); if (active) renderQuiz(); if (!$('#finish').hidden) finish();
}
document.querySelectorAll('.langsw button').forEach((b) => b.onclick = () => { lang = b.dataset.l; try { localStorage.setItem('nce:v1:lang', lang); } catch {} applyLang(); });

// ---------- chapters ----------
const chapterAt = (t) => { let i = 0; M.chapters.forEach((c, k) => { if (t >= c.t - 0.05) i = k; }); return i; };
function renderChapters() {
  if (!M) return;
  const cur = chapterAt(video.currentTime || 0);
  $('#chapters').innerHTML = M.chapters.map((c, i) => `<button type="button" class="dstep ${i === cur ? 'on' : i < cur || done.has(i) ? 'done' : ''}" data-i="${i}" aria-current="${i === cur}"><b>${i < cur || done.has(i) ? '✓' : i + 1}</b>${esc(T(c.title))}</button>`).join('');
  $('#part').textContent = S().part(cur + 1, M.chapters.length);
  $('#sceneTitle').textContent = T(M.chapters[cur].title);
  $('#sheetList').innerHTML = M.chapters.map((c, i) => `<button type="button" class="mrow" data-i="${i}"><span class="mnum">${i + 1}</span><span class="mtx"><strong>${esc(T(c.title))}</strong><small>${mmss(c.t)}</small></span></button>`).join('');
}
let lastCh = -1;
function onChapterTick() { const c = chapterAt(video.currentTime); if (c !== lastCh) { if (lastCh >= 0 && c > lastCh) done.add(lastCh); lastCh = c; renderChapters(); } }
const seekTo = (t) => { video.currentTime = Math.max(0, Math.min(M.duration - 0.05, t)); tick(); };
$('#chapters').onclick = (e) => { const b = e.target.closest('[data-i]'); if (b) { seekTo(M.chapters[+b.dataset.i].t + 0.01); play(); } };
$('#sheetList').onclick = (e) => { const b = e.target.closest('[data-i]'); if (b) { closeSheet(); seekTo(M.chapters[+b.dataset.i].t + 0.01); play(); } };
$('#menuBtn').onclick = () => { $('#sheet').hidden = false; $('#scrim').hidden = false; $('#sheetList button')?.focus(); };
const closeSheet = () => { $('#sheet').hidden = true; $('#scrim').hidden = true; $('#menuBtn').focus(); };
$('#scrim').onclick = closeSheet;

// ---------- timeline ----------
function tick() {
  if (!M) return;
  const p = (video.currentTime || 0) / M.duration;
  $('#fill').style.width = `${p * 100}%`; $('#thumb').style.left = `${p * 100}%`;
  $('#tl').setAttribute('aria-valuenow', Math.round(p * 100)); $('#tl').setAttribute('aria-valuetext', `${mmss(video.currentTime)} of ${mmss(M.duration)}`);
  $('#time').textContent = `${mmss(video.currentTime)} / ${mmss(M.duration)}`;
  captions(); onChapterTick();
}
const tl = $('#tl');
const posT = (e) => { const r = tl.getBoundingClientRect(); return Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * M.duration; };
let dragging = false, wasPlaying = false;
tl.addEventListener('pointerdown', (e) => { if (!M) return; dragging = true; wasPlaying = !video.paused; video.pause(); tl.classList.add('drag'); tl.setPointerCapture(e.pointerId); seekTo(posT(e)); });
tl.addEventListener('pointermove', (e) => {
  if (!M) return; const t = posT(e), tip = $('#tip');
  tip.hidden = false; tip.style.left = `${(t / M.duration) * 100}%`; tip.textContent = `${mmss(t)} · ${T(M.chapters[chapterAt(t)].title)}`;
  if (dragging) seekTo(t);
});
tl.addEventListener('pointerleave', () => { $('#tip').hidden = true; });
tl.addEventListener('pointerup', () => { if (!dragging) return; dragging = false; tl.classList.remove('drag'); if (wasPlaying) play(); });
tl.addEventListener('keydown', (e) => { if (e.key === 'ArrowRight') { seekTo(video.currentTime + 5); e.preventDefault(); } if (e.key === 'ArrowLeft') { seekTo(video.currentTime - 5); e.preventDefault(); } });

// ---------- captions (drawn by the player, in the language of the switch) ----------
function captions() {
  if (!ccOn || !M) { $('#cc').innerHTML = ''; return; }
  const t = video.currentTime, track = lang === 'en' && M.language !== 'english' ? M.captions.en : M.captions.main;
  const c = track.find((x) => t >= x.s && t < x.e);
  $('#cc').innerHTML = c ? `<span>${esc(c.text)}</span>` : '';
}
$('#ccBtn').onclick = () => { ccOn = !ccOn; try { localStorage.setItem('eduvid:cc', ccOn ? 'on' : 'off'); } catch {} $('#ccBtn').setAttribute('aria-pressed', String(ccOn)); captions(); };

// ---------- play / pause ----------
function play() { if (active) return; video.play().catch(() => {}); }
function renderMain() {
  const b = $('#mainBtn');
  if (active) return;
  if (!$('#finish').hidden) { b.disabled = false; b.innerHTML = `${V.replay}<span>${S().again}</span>`; $('#backBtn').innerHTML = `${I.left}<span>${S().close}</span>`; return; }
  b.disabled = !M; b.innerHTML = video.paused ? `${V.play}<span>${S().play}</span>` : `${V.pause}<span>${S().pause}</span>`;
  $('#bigplay').hidden = !video.paused || !M || video.currentTime > 0.2;
}
$('#mainBtn').onclick = () => {
  if (active) return quizMain();
  if (!$('#finish').hidden) { $('#finish').hidden = true; $('#watch').hidden = false; seekTo(0); xp = 0; rightFirst = 0; asked = 0; done.clear(); answered.clear(); $('#xpN').textContent = '0'; play(); return; }
  video.paused ? play() : video.pause();
};
$('#bigplay').onclick = play;
video.addEventListener('click', () => (video.paused ? play() : video.pause()));
$('#backBtn').onclick = () => {
  if (active) return skipQuiz();
  if (!$('#finish').hidden) return closeBtn();
  seekTo(video.currentTime - 10);
};
video.addEventListener('play', renderMain); video.addEventListener('pause', renderMain);
// smooth timeline and captions while playing (timeupdate alone fires ~4 times a second)
const raf = () => { if (!video.paused && !video.ended) { tick(); checkQuiz(); requestAnimationFrame(raf); } };
video.addEventListener('playing', () => requestAnimationFrame(raf));
video.addEventListener('waiting', () => { $('#spin').hidden = false; }); video.addEventListener('playing', () => { $('#spin').hidden = true; });
video.addEventListener('timeupdate', () => { tick(); checkQuiz(); });
video.addEventListener('ended', finish);
$('#muteBtn').onclick = () => { muted = !muted; video.muted = muted; try { localStorage.setItem('nce:v1:voice', muted ? 'off' : 'on'); } catch {} applyLang(); };
$('#speedBtn').onclick = () => { speedI = (speedI + 1) % SPEEDS.length; video.playbackRate = SPEEDS[speedI]; $('#speedBtn').textContent = SPEEDS[speedI] + '×'; };
$('#fsBtn').onclick = () => { const f = $('#vidwrap'); document.fullscreenElement ? document.exitFullscreen() : f.requestFullscreen?.().catch(() => {}); };
document.addEventListener('fullscreenchange', () => $('#vidwrap').classList.toggle('fullscreen', !!document.fullscreenElement));
$('#modeBtn').onclick = () => { const other = M.modes.find((m) => m !== M.mode); if (other) location.search = '?mode=' + other; };
function closeBtn() { if (history.length > 1) history.back(); else location.href = '/studio/library'; }
$('#closeBtn').onclick = closeBtn;
document.addEventListener('keydown', (e) => {
  if (e.target.closest('input,textarea') || active) { if (e.key === 'Escape' && !$('#sheet').hidden) closeSheet(); return; }
  if (e.key === ' ' || e.key === 'k') { if (e.target.closest('button') && e.key === ' ') return; e.preventDefault(); video.paused ? play() : video.pause(); }
  else if (e.key === 'ArrowRight' && e.target !== tl) seekTo(video.currentTime + 5);
  else if (e.key === 'ArrowLeft' && e.target !== tl) seekTo(video.currentTime - 5);
  else if (e.key === 'c') $('#ccBtn').click(); else if (e.key === 'f') $('#fsBtn').click(); else if (e.key === 'm') $('#muteBtn').click();
  else if (e.key === 'Escape' && !$('#sheet').hidden) closeSheet();
});

// ---------- pause-to-check ----------
const answered = new Set();
function checkQuiz() {
  if (!M || active || dragging) return;
  const q = M.checks.find((c) => !answered.has(c.id) && video.currentTime >= c.t && video.currentTime < c.resume - 0.05);
  if (!q) return;
  video.pause(); seekTo(q.t);
  active = q; attempts = 0; sel = null; asked++; wrong = new Set(); solved = false;
  $('#watch').hidden = true; $('#quiz').hidden = false; $('#qHint').hidden = true; $('#fb').innerHTML = '';
  renderQuiz();
  $('#qOpts .opt')?.focus();
}
function renderQuiz() {
  const q = active;
  $('#qText').textContent = T(q.question);
  const locked = attempts >= 2 || solved;
  $('#qOpts').innerHTML = q.options.map((o, i) => {
    const good = (solved || attempts >= 2) && i === q.correct, bad = wrong.has(i);
    return `<button type="button" role="radio" aria-checked="${sel === i}" class="opt ${good ? 'good' : bad ? 'bad' : sel === i ? 'sel' : ''}" data-i="${i}" ${locked || bad ? 'disabled' : ''}><span class="lt">${'ABCD'[i]}</span><span class="tx">${esc(T(o))}</span><span class="mk">${good ? I.check : bad ? I.x : ''}</span></button>`;
  }).join('');
  if (locked) return;
  $('#hintBtn').parentElement.hidden = !T(q.hint);
  $('#qHintTxt').textContent = T(q.hint);
  $('#backBtn').innerHTML = `<span>${S().skip}</span>`;
  const b = $('#mainBtn'); b.disabled = sel == null; b.innerHTML = `<span>${sel == null ? S().pick : S().check}</span>`;
}
$('#qOpts').onclick = (e) => { const b = e.target.closest('[data-i]'); if (!b || b.disabled) return; sel = +b.dataset.i; renderQuiz(); };
$('#hintBtn').onclick = () => { $('#qHint').hidden = false; };
function fcard(kind, title, text) {
  const ico = kind === 'ok' ? I.check : kind === 'no' ? I.x : I.info;
  $('#fb').innerHTML = `<div class="fcard ${kind}" role="status"><span class="fc-ic">${ico}</span><span class="fc-txt"><span class="fc-title">${esc(title)}</span>${text ? `<p>${esc(text)}</p>` : ''}</span>${kind === 'ok' && attempts === 1 ? '<span class="xpchip">+10</span>' : ''}</div>`;
}
function quizMain() {
  const q = active, b = $('#mainBtn');
  if (b.dataset.next === '1') { b.dataset.next = ''; return endQuiz(); }
  if (sel == null) return;
  attempts++;
  const opts = [...document.querySelectorAll('#qOpts .opt')];
  if (sel === q.correct) {
    solved = true;
    opts[sel].classList.add('good'); opts[sel].querySelector('.mk').innerHTML = I.check;
    if (attempts === 1) { xp += 10; rightFirst++; const p = $('#xp'); $('#xpN').textContent = xp; p.classList.remove('bump'); void p.offsetWidth; p.classList.add('bump'); }
    fcard('ok', S().right, T(q.explain));
    opts.forEach((o) => { o.disabled = true; });
    b.disabled = false; b.innerHTML = `<span>${S().cont}</span>${I.right}`; b.dataset.next = '1';
  } else {
    opts[sel].classList.add('bad'); opts[sel].querySelector('.mk').innerHTML = I.x; wrong.add(sel);
    if (attempts >= 2) {
      opts[q.correct].classList.add('good'); opts[q.correct].querySelector('.mk').innerHTML = I.check;
      opts.forEach((o) => { o.disabled = true; });
      fcard('no', S().notq, `${S().answer} ${T(q.options[q.correct])}. ${T(q.explain)}`);
      b.disabled = false; b.innerHTML = `<span>${S().cont}</span>${I.right}`; b.dataset.next = '1';
    } else {
      fcard('no', S().notq, S().tryagain); $('#qHint').hidden = !T(q.hint);
      opts[sel].disabled = true; sel = null; b.disabled = true; b.innerHTML = `<span>${S().pick}</span>`;
    }
  }
}
function skipQuiz() { endQuiz(); }
function endQuiz() {
  const q = active; answered.add(q.id); active = null; $('#mainBtn').dataset.next = '';
  $('#quiz').hidden = true; $('#watch').hidden = false; $('#fb').innerHTML = '';
  $('#backBtn').innerHTML = `${V.back10}<span>${S().back}</span>`;
  seekTo(q.resume - 0.05); play(); $('#mainBtn').focus();
}

// ---------- finish ----------
function finish() {
  if (!M || active) return;
  M.chapters.forEach((_, i) => done.add(i)); renderChapters();
  $('#watch').hidden = true; $('#quiz').hidden = true; $('#finish').hidden = false;
  $('#finTitle').textContent = S().done; $('#finSub').textContent = `${T(M.title)} · ${S().fin(M.chapters.length)}`;
  $('#stTime').textContent = mmss(M.duration); $('#stRight').textContent = `${rightFirst}/${M.checks.length}`; $('#stXp').textContent = xp;
  $('#stTimeL').textContent = S().watched; $('#stRightL').textContent = S().rightL; $('#stXpL').textContent = S().pts;
  $('#finBubble').textContent = S().cheer;
  renderMain();
}
