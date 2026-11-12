// NCE kit for video frames: tokens copied from the NCE design kit's theme.css (design_ref.md §2, §11) and the
// drawing primitives every scene uses. Everything draws on one 2D canvas; every function is a pure function of its
// arguments, so any frame can be drawn at any time in any order (capture renders frames in parallel browsers).
export const C = {
  bg: '#FCFCFC', surface: '#FFFFFF', surface2: '#F4F5F9', line: '#E6E7EE', line2: '#DEE0F1', press: '#D6D4E3',
  grid: '#EEEEF2', ink: '#1B2033', ink2: '#394058', muted: '#6B7189', faint: '#A0A5B8',
  brand: '#5A4499', brandSoft: '#EFEBFA', primary: '#2260E9', primaryDeep: '#1846B3', primarySoft: '#EEF3FE',
  indigo: '#525EC0', accentInk: '#17377B', chip: '#E8EDFA', chipInk: '#525EC0', start: '#6A4FC4', startSoft: '#F0ECFB',
  step: '#2260E9', frame: '#DEE0F1', paper: '#F7F5F0',
  good: '#23A160', goodBg: '#E3FAEE', goodLine: '#9FDDBA', goodInk: '#11663B',
  bad: '#CF4038', noteBg: '#FBF2E5', noteLine: '#F0DCBF', noteInk: '#99520F',
  infoBg: '#EEF2FD', infoLine: '#CCD8F7', infoInk: '#1E3F99', flame: '#F2701A', flameBg: '#FFF1E6',
  gold: '#F5B700', goldDeep: '#F0A800', goldBg: '#FFF8E1', goldLine: '#F1D48A', goldInk: '#8A5A00',
};
export const UI = '"Mukta", "Nirmala UI", "Noto Sans Devanagari", sans-serif';
export const DISPLAY = '"Baloo 2", "Mukta", "Nirmala UI", "Noto Sans Devanagari", sans-serif';
export const NAMED = { ink: C.ink, primary: C.primary, start: C.start, good: C.good, flame: C.flame, gold: C.goldDeep, muted: C.muted };

export let ctx = null, W = 1920, H = 1080;
export function setup(c, w, h) { ctx = c; W = w; H = h; }

