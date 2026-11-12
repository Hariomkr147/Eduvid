// WHY IS THE AREA OF A CIRCLE πr²? : the shot list (Paper Atlas, kinetic). Everything is cut paper on parchment.
// The proof: slice the circle into n wedges, flip every other one, line them up → a bumpy parallelogram that becomes a
// rectangle as n grows: height r, width = half the circumference = πr, area = πr · r = πr².
// A shot: { id, at, cam, zoom, note, draw(lt, d, t) } · lt = time in shot, d = shot length. Pure functions of time.
import { ctx, W, H, TAU, clamp, lerp, seg, eo, eio, eob, rr, circle } from './core/lib.js';
import { L, Wd, T, lineWords } from './core/timing.js';
import * as K from './core/kit.js';
const { P, cut, P_rr, P_poly, P_circ } = K;
const SERIF = 'Caladea, Cambria, Georgia, serif';
const PI = Math.PI;

// ═══════════════ geometry ═══════════════
const R = 270, CX = 540, CY = 860;                 // the circle
const YB = 1040, YT = YB - R;                      // the row / rectangle: bottom and top edges
const RL = 540 - PI * R / 2, RRt = 540 + PI * R / 2; // the rectangle's left / right edges (width πr)
const UP = P.royal, DN = P.stone;                  // even wedges (point up in the row) / odd wedges (point down)
const SEED = 21;                                   // one parchment for the whole proof, so cuts feel continuous
const A = (n) => TAU / n;
const col = (i) => (i % 2 ? DN : UP);

/** wedge i of n inside the circle; spin = whole-circle rotation, gap = push outward along its middle */
function circState(i, n, spin = 0, gap = 0) { const rot = i * A(n) + spin, dir = rot - PI / 2; return { x: CX + Math.cos(dir) * gap, y: CY + Math.sin(dir) * gap, rot }; }
/** wedge i of n in the row: even ones stand on the bottom edge pointing up, odd ones hang from the top, flipped */
function rowState(i, n) { const s = R * Math.sin(A(n) / 2), x0 = 540 - (n + 1) * s / 2, up = i % 2 === 0; return { x: x0 + s + i * s, y: up ? YB : YT, rot: up ? 0 : PI }; }
/** blend two wedge states (rotation takes the short way round); lift = hop height for a kinetic arc */
function mix(a, b, p, lift = 0) { let r1 = b.rot; r1 += TAU * Math.round((a.rot - r1) / TAU); return { x: lerp(a.x, b.x, p), y: lerp(a.y, b.y, p) - lift * Math.sin(PI * clamp(p)), rot: lerp(a.rot, r1, p) }; }

