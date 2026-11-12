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

export function compile(code) {
  // eslint-disable-next-line no-new-func
  const f = new Function('ctx', 't', 'A', ...SHADOW, '"use strict";\n' + code);
  return (ctx, t, A) => f(ctx, t, A, ...SHADOW.map(() => undefined));
}

// A: the helper API documented to the model in services/studio/studio/prompts.py (CUSTOM_API). Keep them in sync.
export function makeA(S) {
  const norm = (w) => String(w).toLowerCase().replace(/[^\p{L}\p{M}\p{N}']+/gu, '');
  return {
    W: S.W, H: S.H, box: S.box, dur: S.dur, c: K.C,
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