// ---------- maths of motion (design_ref §8) ----------
export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a, b, x) => a + (b - a) * x;
export const eo = (x) => 1 - Math.pow(1 - clamp(x), 3);
export const eio = (x) => { x = clamp(x); return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; };
export const prog = (t, start, len) => clamp((t - start) / Math.max(1e-6, len));
// cubic-bezier(.3,1.5,.5,1)-like hop: overshoots a little, settles at 1
export const spring = (x) => { x = clamp(x) - 1; return 1 + 2.2 * x * x * x + 1.2 * x * x; };   // ease-out-back
export const pop = (t, t0, len = 0.3) => (t < t0 ? 0 : 0.96 + 0.04 * eo(prog(t, t0, len)));   // "pop": scale from .96
export const fade = (t, t0, len = 0.3) => eo(prog(t, t0, len));
export const rand = (i) => { const x = Math.sin(i * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };

// ---------- shapes ----------
export function rr(x, y, w, h, r) {
  r = Math.max(0, Math.min(r, w / 2, h / 2));
  ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}

// a card that "sits on a flat ledge" (design_ref §4): no blur, a solid coloured strip under it
export function card(x, y, w, h, o = {}) {
  const r = o.radius ?? 28, ledge = o.ledge ?? 6;
  ctx.save(); ctx.globalAlpha *= o.alpha ?? 1;
  if (o.shadow) { ctx.shadowColor = 'rgba(23,30,60,.08)'; ctx.shadowBlur = 40; ctx.shadowOffsetY = 12; }
  if (ledge) { rr(x, y + ledge, w, h, r); ctx.fillStyle = o.ledgeColor || C.line2; ctx.fill(); }
  ctx.shadowColor = 'transparent';
  rr(x, y, w, h, r); ctx.fillStyle = o.fill || C.surface; ctx.fill();
  ctx.lineWidth = o.border ?? 2; ctx.strokeStyle = o.stroke || C.line; ctx.stroke();
  ctx.restore();
}

// figure card: lavender frame (radius 16 → 32 at 2x) holding warm paper (radius 11 → 22), optional graph paper
export function figureCard(x, y, w, h, o = {}) {
  ctx.save(); ctx.globalAlpha *= o.alpha ?? 1;
  rr(x, y, w, h, 32); ctx.fillStyle = C.frame; ctx.fill();
  const p = 16; rr(x + p, y + p, w - 2 * p, h - 2 * p, 22); ctx.fillStyle = C.paper; ctx.fill();
  if (o.grid !== false) {
    ctx.save(); rr(x + p, y + p, w - 2 * p, h - 2 * p, 22); ctx.clip();
    ctx.strokeStyle = 'rgba(160,165,184,.18)'; ctx.lineWidth = 2;
    const s = 60;
    for (let gx = x + p + s; gx < x + w - p; gx += s) { ctx.beginPath(); ctx.moveTo(gx, y + p); ctx.lineTo(gx, y + h - p); ctx.stroke(); }
    for (let gy = y + p + s; gy < y + h - p; gy += s) { ctx.beginPath(); ctx.moveTo(x + p, gy); ctx.lineTo(x + w - p, gy); ctx.stroke(); }
    ctx.restore();
  }
  ctx.restore();
  return { x: x + p, y: y + p, w: w - 2 * p, h: h - 2 * p };
}

export function font(size, weight = 600, display = true) { return `${weight} ${size}px ${display ? DISPLAY : UI}`; }

export function text(str, x, y, o = {}) {
  str = String(str ?? '');
  ctx.save();
  ctx.globalAlpha *= o.alpha ?? 1;
  ctx.font = font(o.size || 40, o.weight || (o.display === false ? 500 : 700), o.display !== false);
  ctx.fillStyle = o.color || C.ink; ctx.textAlign = o.align || 'left'; ctx.textBaseline = o.baseline || 'alphabetic';
  if (o.maxW) { const w = ctx.measureText(str).width; if (w > o.maxW) { const k = o.maxW / w; ctx.translate(x, y); ctx.scale(k, k); ctx.fillText(str, 0, 0); ctx.restore(); return; } }
  ctx.fillText(str, x, y);
  ctx.restore();
}

// word-wrap by measured width; returns lines. Keeps Devanagari clusters intact (splits on spaces only).
export function wrap(str, maxW, size, weight = 500, display = false) {
  ctx.save(); ctx.font = font(size, weight, display);
  const words = String(str ?? '').split(/\s+/).filter(Boolean), lines = [];
  let cur = '';
  for (const w of words) {
    const t = cur ? cur + ' ' + w : w;
    if (ctx.measureText(t).width <= maxW || !cur) cur = t; else { lines.push(cur); cur = w; }
  }
  if (cur) lines.push(cur);
  ctx.restore();
  return lines;
}

export function para(str, x, y, maxW, o = {}) {
  const size = o.size || 40, lh = o.lh || size * 1.4, lines = wrap(str, maxW, size, o.weight || 500, !!o.display).slice(0, o.maxLines || 99);
  lines.forEach((ln, i) => text(ln, x, y + i * lh, { ...o, size, display: !!o.display, weight: o.weight || 500 }));
  return lines.length * lh;
}

export function measure(str, size, weight = 600, display = true) { ctx.save(); ctx.font = font(size, weight, display); const w = ctx.measureText(String(str)).width; ctx.restore(); return w; }

export function pill(str, x, y, o = {}) {
  const size = o.size || 30, padX = size * 0.75, h = size * 1.75, w = measure(str, size, 600) + 2 * padX;
  const tone = { brand: [C.brandSoft, C.brand], level: [C.primarySoft, C.primary], good: [C.goodBg, C.goodInk],
    gold: [C.goldBg, C.goldInk], flame: [C.flameBg, C.flame], ink: [C.surface2, C.ink2] }[o.tone || 'brand'];
  const ax = o.align === 'center' ? x - w / 2 : o.align === 'right' ? x - w : x;
  ctx.save(); ctx.globalAlpha *= o.alpha ?? 1;
  rr(ax, y, w, h, h / 2); ctx.fillStyle = tone[0]; ctx.fill();
  ctx.restore();
  text(str, ax + padX, y + h * 0.68, { size, weight: 600, color: tone[1], alpha: o.alpha });
  return w;
}

export function chip(n, x, y, o = {}) {
  const r = o.r || 30;
  ctx.save(); ctx.globalAlpha *= o.alpha ?? 1;
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fillStyle = o.solid ? (o.color || C.primary) : C.chip; ctx.fill();
  ctx.restore();
  text(n, x, y + r * 0.36, { size: r * 1.05, weight: 700, color: o.solid ? '#fff' : (o.color || C.chipInk), align: 'center', alpha: o.alpha });
}

// line/arrow/circle/poly with partial "being drawn" progress
export function stroke(path, o = {}) {
  ctx.save(); ctx.globalAlpha *= o.alpha ?? 1;
  ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  ctx.lineWidth = o.width || 5; ctx.strokeStyle = o.color || C.ink;
  if (o.dash) ctx.setLineDash(o.dash);
  path();
  if (o.fill) { ctx.fillStyle = o.fill; ctx.fill(); }
  ctx.stroke(); ctx.restore();
}
function polyLen(pts) { let L = 0; for (let i = 1; i < pts.length; i++) L += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); return L; }
export function polyline(pts, o = {}) {
  if (!pts || pts.length < 2) return;
  const p = clamp(o.progress ?? 1); if (p <= 0) return;
  const all = o.close ? [...pts, pts[0]] : pts, L = polyLen(all) * p;
  stroke(() => {
    ctx.beginPath(); ctx.moveTo(all[0][0], all[0][1]); let acc = 0;
    for (let i = 1; i < all.length; i++) {
      const d = Math.hypot(all[i][0] - all[i - 1][0], all[i][1] - all[i - 1][1]);
      if (acc + d >= L) { const k = (L - acc) / (d || 1); ctx.lineTo(lerp(all[i - 1][0], all[i][0], k), lerp(all[i - 1][1], all[i][1], k)); break; }
      ctx.lineTo(all[i][0], all[i][1]); acc += d;
    }
  }, { ...o, fill: p >= 1 ? o.fill : null });
}
export function line(x1, y1, x2, y2, o = {}) { polyline([[x1, y1], [x2, y2]], o); }
export function arrow(x1, y1, x2, y2, o = {}) {
  const p = clamp(o.progress ?? 1); if (p <= 0) return;
  const ex = lerp(x1, x2, p), ey = lerp(y1, y2, p);
  line(x1, y1, ex, ey, o);
  const a = Math.atan2(y2 - y1, x2 - x1), s = (o.width || 5) * 4;
  polyline([[ex - s * Math.cos(a - 0.45), ey - s * Math.sin(a - 0.45)], [ex, ey], [ex - s * Math.cos(a + 0.45), ey - s * Math.sin(a + 0.45)]], { ...o, progress: 1, dash: null });
}
export function arc(x, y, r, a0, a1, o = {}) {
  const p = clamp(o.progress ?? 1); if (p <= 0) return;
  stroke(() => { ctx.beginPath(); ctx.arc(x, y, r, a0, a0 + (a1 - a0) * p); }, { ...o, fill: p >= 1 ? o.fill : null });
}
export function circle(x, y, r, o = {}) { arc(x, y, r, -Math.PI / 2, Math.PI * 1.5, o); }
export function rect(x, y, w, h, o = {}) {
  if (o.radius) { const p = clamp(o.progress ?? 1); if (p <= 0) return; stroke(() => rr(x, y, w, h, o.radius), { ...o, alpha: (o.alpha ?? 1) * p }); return; }
  polyline([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], { ...o, close: true });
}
export function ellipse(x, y, rx, ry, o = {}, a0 = 0, a1 = Math.PI * 2) {
  const p = clamp(o.progress ?? 1); if (p <= 0) return;
  stroke(() => { ctx.beginPath(); ctx.ellipse(x, y, Math.max(0.1, rx), Math.max(0.1, ry), 0, a0, a0 + (a1 - a0) * p); }, { ...o, fill: p >= 1 ? o.fill : null });
}