/** one cut-paper wedge (apex at the state point, crust arc away from it). o = { crust: 0..1, crustCol, sy } */
function wedge(st, n, fill, o = {}) {
  const a = A(n);
  const path = () => { ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, R, -PI / 2 - a / 2, -PI / 2 + a / 2); ctx.closePath(); };
  ctx.save(); ctx.translate(st.x, st.y); ctx.rotate(st.rot); if (o.sy) ctx.scale(1, o.sy);
  cut(path, fill, { shadow: n <= 8 ? 0.8 : n <= 16 ? 0.5 : 0.22, edge: n <= 8 ? 5 : n <= 16 ? 3 : n <= 32 ? 1.6 : 0.9 });
  if (o.crust > 0) { ctx.beginPath(); ctx.arc(0, 0, R - 5, -PI / 2 - a / 2, -PI / 2 + a / 2); ctx.globalAlpha = clamp(o.crust); ctx.strokeStyle = o.crustCol || P.crimson; ctx.lineWidth = 10; ctx.stroke(); ctx.globalAlpha = 1; }
  ctx.restore();
}
/** all n wedges in the row (o.clip = trim to the exact πr × r rectangle; o.crustUp / crustDn = crust highlight) */
function row(n, o = {}) {
  ctx.save();
  if (o.clip) { const pad = 8 * (1 - clamp(o.clip)); ctx.beginPath(); ctx.rect(RL - pad - 60 * (1 - clamp(o.clip)), YT - 40, RRt - RL + 2 * pad + 120 * (1 - clamp(o.clip)), R + 80); ctx.clip(); }
  ctx.translate(540, (YT + YB) / 2); ctx.scale(o.sx || 1, o.sy || 1); ctx.translate(-540, -(YT + YB) / 2);
  for (let i = 0; i < n; i++) wedge(rowState(i, n), n, col(i), { crust: i % 2 ? o.crustDn : o.crustUp, crustCol: i % 2 ? P.sepia : P.crimson });
  ctx.restore();
}
/** the finished rectangle (64 thin wedges trimmed to πr × r) + optional crimson wash for "area" */
function rect(o = {}) {
  row(64, { clip: 1, crustUp: o.crustUp });
  if (o.wash > 0) { ctx.save(); ctx.globalAlpha = 0.32 * clamp(o.wash); ctx.fillStyle = P.crimson; ctx.fillRect(RL, YT, RRt - RL, R); ctx.restore(); }
  if (o.outline > 0) traceRect(o.outline);
}
/** crimson outline drawn round the rectangle, p 0..1 (clockwise from top-left) */
function traceRect(p, w = 9) {
  const pts = [[RL, YT], [RRt, YT], [RRt, YB], [RL, YB], [RL, YT]], per = 2 * (RRt - RL) + 2 * R; let left = per * clamp(p);
  ctx.beginPath(); ctx.moveTo(RL, YT);
  for (let i = 1; i < pts.length && left > 0; i++) { const l = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]), k = Math.min(1, left / l); ctx.lineTo(lerp(pts[i - 1][0], pts[i][0], k), lerp(pts[i - 1][1], pts[i][1], k)); left -= l; }
  ctx.strokeStyle = P.crimson; ctx.lineWidth = w; ctx.lineJoin = 'round'; ctx.lineCap = 'round'; ctx.stroke();
}
/** a measuring brace: crimson line with end ticks, grown from (x0, y0) to (x1, y1) by p */
function brace(x0, y0, x1, y1, p) {
  if (p <= 0) return; const x = lerp(x0, x1, clamp(p)), y = lerp(y0, y1, clamp(p)), ang = Math.atan2(y1 - y0, x1 - x0), nx = -Math.sin(ang) * 20, ny = Math.cos(ang) * 20;
  ctx.strokeStyle = P.crimson; ctx.lineWidth = 8; ctx.lineCap = 'round';
  ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x, y); ctx.moveTo(x0 - nx, y0 - ny); ctx.lineTo(x0 + nx, y0 + ny); if (p >= 1) { ctx.moveTo(x1 - nx, y1 - ny); ctx.lineTo(x1 + nx, y1 + ny); } ctx.stroke();
}
/** a big crimson rubber-stamp formula on a paper card */
function stamp(text, x, y, sc = 1, rot = -0.06, size = 130) {
  if (sc <= 0) return; ctx.save(); ctx.translate(x, y); ctx.rotate(rot); ctx.scale(sc, sc); ctx.font = `700 ${size}px ${SERIF}`;
  const w = ctx.measureText(text).width + 110, h = size * 1.45;
  cut(P_rr(-w / 2, -h / 2, w, h, 16), '#F3E9D2', { shadow: 0.9, edge: 0 });
  rr(-w / 2 + 16, -h / 2 + 16, w - 32, h - 32, 10); ctx.strokeStyle = P.crimson; ctx.lineWidth = 8; ctx.stroke();
  ctx.fillStyle = P.crimson; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(text, 0, 8); ctx.restore();
}
/** a formula tile (paper slip, bigger serif) */
const tile = (text, x, y, sc = 1, rot = 0, size = 96) => K.slip(text, x, y, sc, rot, size);
/** big ink letter label (r, πr) on paper */
const tag = (text, x, y, sc = 1) => K.slip(text, x, y, sc, 0.02, 72);
const solid = (a = 1) => cut(P_circ(CX, CY, R), UP, { shadow: a, edge: 6 });

