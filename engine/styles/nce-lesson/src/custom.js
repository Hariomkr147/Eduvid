// LLM-written scene animations (spec 2026-11-12 §5): the model writes the body of draw(ctx, t, A).
// The code is compiled with the browser globals shadowed, dry-run at boot, and any scene that throws, is slow, or
// leaves nothing on screen falls back to its template (the render never fails because of one scene).
import * as K from './kit.js';

const SHADOW = ['window', 'document', 'fetch', 'XMLHttpRequest', 'globalThis', 'self', 'localStorage', 'setTimeout',
  'setInterval', 'requestAnimationFrame', 'WebSocket', 'importScripts', 'navigator', 'location'];

// LaTeX written in a JS string with single backslashes loses them: '\frac' becomes form-feed + 'rac', '\times' tab +
// 'imes'. Real LaTeX never contains these control characters, so turning them back is lossless.
const CTRL = { '\f': '\\f', '\t': '\\t', '\b': '\\b', '\r': '\\r', '\v': '\\v', '\n': '\\n' };
export const fixTex = (s) => String(s).replace(/[\f\t\b\r\v\n]/g, (c) => CTRL[c]);

// Model code computes radii like r * (1 - p) that land on -2e-16 at the end of an animation; the canvas throws on any
// negative radius. Clamp to 0 once, for every caller (it is never meaningful to draw a negative radius).
const P2D = CanvasRenderingContext2D.prototype;
if (!P2D.__nceClamped) {
  const arc0 = P2D.arc, ell0 = P2D.ellipse, rr0 = P2D.roundRect;
  P2D.arc = function (x, y, r, ...a) { return arc0.call(this, x, y, Math.max(0, r), ...a); };
  P2D.ellipse = function (x, y, rx, ry, ...a) { return ell0.call(this, x, y, Math.max(0, rx), Math.max(0, ry), ...a); };
  if (rr0) P2D.roundRect = function (x, y, w, h, r) { return rr0.call(this, x, y, w, h, typeof r === 'number' ? Math.max(0, r) : r); };
  P2D.__nceClamped = true;
}

export function compile(code) {
  // eslint-disable-next-line no-new-func
  const f = new Function('ctx', 't', 'A', ...SHADOW, '"use strict";\n' + code);
  return (ctx, t, A) => f(ctx, t, A, ...SHADOW.map(() => undefined));
}

// A: the helper API documented to the model in services/studio/studio/prompts.py (CUSTOM_API). Keep them in sync.
// gradient stops: ['#fff', '#000'] spread evenly, or [[0, '#fff'], [0.7, '#888'], [1, '#000']]
function addStops(g, stops) {
  const list = Array.isArray(stops) && stops.length ? stops.slice(0, 12) : ['#ffffff', '#000000'];
  list.forEach((s, k) => {
    const [at, col] = Array.isArray(s) ? s : [list.length > 1 ? k / (list.length - 1) : 0, s];
    try { g.addColorStop(K.clamp(+at || 0), String(col)); } catch { /* a bad colour string is skipped */ }
  });
  return g;
}