// ---------- Bal Krishna (design_ref §1: the guide; a white bubble, never lectures) ----------
const BK = {};
export async function loadImages() {
  await Promise.all(['calm', 'wave'].map((k) => new Promise((res) => { const im = new Image(); im.onload = () => { BK[k] = im; res(); }; im.onerror = res; im.src = `assets/bk-${k}.png`; })));
}
export function bk(x, y, h, pose = 'calm', o = {}) {
  const im = BK[pose] || BK.calm; if (!im) return;
  const w = h * im.width / im.height;
  ctx.save(); ctx.globalAlpha *= o.alpha ?? 1;
  ctx.shadowColor = 'rgba(23,30,60,.16)'; ctx.shadowBlur = 18; ctx.shadowOffsetY = 8;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(im, x - w / 2, y - h - (o.hop || 0), w, h);
  ctx.restore();
}
// speech bubble with a small tail; (x, y) = tail tip; side = where the bubble sits relative to the tip
export function bubble(str, x, y, o = {}) {
  const size = o.size || 38, maxW = o.maxW || 620, pad = size * 0.7;
  const lines = wrap(str, maxW - 2 * pad, size, 500, false), lh = size * 1.45;
  const w = Math.min(maxW, Math.max(...lines.map((l) => measure(l, size, 500, false))) + 2 * pad), h = lines.length * lh + 2 * pad - (lh - size) ;
  const side = o.side || 'left';
  const bx = side === 'left' ? x - w - 24 : side === 'right' ? x + 24 : x - w / 2, by = side === 'top' ? y - h - 24 : y - h * 0.7;
  ctx.save(); ctx.globalAlpha *= o.alpha ?? 1;
  ctx.shadowColor = 'rgba(23,30,60,.08)'; ctx.shadowBlur = 40; ctx.shadowOffsetY = 12;
  rr(bx, by, w, h, 32); ctx.fillStyle = C.surface; ctx.fill();
  ctx.beginPath();
  if (side === 'left') { ctx.moveTo(bx + w - 2, by + h * 0.55); ctx.lineTo(x, y); ctx.lineTo(bx + w - 2, by + h * 0.55 + 34); }
  else if (side === 'right') { ctx.moveTo(bx + 2, by + h * 0.55); ctx.lineTo(x, y); ctx.lineTo(bx + 2, by + h * 0.55 + 34); }
  else { ctx.moveTo(x - 20, by + h - 2); ctx.lineTo(x, y); ctx.lineTo(x + 20, by + h - 2); }
  ctx.fill();
  ctx.restore();
  lines.forEach((ln, i) => text(ln, bx + pad, by + pad + size * 0.85 + i * lh, { size, weight: 500, display: false, color: C.ink2, alpha: o.alpha }));
  return { x: bx, y: by, w, h };
}