// time of the k-th exact occurrence of a word in a line (Wd only finds the first, by prefix)
const nrm = (w) => String(w).toLowerCase().replace(/[^\p{L}\p{M}\p{N}']+/gu, '');
function Wn(word, line, k = 0) { const h = lineWords(line).filter((w) => nrm(w.w) === word); if (!h.length) throw new Error(`word "${word}" not in line ${line}`); return h[Math.min(k, h.length - 1)].s; }

export function buildShots() {
  const S = [], CUES = [], add = (o) => (S.push(o), o), cue = (t, type, o = {}) => CUES.push({ t: +Math.max(0, t).toFixed(3), type, ...o });
  const cutAt = (i) => (i === 0 ? 0 : L(i) - 0.08);
  const shotLen = (i) => (i + 1 < T.lines.length ? cutAt(i + 1) : T.dur) - cutAt(i);
  const CAM = [540, 880];

  // ── 1 · HOOK: a paper circle; "area?" then the πr² stamp slams down ─────────────
  { const st = 0, ar = Wd('area', 0) - st, sq = Wd('squared', 0) - st;
    add({ id: 'S01', at: st, cam: CAM, zoom: 0.05, note: 'paper circle, AREA = ? slip on "area", πr² stamp on "squared"', draw(lt) {
      K.parchment(SEED); solid();
      if (lt > ar) { const k = seg(lt, ar, ar + 0.35); ctx.save(); ctx.globalAlpha = 0.3 * k * (lt > sq ? 1 - seg(lt, sq, sq + 0.3) : 1); circle(CX, CY, R - 6, P.crimson); ctx.restore(); }
      K.slip('AREA = ?', 540, 360, lt > ar && lt < sq + 0.1 ? eob(seg(lt, ar, ar + 0.25)) : 0, -0.03, 70);
      if (lt > sq) stamp('A = πr²', 540, 380, lerp(1.9, 1, eob(seg(lt, sq, sq + 0.22))), -0.06, 120);
    } });
    cue(st + ar, 'pop'); cue(st + sq, 'stamp'); cue(st + sq + 0.02, 'thud', { gain: 0.7 }); }

  // ── 2 · a radius sweeps out (r), then four knife cuts make 8 wedges ──────────────
  { const st = cutAt(1), cr = Wd('circle', 1) - st, sl = Wd('slice', 1) - st, pz = Wd('pizza', 1) - st, step = Math.max(0.12, (pz - sl) / 4);
    add({ id: 'S02', at: st, cam: CAM, zoom: 0.08, note: 'radius r sweeps on "circle", 4 knife cuts from "slice"', draw(lt) {
      K.parchment(SEED);
      const done = sl + 4 * step, k = seg(lt, done, done + 0.25);
      solid();
      if (k > 0) { ctx.save(); ctx.globalAlpha = k; for (let i = 0; i < 8; i++) wedge(circState(i, 8, 0, 4 * k), 8, col(i)); ctx.restore(); }
      for (let j = 0; j < 4; j++) {                              // knife lines through the centre, one per cut
        const p = eo(seg(lt, sl + j * step, sl + j * step + step * 0.9)); if (p <= 0 || k >= 1) continue;
        const ang = -PI / 2 + A(8) / 2 + j * A(8), dx = Math.cos(ang) * (R + 40), dy = Math.sin(ang) * (R + 40);
        ctx.save(); ctx.globalAlpha = 1 - k; ctx.strokeStyle = P.ink; ctx.lineWidth = 7; ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(CX - dx, CY - dy); ctx.lineTo(CX - dx + 2 * dx * p, CY - dy + 2 * dy * p); ctx.stroke(); ctx.restore();
      }
      const rp = eo(seg(lt, cr - 0.1, cr + 0.3)), fade = 1 - seg(lt, sl - 0.1, sl + 0.15);
      if (rp > 0 && fade > 0) { ctx.save(); ctx.globalAlpha = fade; ctx.strokeStyle = P.crimson; ctx.lineWidth = 10; ctx.lineCap = 'round'; ctx.beginPath(); ctx.moveTo(CX, CY); ctx.lineTo(CX + R * rp, CY); ctx.stroke(); circle(CX, CY, 11, P.crimson); ctx.restore(); tag('r', CX + R / 2, CY - 70, eob(seg(lt, cr + 0.1, cr + 0.35)) * fade); }
    } });
    cue(st, 'whoosh'); cue(st + cr, 'pop', { gain: 0.6 }); for (let j = 0; j < 4; j++) cue(st + sl + j * step, 'zip', { gain: 0.55, pan: j % 2 ? 0.3 : -0.3 }); }

  // ── 3 · the wedges pop apart and turn slowly ─────────────────────────────────────
  const D3 = shotLen(2), SPIN3 = (lt) => 0.22 * lt, GAP = 34;
  { const st = cutAt(2), wd = Wd('wedges', 2) - st;
    add({ id: 'S03', at: st, cam: CAM, zoom: 0.1, note: '8 wedges pop apart, slow spin, "8 SLICES" slip', draw(lt) {
      K.parchment(SEED);
      for (let i = 0; i < 8; i++) wedge(circState(i, 8, SPIN3(lt), 4 + (GAP - 4) * eob(seg(lt, 0.05 + i * 0.05, 0.35 + i * 0.05))), 8, col(i));
      K.slip('8 SLICES', 540, 400, eob(seg(lt, wd - 0.1, wd + 0.15)), -0.03, 64);
    } });
    cue(st, 'whoosh'); for (let i = 0; i < 8; i++) cue(st + 0.05 + i * 0.05, 'pop', { gain: 0.35, pan: (i / 7 - 0.5) }); cue(st + wd, 'pop', { gain: 0.6 }); }

  // ── 4 · KINETIC: every wedge hops into the row, every other one flipped ─────────
  { const st = cutAt(3), fl = Wd('flip', 3) - st, sd = Wd('side', 3) - st, d = shotLen(3);
    const t0 = Math.max(0.2, fl - 0.05), t1 = Math.min(d - 0.35, Math.max(sd + 0.5, t0 + 1.4)), dur = 0.55, stag = (t1 - t0 - dur) / 7;
    add({ id: 'S04', at: st, cam: [540, 920], zoom: 0.06, note: 'wedges hop one by one from the circle into an alternating row', draw(lt) {
      K.parchment(SEED);
      const order = [...Array(8).keys()].sort((a, b) => (seg(lt, t0 + a * stag, t0 + a * stag + dur) > 0) - (seg(lt, t0 + b * stag, t0 + b * stag + dur) > 0));
      for (const i of order) {                                    // wedges in flight are drawn on top
        const p = seg(lt, t0 + i * stag, t0 + i * stag + dur);
        const from = circState(i, 8, SPIN3(D3), GAP), to = rowState(i, 8);
        wedge(mix(from, to, eob(p), 170), 8, col(i));
      }
    } });
    cue(st, 'whoosh');
    for (let i = 0; i < 8; i++) { cue(st + t0 + i * stag, 'slide', { dur: dur, gain: 0.35, pan: (i / 7 - 0.5) * 0.8 }); cue(st + t0 + i * stag + dur * 0.8, 'tock', { gain: 0.8, pan: (i / 7 - 0.5) * 0.8 }); } }

  // ── 5 · a bumpy parallelogram: crimson dashed outline, bumps glow ────────────────
  { const st = cutAt(4), bm = Wd('bumpy', 4) - st, pg = Wd('parallelogram', 4) - st;
    const n = 8, s = R * Math.sin(A(n) / 2), c = R * Math.cos(A(n) / 2), a0 = rowState(0, n), aL = rowState(n - 1, n);
    const outline = [[a0.x, a0.y], [a0.x - s, a0.y - c], [aL.x, aL.y], [aL.x + s, aL.y + c], [a0.x, a0.y]];
    add({ id: 'S05', at: st, cam: [540, 905], zoom: 0.12, note: 'row of 8, bumps glow on "bumpy", dashed parallelogram on "parallelogram"', draw(lt) {
      K.parchment(SEED);
      const glow = lt > bm ? 0.5 + 0.5 * Math.sin((lt - bm) * 9) : 0;
      row(n, { crustUp: glow * (1 - seg(lt, pg, pg + 0.3)), crustDn: glow * (1 - seg(lt, pg, pg + 0.3)) });
      if (lt > pg - 0.1) K.dashedRoute(outline, eio(seg(lt, pg - 0.1, pg + 0.7)));
    } });
    cue(st, 'whoosh'); cue(st + bm, 'boing', { gain: 0.45 }); cue(st + pg, 'slide', { dur: 0.8, gain: 0.5 }); }

  // ── 6 · thinner and thinner: 8 → 16 → 32 → 64 slices, the bumps flatten ──────────
  { const st = cutAt(5), th1 = Wn('thinner', 5, 0) - st, th2 = Wn('thinner', 5, 1) - st, bu = Wd('bumps', 5) - st;
    const steps = [[0, 8], [th1 - 0.05, 16], [th2 - 0.05, 32], [bu - 0.05, 64]];
    add({ id: 'S06', at: st, cam: [540, 905], zoom: 0.1, note: 'n doubles on each "thinner" and on "bumps"; counter slip', draw(lt) {
      K.parchment(SEED);
      let k = 0; while (k + 1 < steps.length && lt >= steps[k + 1][0]) k++;
      const [t0, n] = steps[k], q = k ? seg(lt, t0, t0 + 0.28) : 1;
      row(n, { sx: k ? lerp(0.9, 1, eob(q)) : 1, sy: k ? lerp(1.18, 1, eob(q)) : 1 });
      K.slip(`${n} SLICES`, 540, 420, k ? lerp(1.35, 1, eob(q)) : 1, k % 2 ? 0.03 : -0.03, 64);
    } });
    cue(st, 'whoosh'); steps.slice(1).forEach(([t0], j) => { cue(st + t0, 'zip', { gain: 0.6 }); cue(st + t0 + 0.05, 'pop', { gain: 0.4 + j * 0.1 }); }); }

  // ── 7 · SNAP: a perfect rectangle, traced in crimson ─────────────────────────────
  { const st = cutAt(6), pf = Wd('perfect', 6) - st, rc = Wd('rectangle', 6) - st;
    add({ id: 'S07', at: st, cam: [540, 905], zoom: 0.08, note: 'snaps into a clean πr × r rectangle on "perfect", traced on "rectangle"', draw(lt) {
      K.parchment(SEED);
      const k = seg(lt, pf - 0.05, pf + 0.25);
      if (k <= 0) row(64);
      else row(64, { clip: eo(k), sx: lerp(1.06, 1, eob(k)), sy: lerp(0.86, 1, eob(k)) });
      if (lt > rc - 0.05) traceRect(eio(seg(lt, rc - 0.05, rc + 0.55)));
    } });
    cue(st, 'whoosh'); cue(st + pf, 'thud'); cue(st + rc, 'slide', { dur: 0.6, gain: 0.45 }); cue(st + rc + 0.6, 'sparkle', { dur: 0.8, gain: 0.6 }); }

  // ── 8 · height = the radius, r ─────────────────────────────────────────────────
  { const st = cutAt(7), ht = Wd('height', 7) - st, rd = Wd('radius', 7) - st;
    add({ id: 'S08', at: st, cam: [420, 905], zoom: 0.1, note: 'brace up the left side on "height", r tag on "radius"', draw(lt) {
      K.parchment(SEED); rect({ outline: 1 });
      brace(RL - 40, YB, RL - 40, YT, eo(seg(lt, ht - 0.1, ht + 0.4)));
      if (lt > rd) { ctx.save(); ctx.globalAlpha = 0.5 + 0.5 * Math.sin((lt - rd) * 10); ctx.strokeStyle = P.crimson; ctx.lineWidth = 16; ctx.beginPath(); ctx.moveTo(RL, YB); ctx.lineTo(RL, YT); ctx.stroke(); ctx.restore(); }
      tag('r', RL - 40, (YT + YB) / 2, eob(seg(lt, rd, rd + 0.25)));
    } });
    cue(st, 'whoosh'); cue(st + ht, 'slide', { dur: 0.45, gain: 0.45 }); cue(st + rd, 'pop'); }

  // ── 9 · width = half the crust: the top edge IS the crust of the up-wedges ───────
  const MINI = { x: 540, y: 420, r: 135, n: 16 };
  function mini(k) {                                               // the small reference circle: its crust, half lit
    for (let i = 0; i < MINI.n; i++) {
      const a = A(MINI.n), rot = i * a;
      ctx.save(); ctx.translate(MINI.x, MINI.y); ctx.rotate(rot);
      cut(() => { ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, MINI.r, -PI / 2 - a / 2, -PI / 2 + a / 2); ctx.closePath(); }, col(i), { shadow: 0.3, edge: 2 });
      ctx.beginPath(); ctx.arc(0, 0, MINI.r - 4, -PI / 2 - a / 2, -PI / 2 + a / 2); ctx.lineWidth = 10;
      ctx.strokeStyle = i % 2 ? P.sepia : P.crimson; ctx.globalAlpha = i % 2 ? 0.55 : clamp(k); ctx.stroke(); ctx.globalAlpha = 1; ctx.restore();
    }
  }
  { const st = cutAt(8), wd = Wd('width', 8) - st, h1 = Wn('half', 8, 0) - st, cr = Wd('crust', 8) - st, cf = Wd('circumference', 8) - st;
    add({ id: 'S09', at: st, cam: [540, 760], zoom: 0.06, note: 'mini circle: alternate crust pieces light up; the same pieces form the top edge', draw(lt) {
      K.parchment(SEED);
      const crust = eo(seg(lt, cr - 0.1, cr + 0.3));
      rect({ crustUp: crust });
      const mk = eob(seg(lt, 0.05, 0.35)); ctx.save(); ctx.translate(MINI.x, MINI.y); ctx.scale(mk, mk); ctx.translate(-MINI.x, -MINI.y); mini(crust); ctx.restore();
      if (lt > h1 - 0.1) { ctx.strokeStyle = P.crimson; ctx.lineWidth = 12; ctx.lineCap = 'round'; ctx.beginPath(); ctx.moveTo(RL, YT); ctx.lineTo(lerp(RL, RRt, eio(seg(lt, h1 - 0.1, cr + 0.4))), YT); ctx.stroke(); }
      K.slip('½ the crust', 540, 650, lt > cf - 0.05 ? eob(seg(lt, cf - 0.05, cf + 0.2)) : eob(seg(lt, wd, wd + 0.2)) * 0, -0.02, 54);
    } });
    cue(st, 'whoosh'); cue(st + h1, 'slide', { dur: cr + 0.4 - h1, gain: 0.45 }); cue(st + cr, 'sparkle', { dur: 0.7, gain: 0.55 }); cue(st + cf, 'pop'); }

  // ── 10 · …which is πr ───────────────────────────────────────────────────────────
  { const st = cutAt(9), pi = Wd('pi', 9) - st;
    add({ id: 'S10', at: st, cam: [540, 760], zoom: 0.08, note: '2πr ÷ 2 slip, brace over the top, πr tag on "pi"', draw(lt) {
      K.parchment(SEED); rect({ crustUp: 1 });
      ctx.strokeStyle = P.crimson; ctx.lineWidth = 12; ctx.lineCap = 'round'; ctx.beginPath(); ctx.moveTo(RL, YT); ctx.lineTo(RRt, YT); ctx.stroke();
      tile('2πr ÷ 2', 540, 420, eob(seg(lt, 0.05, 0.3)), -0.03, 84);
      brace(RL, YT - 60, RRt, YT - 60, eo(seg(lt, pi - 0.2, pi + 0.25)));
      tag('πr', 540, YT - 60, eob(seg(lt, pi, pi + 0.25)));
    } });
    cue(st, 'whoosh'); cue(st + 0.05, 'pop', { gain: 0.5 }); cue(st + pi, 'pop'); }

  // ── 11 · area = πr × r: the tiles slide into an equation ────────────────────────
  const EQY = 1300;
  { const st = cutAt(10), ar = Wd('area', 10) - st, pi = Wd('pi', 10) - st, tm = Wd('times', 10) - st, r2 = Wn('r', 10, 1) - st;
    add({ id: 'S11', at: st, cam: [540, 960], zoom: 0.06, note: 'rect fills on "area", πr then × then r tiles fly to an equation', draw(lt) {
      K.parchment(SEED); rect({ crustUp: 1, wash: lt > ar ? eo(seg(lt, ar, ar + 0.4)) : 0 });
      brace(RL, YT - 60, RRt, YT - 60, 1); brace(RL - 40, YB, RL - 40, YT, 1);
      const p1 = eob(seg(lt, pi, pi + 0.4)), p2 = eob(seg(lt, r2, r2 + 0.4));
      tag('πr', lerp(540, 330, p1), lerp(YT - 60, EQY, p1), lerp(1, 1.3, p1));
      tag('r', lerp(RL - 40, 770, p2), lerp((YT + YB) / 2, EQY, p2), lerp(1, 1.3, p2));
      tile('×', 550, EQY, eob(seg(lt, tm, tm + 0.25)), 0, 90);
    } });
    cue(st, 'whoosh'); cue(st + ar, 'bubbles', { dur: 0.6, gain: 0.4 }); cue(st + pi, 'slide', { dur: 0.4, gain: 0.5 }); cue(st + tm, 'pop'); cue(st + r2, 'slide', { dur: 0.4, gain: 0.5 }); }

  // ── 12 · πr²! the stamp lands on the rectangle ─────────────────────────────────
  { const st = cutAt(11), sq = Wd('squared', 11) - st;
    add({ id: 'S12', at: st, cam: [540, 960], zoom: 0.1, note: 'tiles merge; A = πr² stamp slams on "squared"', draw(lt) {
      K.parchment(SEED); rect({ crustUp: 1, wash: 1 });
      brace(RL, YT - 60, RRt, YT - 60, 1); brace(RL - 40, YB, RL - 40, YT, 1);
      const m = eio(seg(lt, 0, Math.max(0.2, sq - 0.05)));
      if (lt < sq) { tag('πr', lerp(330, 540, m), EQY, 1.3 * (1 - m * 0.4)); tag('r', lerp(770, 540, m), EQY, 1.3 * (1 - m * 0.4)); tile('×', 550, EQY, 1 - m, 0, 90); }
      if (lt > sq - 0.02) stamp('A = πr²', 540, (YT + YB) / 2, lerp(2.1, 1, eob(seg(lt, sq - 0.02, sq + 0.22))), -0.05, 140);
      tag('πr', 540, YT - 60, 1); tag('r', RL - 40, (YT + YB) / 2, 1);
    } });
    cue(st, 'whoosh'); cue(st + sq, 'stamp'); cue(st + sq + 0.02, 'slam', { gain: 0.6 }); cue(st + sq + 0.15, 'sparkle', { dur: 1, gain: 0.6 }); }

  // ── 13 · c. 260 BC: Archimedes draws a circle in the sand ───────────────────────
  { const st = cutAt(12), ar = Wd('archimedes', 12) - st, pr = Wd('proved', 12) - st, yr = Wd('years', 12) - st, d = shotLen(12);
    const FX = 320, FY = 1400, EX = 740, EY = 1462, ERX = 190, ERY = 52, ARM = 62;
    add({ id: 'S13', at: st, cam: [540, 900], zoom: 0.08, note: 'gold c. 260 BC ribbon, scholar draws a circle in sand with a stick', draw(lt, dd, t) {
      K.parchment(33); ctx.fillStyle = P.sky; ctx.fillRect(-300, -300, W + 600, 1700);
      cut(P_circ(170, 430, 64), '#EFC66A', { shadow: 0.4, edge: 5 });
      for (const x of [890, 1010]) { cut(P_rr(x - 45, 700, 90, 700, 6), P.stone, { shadow: 0.6, edge: 4 }); cut(P_rr(x - 70, 670, 140, 46, 6), P.stoneDark, { shadow: 0.5, edge: 4 }); }
      cut(P_rr(-300, FY, W + 600, 700, 0), P.land, { shadow: 0.4, edge: 0 });
      const p = eio(seg(lt, pr - 0.1, Math.min(d - 0.2, pr + 1.6))), ang = -PI / 2 + p * TAU;
      if (p > 0) { ctx.beginPath(); ctx.ellipse(EX, EY, ERX, ERY, 0, -PI / 2, ang); ctx.strokeStyle = P.sepia; ctx.lineWidth = 7; ctx.stroke(); }
      const th = (-ARM - 10) * PI / 180, hx = FX + 30 - 220 * Math.sin(th), hy = FY - 440 + 220 * Math.cos(th);
      const tx = EX + ERX * Math.cos(ang), ty = EY + ERY * Math.sin(ang);
      K.figure({ x: FX, y: FY, h: 640, role: 'scholar', dir: 1, arm: ARM });
      ctx.strokeStyle = P.sepia; ctx.lineWidth = 9; ctx.lineCap = 'round'; ctx.beginPath(); ctx.moveTo(hx, hy); ctx.lineTo(p > 0 ? tx : EX, p > 0 ? ty : EY - ERY); ctx.stroke();
      K.ribbon('c. 260 BC', 540, 300, eob(seg(lt, 0.05, 0.4)), 92);
      K.slip('ARCHIMEDES', FX, 610, eob(seg(lt, ar, ar + 0.25)), -0.03, 52);
      K.slip('Measurement of a Circle', 760, 540, eob(seg(lt, yr - 0.1, yr + 0.2)), 0.02, 40);
    } });
    cue(st, 'whoosh'); cue(st + 0.05, 'pop', { gain: 0.5 }); cue(st + ar, 'pop'); cue(st + pr, 'slide', { dur: 1.6, gain: 0.4 }); cue(st + yr, 'pop', { gain: 0.6 }); }

  // ── 14 · LOOP: the 64 slivers fly home into the circle, seams vanish → frame 0 ──
  { const st = cutAt(13), d = T.dur - st, cc = Wd('circle', 13) - st;
    const t0 = 0.1, t1 = Math.max(t0 + 0.8, Math.min(d - 0.55, cc + 0.6)), dur = 0.5, stag = (t1 - t0 - dur) / 63, seam = t1 + 0.05;
    add({ id: 'S14', at: st, cam: CAM, zoom: 0.05, note: 'slivers fly back into the circle, seams fade: the last frame is frame 0', draw(lt) {
      K.parchment(SEED);
      const s = seg(lt, seam, seam + 0.3);
      if (s >= 1) { solid(); return; }
      for (let i = 0; i < 64; i++) { const j = i, p = seg(lt, t0 + j * stag, t0 + j * stag + dur); wedge(mix(rowState(i, 64), circState(i, 64), eio(p), 110), 64, col(i)); }
      if (s > 0) { ctx.save(); ctx.globalAlpha = s; solid(); ctx.restore(); }
    } });
    cue(st, 'whoosh'); cue(st + t0, 'slide', { dur: t1 - t0, gain: 0.5 }); cue(st + seam, 'thud', { gain: 0.5 }); }

  return { shots: S, cues: CUES };
}
