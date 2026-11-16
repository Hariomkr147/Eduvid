// nce-lesson: NCE-styled lesson video. Boot: fonts → lesson.json + narration timing → scenes → maths images.
// draw(t) renders film time t as a pure function of t. window.OP is the API tools/capture.mjs drives
// (ready, bootError, duration(), draw(t), frame(t, q, fmt), cues(), shots(), captions()).
import * as K from './kit.js';
import { TEMPLATES, layout, header, sceneTex, tr } from './scenes.js';
import { shapeTex } from './figure.js';
import { compile, makeA, dryRun } from './custom.js';
import { loadSolids, GL } from './solid.js';

const cv = document.getElementById('cv');
const OP = (window.OP = { ready: false });
const norm = (w) => String(w).toLowerCase().replace(/[^\p{L}\p{M}\p{N}']+/gu, '');
let LESSON, SCENES = [], DUR = 0, CAPS = [], LAY;

async function getJSON(f) { const r = await fetch(f, { cache: 'no-store' }); if (!r.ok) throw new Error(`missing ${f}`); return r.json(); }

function buildTiming(script, lines, words) {
  const L = lines.lines;
  let g = 0;
  const scenes = script.scenes.map((sc) => { const s = { sc, g0: g, n: sc.lines.length }; g += sc.lines.length; return s; });
  if (g !== L.length) throw new Error(`lesson has ${g} lines but the narration has ${L.length}`);
  scenes.forEach((s, i) => {
    const first = L[s.g0].start;
    s.start = i === 0 ? 0 : Math.max(first - 0.45, L[s.g0 - 1].end + 0.05);
  });
  scenes.forEach((s, i) => { s.end = i < scenes.length - 1 ? scenes[i + 1].start : lines.duration; s.dur = s.end - s.start; });
  for (const s of scenes) {
    s.words = words.filter((w) => w.line >= s.g0 && w.line < s.g0 + s.n).map((w) => ({ ...w, li: w.line - s.g0, s: w.s - s.start, e: w.e - s.start }));
    s.L = (i) => { const l = L[s.g0 + K.clamp(i, 0, s.n - 1)]; return l.start - s.start; };
    s.Le = (i) => { const l = L[s.g0 + K.clamp(i, 0, s.n - 1)]; return l.end - s.start; };
    s.at = (item) => {
      if (!item) return 0;
      const li = K.clamp(item.line || 0, 0, s.n - 1);
      if (item.word) {
        const n = norm(item.word);
        const hit = n && s.words.find((w) => w.li === li && norm(w.w).startsWith(n));
        if (hit) return hit.s;
      }
      return s.L(li);
    };
    // No empty openings: in scenes whose only visuals are their points / steps / shapes, a first item anchored more
    // than 1.5 s in comes in at 0.6 s instead (the screen was blank for 9 s in a real lesson, 2026-11-16).
    if (['concept', 'board', 'figure'].includes(s.sc.kind)) {
      const items = [...(s.sc.points || []), ...(s.sc.steps || []), ...(s.sc.shapes || [])];
      if (items.length) {
        const raw = s.at, first = items.reduce((a, it) => (raw(it) < raw(a) ? it : a));
        if (raw(first) > 1.5) s.at = (item) => (item === first ? 0.6 : raw(item));
      }
    }
  }
  return scenes;
}

// captions: "|" splits a line's caption into chunks, "@n" pins a chunk to spoken word n of that line
function buildCaptions(script, lines, words) {
  const out = []; let g = 0;
  for (const sc of script.scenes) for (const ln of sc.lines) {
    const L = lines.lines[g], lw = words.filter((w) => w.line === g), parts = String(ln.caps || ln.say).split('|').map((x) => x.trim()).filter(Boolean);
    const chunks = parts.map((p, k) => {
      let anchor = null, txt = p;
      const m = p.match(/^@(\d+)\s+(.*)$/); if (m) { anchor = +m[1]; txt = m[2]; }
      const s = anchor != null && lw[anchor] ? lw[anchor].s : lw.length ? lw[Math.min(lw.length - 1, Math.round(k * lw.length / parts.length))].s : L.start + (L.end - L.start) * k / parts.length;
      return { s, txt: txt.replace(/\*/g, '') };
    });
    chunks.forEach((c, k) => { c.e = k + 1 < chunks.length ? chunks[k + 1].s : L.end + 0.15; out.push(c); });
    g++;
  }
  return out;
}

function drawCaption(t) {
  const c = CAPS.find((x) => t >= x.s && t < x.e); if (!c) return;
  const size = LAY.portrait ? 46 : 44, maxW = K.W * (LAY.portrait ? 0.86 : 0.7);
  const lines = K.wrap(c.txt, maxW - 64, size, 500, false).slice(-2), lh = size * (LESSON.script.language === 'english' ? 1.35 : 1.5);
  const w = Math.max(...lines.map((l) => K.measure(l, size, 500, false))) + 64, h = lines.length * lh + 32;
  const x = (K.W - w) / 2, y = K.H - (LAY.portrait ? 300 : 158) - (lines.length - 1) * lh * 0.5;
  K.ctx.save(); K.rr(x, y, w, h, 20); K.ctx.fillStyle = 'rgba(27,32,51,.78)'; K.ctx.fill(); K.ctx.restore();
  lines.forEach((ln, i) => K.text(ln, K.W / 2, y + 16 + size * 0.95 + i * lh, { size, weight: 500, display: false, color: '#FCFCFC', align: 'center' }));
}

function background() {
  const c = K.ctx;
  c.setTransform(1, 0, 0, 1, 0, 0); c.globalAlpha = 1; c.fillStyle = K.C.bg; c.fillRect(0, 0, K.W, K.H);
  if (LESSON.grid) {
    c.strokeStyle = K.C.grid; c.lineWidth = 2;
    for (let x = 60; x < K.W; x += 60) { c.beginPath(); c.moveTo(x, 0); c.lineTo(x, K.H); c.stroke(); }
    for (let y = 60; y < K.H; y += 60) { c.beginPath(); c.moveTo(0, y); c.lineTo(K.W, y); c.stroke(); }
  }
}

function sceneState(s, i, t) {
  return { sc: s.sc, t: t - s.start, dur: s.dur, lang: LESSON.script.screen_lang || 'en', at: s.at, L: s.L, Le: s.Le,
    words: s.words, idx: i, total: SCENES.length, W: K.W, H: K.H, M: LAY.M, portrait: LAY.portrait, box: LAY,
    bk: LESSON.bk, grid: LESSON.grid, captions: LESSON.captions, chrome: !!LESSON.chrome };
}

// ---------- camera beats ----------
// A still frame for 15-30 s loses children. Every scene is cut into beats (a new line, or a point/step/shape that
// appears), merged when closer than 1.6 s and split when longer than 6 s. Each beat gets its own framing (a small
// punch-in towards a different part of the frame) that eases in over 0.6 s, plus a slow push inside the beat.
// Zoom stays ≤ 1.07 so nothing inside the layout margins is cropped. A pure function of t, like everything else.
const BEAT_MIN = 1.6, BEAT_MAX = 6, BEAT_SPLIT = 4.5;
const FRAMINGS = [[0, 0, 1], [-0.1, 0.04, 1.045], [0.09, -0.03, 1.03], [0.04, 0.05, 1.06], [-0.06, -0.02, 1.025]];

function beatsOf(s) {
  const ts = [0];
  for (let l = 1; l < s.n; l++) ts.push(s.L(l));
  for (const it of [...(s.sc.points || []), ...(s.sc.steps || []), ...(s.sc.shapes || []), ...(s.sc.moves || [])]) ts.push(s.at(it));
  const sorted = ts.filter((x) => x >= 0 && x < s.dur - 0.8).sort((a, b) => a - b);
  const merged = [];
  for (const x of sorted) if (!merged.length || x - merged[merged.length - 1] >= BEAT_MIN) merged.push(x);
  const out = [];
  merged.forEach((x, k) => {
    const end = k + 1 < merged.length ? merged[k + 1] : s.dur, len = end - x;
    const parts = len > BEAT_MAX ? Math.ceil(len / BEAT_SPLIT) : 1;
    for (let p = 0; p < parts; p++) out.push(x + (len * p) / parts);
  });
  return out;
}

function framing(s, k) {
  if (k <= 0) return { fx: 0, fy: 0, z: 1 };
  const f = FRAMINGS[((k + s.g0) % (FRAMINGS.length - 1)) + 1];
  return { fx: f[0], fy: f[1], z: f[2] };
}

function cameraOf(s, st) {
  if (!s.beats) s.beats = beatsOf(s);
  const B = s.beats; let k = 0;
  while (k + 1 < B.length && B[k + 1] <= st) k++;
  const prev = framing(s, k - 1), cur = framing(s, k);
  const e = k === 0 ? 1 : K.eio(K.prog(st, B[k], 0.6));
  const end = k + 1 < B.length ? B[k + 1] : s.dur, push = 1 + 0.012 * K.clamp((st - B[k]) / Math.max(0.5, end - B[k]));
  const fx = K.lerp(prev.fx, cur.fx, e), fy = K.lerp(prev.fy, cur.fy, e), z = K.lerp(prev.z, cur.z, e) * (k === 0 ? 1 : push);
  return { x: LAY.x + LAY.w * (0.5 + fx), y: LAY.y + LAY.h * (0.5 + fy), z };
}

function applyCamera(c, s, st) {
  // the player stops on check scenes: keep them still; solid scenes move their own 3D camera
  if (LESSON.camera === false || s.sc.kind === 'check' || s.sc.kind === 'solid') return;
  const cam = cameraOf(s, st);
  if (Math.abs(cam.z - 1) < 1e-4) return;
  c.translate(cam.x, cam.y); c.scale(cam.z, cam.z); c.translate(-cam.x, -cam.y);
}

// Returns false when the scene's LLM code threw on this frame: the caller repaints the frame from the template.
// (Only this frame: frames are captured in parallel browsers, so a scene must not switch modes part-way through.)
function drawScene(s, i, t, asTemplate = false) {
  const S = sceneState(s, i, t), c = K.ctx;
  const a = K.eo(K.prog(S.t, 0, 0.32)), dy = (1 - a) * 16;     // screenIn: fade up 8 px (16 at 2x)
  c.save(); c.globalAlpha = i === 0 ? 1 : a; c.translate(0, i === 0 ? 0 : dy);
  if (s.custom && !s.fallback && !asTemplate) {
    header(S, { noTitle: s.sc.kind === 'title' });   // a title scene draws its own big title
    c.save();
    if (!s.ownCamera) applyCamera(c, s, S.t);         // scenes that call A.camera() frame themselves
    let ok = true;
    try { s.custom(c, S.t, s.A); } catch (e) { ok = false; s.runtimeError = `${e && e.message || e} (t=${S.t.toFixed(2)})`; }
    c.restore(); c.restore();
    return ok;
  } else {
    applyCamera(c, s, S.t);
    TEMPLATES[s.sc.kind](S);
  }
  c.restore();
  return true;
}

function draw(t) {
  t = K.clamp(t, 0, DUR - 1e-4);
  // Start every frame from a clean context: LLM code that returns early between ctx.save() and ctx.restore() leaves
  // states (clips, alpha, transforms) on the stack, and they pile up over thousands of frames in one capture page.
  if (K.ctx.reset) K.ctx.reset();
  background();
  let i = SCENES.length - 1; while (i > 0 && SCENES[i].start > t) i--;
  if (!drawScene(SCENES[i], i, t)) { background(); drawScene(SCENES[i], i, t, true); }
  K.ctx.setTransform(1, 0, 0, 1, 0, 0); K.ctx.globalAlpha = 1;
  if (LESSON.captions) drawCaption(t);
}

function cues() {
  if (!LESSON.sfx) return [];
  const out = [];
  SCENES.forEach((s, i) => {
    if (i > 0) out.push({ t: s.start + 0.02, type: 'whoosh', gain: 0.12 });
    const sc = s.sc;
    [...(sc.points || []), ...(sc.steps || []), ...(sc.shapes || [])].forEach((it) => out.push({ t: s.start + s.at(it), type: 'pop', gain: 0.16 }));
    (sc.moves || []).forEach((m) => out.push({ t: s.start + s.at(m), type: ['revolve', 'unroll', 'orbit', 'cut'].includes(m.do) ? 'whoosh' : 'pop', gain: 0.12 }));
    if (sc.kind === 'check' && s.n > 1) out.push({ t: s.start + s.L(1), type: 'ding', gain: 0.3 });
  });
  return out.filter((c) => c.t < DUR - 0.05);
}

(async () => {
  try {
    LESSON = await getJSON('lesson.json');
    const [w, h] = LESSON.aspect === '9:16' ? [1080, 1920] : [1920, 1080];
    cv.width = w; cv.height = h;
    K.setup(cv.getContext('2d'), w, h);
    LAY = layout(w, h, LESSON.captions);
    const sample = 'Aa1 अआक्षज्ञ';
    await Promise.all(['500 40px Mukta', '400 40px Mukta', '700 40px Mukta', '600 40px "Baloo 2"', '700 40px "Baloo 2"', '800 40px "Baloo 2"']
      .map((f) => document.fonts.load(f, sample)));
    await K.loadImages();
    const lines = await getJSON('data/lines.json'), words = await getJSON('data/words.json');
    DUR = lines.duration;
    SCENES = buildTiming(LESSON.script, lines, words);
    if (SCENES.some((s) => s.sc.kind === 'solid')) await loadSolids();   // three.js only when a scene needs it
    CAPS = buildCaptions(LESSON.script, lines, words);
    // LLM-animation mode: compile + dry-run each scene's code; any problem → the template draws that scene
    for (const [i, s] of SCENES.entries()) {
      if (LESSON.mode !== 'llm' || !s.sc.custom_code || s.sc.kind === 'check' || s.sc.kind === 'solid') continue;
      try {
        s.custom = compile(s.sc.custom_code);
        s.ownCamera = /A\.camera\s*\(/.test(s.sc.custom_code);
        const S = sceneState(s, i, s.start); s.A = makeA(S);
        const err = dryRun(s.custom, S, s.A);
        if (err) s.fallback = err;
      } catch (e) { s.fallback = `compile: ${e && e.message || e}`; }
    }
    // maths: everything templates and custom code ask for, found by drawing every scene at its key moments
    for (const s of SCENES) [...sceneTex(s.sc), ...shapeTex(s.sc.shapes || [])].forEach(([l, c]) => K.wantTex(l, c));
    for (let pass = 0; pass < 3; pass++) {
      await K.prepareTex();
      SCENES.forEach((s, i) => { for (let k = 0; k <= 8; k++) { try { drawScene(s, i, s.start + s.dur * k / 8); } catch { } } for (let l = 0; l < s.n; l++) { try { drawScene(s, i, s.start + s.L(l) + 1.2); } catch { } } });
    }
    await K.prepareTex();
    OP.duration = () => DUR;
    OP.draw = draw;
    OP.frame = (t, q = 0.92, fmt = 'image/jpeg') => { draw(t); return cv.toDataURL(fmt, q); };
    OP.shots = () => SCENES.map((s) => ({ id: s.sc.id, at: +s.start.toFixed(3), end: +s.end.toFixed(3),
      note: `${s.sc.kind}${s.sc.kind === 'solid' ? (GL.ok ? ' · 3D' : ` · 3D OFF, 2D drawing: ${GL.error || 'no WebGL'}`) : ''}${s.custom ? (s.fallback ? ` · TEMPLATE FALLBACK: ${s.fallback}` : ' · llm animation') : ''}` }));
    OP.gl = () => ({ ...GL });
    OP.captions = () => CAPS.map((c) => ({ s: +c.s.toFixed(3), e: +c.e.toFixed(3), text: c.txt, miss: false }));
    OP.cues = () => cues().sort((a, b) => a.t - b.t);
    OP.ready = true;
    const q = new URLSearchParams(location.search);
    if (!q.has('capture')) {
      if (q.has('t')) draw(+q.get('t'));
      else {
        const audio = new Audio(LESSON.preview_audio || 'data/narration.wav'); let t0 = null;
        const btn = document.getElementById('play'); btn.hidden = false;
        btn.onclick = () => { btn.hidden = true; t0 = performance.now(); audio.currentTime = 0; audio.play().catch(() => {}); };
        const loop = (now) => { const t = t0 == null ? 0 : (now - t0) / 1000; draw(t); if (t0 != null && t > DUR) { t0 = null; btn.hidden = false; } requestAnimationFrame(loop); };
        requestAnimationFrame(loop);
      }
    }
  } catch (e) { OP.bootError = String(e && e.stack || e); }
})();