// ---------- maths (MathJax SVG → image, prepared before frames are drawn) ----------
const TEX = new Map();
const pending = new Set();
export function texKey(latex, color) { return `${color}|${latex}`; }
export function wantTex(latex, color = C.ink) { const k = texKey(latex, color); if (!TEX.has(k)) pending.add(k); return k; }
export async function prepareTex() {
  if (!pending.size) return;
  await window.MathJax.startup.promise;
  const jobs = [...pending].map(async (k) => {
    pending.delete(k);
    const bar = k.indexOf('|'), color = k.slice(0, bar), latex = k.slice(bar + 1);
    try {
      const node = window.MathJax.tex2svg(latex, { display: true });
      const svg = node.querySelector('svg');
      if (!svg || node.querySelector('[data-mjx-error], merror')) throw new Error('bad latex');
      const exW = parseFloat(svg.getAttribute('width')), exH = parseFloat(svg.getAttribute('height'));
      const valign = parseFloat((svg.getAttribute('style') || '').match(/vertical-align:\s*(-?[\d.]+)ex/)?.[1] || 0);
      svg.setAttribute('color', color); svg.style.color = color;
      let xml = new XMLSerializer().serializeToString(svg).replace(/currentColor/g, color);
      const big = 8; // rasterise large so scaling stays crisp
      xml = xml.replace(/width="[^"]+"/, `width="${exW * big * 8}px"`).replace(/height="[^"]+"/, `height="${exH * big * 8}px"`);
      const im = new Image();
      await new Promise((res, rej) => { im.onload = res; im.onerror = rej; im.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(xml); });
      TEX.set(k, { im, exW, exH, valign });
    } catch (e) { TEX.set(k, { error: String(e), latex }); }
  });
  await Promise.all(jobs);
}
// draw maths with its x-height scaled to `size` px (1ex ≈ 0.45 × font size). Falls back to plain text.
export function tex(latex, x, y, o = {}) {
  const size = o.size || 52, color = o.color || C.ink, k = texKey(latex, color), m = TEX.get(k);
  if (!m) { pending.add(k); return { w: 0, h: 0 }; }
  if (m.error) { text(latex, x, y, { size: size * 0.8, color, align: o.align, display: false, alpha: o.alpha }); return { w: measure(latex, size * 0.8, 500, false), h: size }; }
  const ex = size * 0.45, w = m.exW * ex, h = m.exH * ex;
  const ax = o.align === 'center' ? x - w / 2 : o.align === 'right' ? x - w : x;
  const reveal = clamp(o.progress ?? 1); if (reveal <= 0) return { w, h };
  ctx.save(); ctx.globalAlpha *= o.alpha ?? 1;
  const top = y - h + (-m.valign) * ex; // y is the baseline
  if (reveal < 1) { ctx.beginPath(); ctx.rect(ax - 4, top - 10, (w + 8) * reveal, h + 20); ctx.clip(); }
  ctx.drawImage(m.im, ax, top, w, h);
  ctx.restore();
  return { w, h, top };
}
export function texSize(latex, size, color = C.ink) { const m = TEX.get(texKey(latex, color)); if (!m || m.error) return { w: measure(latex, size * 0.8, 500, false), h: size }; const ex = size * 0.45; return { w: m.exW * ex, h: m.exH * ex }; }