export function makeA(S) {
  const norm = (w) => String(w).toLowerCase().replace(/[^\p{L}\p{M}\p{N}']+/gu, '');
  // the stage: full width, from just under the scene heading to the bottom of the frame (the LLM scene owns it)
  const top = Math.max(0, S.box.y - 20), stage = { x: 0, y: top, w: S.W, h: S.H - top };
  const scx = stage.x + stage.w / 2, scy = stage.y + stage.h / 2;
  // a framing: zoom 1-1.8, centre kept so the camera window (stage.w/zoom × stage.h/zoom) never leaves the stage
  const frame = (k) => {
    const z = K.clamp(Number.isFinite(+k.zoom) ? +k.zoom : 1, 1, 1.8), hw = stage.w / (2 * z), hh = stage.h / (2 * z);
    return { x: K.clamp(Number.isFinite(+k.x) ? +k.x : scx, stage.x + hw, stage.x + stage.w - hw),
      y: K.clamp(Number.isFinite(+k.y) ? +k.y : scy, stage.y + hh, stage.y + stage.h - hh), z };
  };
  return {
    W: S.W, H: S.H, box: S.box, stage, dur: S.dur, c: K.C,
    // camera: keys [{at, x, y, zoom, len?}] = "at time `at`, glide (len s, default .7) until point (x, y) is at the
    // stage centre, magnified `zoom`". Clips to the stage so the heading never moves. Call it before drawing.
    camera: (t, keys) => {
      const ks = (Array.isArray(keys) ? keys : []).filter((k) => k && typeof k === 'object').slice(0, 16)
        .map((k) => ({ ...k, at: Number.isFinite(+k.at) ? +k.at : 0 })).sort((a, b) => a.at - b.at);
      let cur = { x: scx, y: scy, z: 1 };
      if (ks.length) {
        let j = 0; while (j + 1 < ks.length && ks[j + 1].at <= t) j++;
        const to = frame(ks[j]), from = j > 0 ? frame(ks[j - 1]) : to;
        const e = j > 0 ? K.eio(K.prog(t, ks[j].at, Number.isFinite(+ks[j].len) ? +ks[j].len : 0.7)) : 1;
        cur = { x: K.lerp(from.x, to.x, e), y: K.lerp(from.y, to.y, e), z: K.lerp(from.z, to.z, e) };
      }
      const c = K.ctx;
      c.beginPath(); c.rect(stage.x, stage.y, stage.w, stage.h); c.clip();
      c.translate(scx, scy); c.scale(cur.z, cur.z); c.translate(-cur.x, -cur.y);
      return { x: cur.x, y: cur.y, zoom: cur.z };
    },
    // paint the stage (a colour, or a gradient from A.grad / A.radial); call it before A.camera
    bg: (fill) => { const c = K.ctx; c.save(); c.fillStyle = fill || K.C.paper; c.fillRect(stage.x, stage.y, stage.w, stage.h); c.restore(); },
    grad: (x0, y0, x1, y1, stops) => addStops(K.ctx.createLinearGradient(+x0 || 0, +y0 || 0, +x1 || 0, +y1 || 0), stops),
    radial: (x, y, r, stops) => addStops(K.ctx.createRadialGradient(+x || 0, +y || 0, 0, +x || 0, +y || 0, Math.max(1, +r || 1)), stops),
    L: (i) => S.L(i), Le: (i) => S.Le(i),
    T: (word, i) => {
      const n = norm(word);
      const hit = S.words.find((w) => (i == null || w.li === i) && norm(w.w).startsWith(n));
      return hit ? hit.s : (i != null ? S.L(i) : 0);
    },
    clamp: K.clamp, prog: K.prog, eo: K.eo, eio: K.eio, spring: K.spring, lerp: K.lerp, rand: K.rand,
    pop: (t, t0) => (t < t0 ? 0 : K.spring(K.prog(t, t0, 0.45))), fade: K.fade,
    text: (s, x, y, o = {}) => K.text(s, x, y, o),
    tex: (latex, x, y, o = {}) => K.tex(fixTex(latex), x, y, o),
    line: K.line, arrow: K.arrow, circle: K.circle, arc: K.arc,
    rect: (x, y, w, h, o = {}) => K.rect(x, y, w, h, o),
    poly: (pts, o = {}) => K.polyline(pts, { close: true, ...o }), curve: (pts, o = {}) => K.polyline(pts, o),
    card: (x, y, w, h, o = {}) => K.card(x, y, w, h, o), pill: (s, x, y, o = {}) => K.pill(s, x, y, o),
    chip: (n, x, y, o = {}) => K.chip(n, x, y, o), bk: (x, y, h, pose) => K.bk(x, y, h, pose),
    bubble: (s, x, y, o = {}) => K.bubble(s, x, y, o),
  };
}

// run fn at several times; returns '' if fine or the error text
export function dryRun(fn, S, A) {
  const times = [0, 0.15, 0.35, 0.5, 0.75, 0.95].map((k) => k * S.dur);
  for (let i = 0; i < 12; i++) { try { times.push(S.L(i)); } catch { break; } }
  // the first call pays one-time costs (font shaping, image decode): run it untimed, then time the rest
  let slow = 0, worst = 0;
  for (const [k, t] of times.entries()) {
    const t0 = performance.now();
    K.ctx.save();
    try { fn(K.ctx, t, A); } catch (e) { K.ctx.restore(); return `${e && e.message || e} (t=${t.toFixed(2)})`; }
    K.ctx.restore();
    const ms = performance.now() - t0;
    if (k > 0 && ms > 400) { slow++; worst = Math.max(worst, ms); }
  }
  return slow >= 2 ? `too slow: ${worst.toFixed(0)} ms for one frame` : '';
}