// ---------- icons (design kit icons.js, stroke 2.2 on a 24 grid) ----------
export function icon(name, x, y, s, color) {
  ctx.save(); ctx.translate(x - s / 2, y - s / 2); ctx.scale(s / 24, s / 24);
  ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  if (name === 'check') { ctx.lineWidth = 3; ctx.stroke(new Path2D('M5 12.5l4.5 4.5L19 7.5')); }
  else if (name === 'x') { ctx.lineWidth = 3; ctx.stroke(new Path2D('M7 7l10 10M17 7L7 17')); }
  else if (name === 'info') { ctx.lineWidth = 2.6; ctx.stroke(new Path2D('M12 11v6M12 7.5v.01')); }
  else if (name === 'flame') ctx.fill(new Path2D('M12.6 2.2c.3 2.6-.7 4.3-2 5.9-1.3 1.6-2.9 3.1-2.9 5.6 0 1.3.5 2.4 1.3 3.2-.2-1.7.6-3 1.8-4 .3 1.6 1.5 2.4 2.6 3.2 1.1.8 2 1.6 2 3.1 0 .6-.1 1.1-.4 1.6 2.4-1 4-3.3 4-6 0-3.4-2-5.8-3.5-7.5-1-1.1-1.9-2.2-2.9-5.1z'));
  else if (name === 'star') ctx.fill(new Path2D('M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4l-5.9 3.1 1.2-6.5L2.5 9.4l6.6-.9z'));
  else if (name === 'pause') { ctx.lineWidth = 2.6; ctx.stroke(new Path2D('M9 6v12M15 6v12')); }
  ctx.restore();
}
export function iconCircle(name, x, y, r, bg, fg) { ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fillStyle = bg; ctx.fill(); icon(name, x, y, r * 1.2, fg); }
