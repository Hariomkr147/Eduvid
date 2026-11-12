// Template scenes (spec 2026-11-12 §5): each draws one frame of its scene at scene time t, from the script data.
// S = { sc, t, dur, lang, at(item), L(i), Le(i), idx, total, W, H, portrait, bk, box }
import {
  C, ctx, clamp, eo, prog, fade, spring, text, para, wrap, measure, pill, chip, card, figureCard, bk, bubble, tex,
  texSize, iconCircle, rr,
} from './kit.js';
import { drawShapes } from './figure.js';

export const tr = (bi, lang) => (bi ? (bi[lang] || bi.en || bi.hi || '') : '');
const KIND = {
  title: { en: 'Lesson', hi: 'पाठ', tone: 'brand' }, concept: { en: 'Idea', hi: 'विचार', tone: 'level' },
  board: { en: 'On the board', hi: 'बोर्ड पर', tone: 'level' }, figure: { en: 'Picture it', hi: 'चित्र से समझें', tone: 'level' },
  example: { en: 'Worked example', hi: 'हल किया उदाहरण', tone: 'level' }, check: { en: 'Pause and try', hi: 'रुककर सोचो', tone: 'gold' },
  summary: { en: 'Summary', hi: 'सारांश', tone: 'good' },
};

export function layout(W, H, captions) {
  const portrait = H > W, M = portrait ? 72 : 112;
  const top = portrait ? 340 : 268, bottom = H - (captions ? (portrait ? 330 : 190) : (portrait ? 140 : 96));
  return { portrait, M, top, bottom, x: M, y: top, w: W - 2 * M, h: bottom - top };
}

// shared chrome: purple progress bar, kind tag, scene heading
export function header(S, opts = {}) {
  const { W, M, portrait } = S;
  if (S.chrome) {           // progress bar + "2 / 6": for MP4s watched outside the player (the player shows its own)
    const p = (S.idx + clamp(S.t / Math.max(1, S.dur))) / S.total;
    rr(M, 56, W - 2 * M, 12, 6); ctx.fillStyle = C.line; ctx.fill();
    rr(M, 56, Math.max(12, (W - 2 * M) * p), 12, 6); ctx.fillStyle = C.brand; ctx.fill();
    pill(`${S.idx + 1} / ${S.total}`, W - M, 104, { size: 30, tone: 'ink', align: 'right' });
  }
  const k = KIND[S.sc.kind] || KIND.concept;
  pill(S.lang === 'hi' ? k.hi : k.en, M, 104, { size: 30, tone: k.tone });
  if (opts.noTitle) return;
  const size = portrait ? 66 : 70, lines = wrap(tr(S.sc.title, S.lang), W - 2 * M - (portrait ? 0 : 200), size, 700, true).slice(0, 2);
  const a = fade(S.t, 0, 0.35);
  lines.forEach((ln, i) => text(ln, M, (portrait ? 236 : 218) + i * size * 1.12, { size, weight: 700, alpha: a }));
}

// ---------- title ----------
function title(S) {
  const { W, H, M, t, lang, portrait } = S, sc = S.sc;
  header(S, { noTitle: true });
  const a = fade(t, 0.05, 0.4), dy = (1 - eo(prog(t, 0.05, 0.4))) * 16;
  const colW = portrait ? W - 2 * M : W * 0.58;
  let y = portrait ? 330 : 300;
  if (tr(sc.tag, lang)) { pill(tr(sc.tag, lang), M, y - 70 + dy, { size: 32, tone: 'level', alpha: a }); y += 30; }
  const size = portrait ? 92 : 104;
  const tl = wrap(tr(sc.title, lang), colW, size, 800, true).slice(0, 3);
  tl.forEach((ln, i) => text(ln, M, y + size + i * size * 1.08 + dy, { size, weight: 800, alpha: a }));
  y += size + tl.length * size * 1.08;
  if (tr(sc.subtitle, lang)) y += para(tr(sc.subtitle, lang), M, y + 20, colW, { size: 44, color: S.muted || C.muted, alpha: fade(t, 0.4, 0.4) }) + 40;
  (sc.objectives || []).slice(0, 4).forEach((ob, i) => {
    const t0 = 1.0 + i * 0.6, aa = fade(t, t0, 0.3), s = 0.96 + 0.04 * eo(prog(t, t0, 0.3));
    if (aa <= 0) return;
    ctx.save(); ctx.translate(M, y + i * 92); ctx.scale(s, s);
    iconCircle('check', 30, 0, 30, C.goodBg, C.good);
    text(tr(ob, lang), 84, 16, { size: 42, weight: 500, display: false, color: C.ink2, alpha: aa, maxW: colW - 90 });
    ctx.restore();
  });
  if (S.bk) {
    const hop = t < 1.2 ? Math.sin(prog(t, 0.2, 0.6) * Math.PI) * 26 : 0;
    const bx = portrait ? W - 230 : W - 340, by = portrait ? H - 200 : H - 110, bh = portrait ? 420 : 470;
    bk(bx, by, bh, 'wave', { alpha: fade(t, 0.15, 0.35), hop });
    if (t > 0.6) bubble(lang === 'hi' ? 'नमस्ते! चलो शुरू करें।' : 'Namaste! Let’s begin.', bx - 120, by - bh * 0.78, { side: 'left', size: 38, maxW: 520, alpha: fade(t, 0.6, 0.3) });
  }
}

// ---------- concept ----------
function concept(S) {
  const { t, lang, portrait, box } = S, sc = S.sc;
  header(S);
  const pts = sc.points || [], withTex = pts.some((p) => p.tex);
  const listW = withTex && !portrait ? box.w * 0.55 : box.w;
  let y = box.y + 20, current = -1;
  pts.forEach((p, i) => { if (t >= S.at(p)) current = i; });
  pts.forEach((p, i) => {
    const t0 = S.at(p), a = fade(t, t0, 0.3);
    if (a <= 0) return;
    const lines = wrap(tr(p.text, lang), listW - 150, 46, 500, false), h = Math.max(96, lines.length * 64 + 36);
    const s = 0.96 + 0.04 * eo(prog(t, t0, 0.3));
    ctx.save(); ctx.translate(box.x, y); ctx.scale(s, s); ctx.globalAlpha = a;
    if (i === current) { rr(0, 0, listW, h, 28); ctx.fillStyle = C.primarySoft; ctx.fill(); }
    chip(i + 1, 56, h / 2, { r: 30, solid: i === current });
    lines.forEach((ln, k) => text(ln, 116, h / 2 - (lines.length - 1) * 32 + 16 + k * 64, { size: 46, weight: 500, display: false, color: i === current ? C.ink : C.ink2 }));
    ctx.restore();
    y += h + 22;
  });
  if (withTex) {
    const fx = portrait ? box.x : box.x + listW + 48, fy = portrait ? Math.min(y + 30, box.y + box.h - 360) : box.y, fw = portrait ? box.w : box.w - listW - 48, fh = portrait ? box.y + box.h - fy : box.h;
    const inner = figureCard(fx, fy, fw, fh, { grid: S.grid, alpha: fade(t, S.at(pts.find((p) => p.tex)) - 0.2, 0.3) });
    const shown = pts.filter((p) => p.tex && t >= S.at(p));
    const last = shown[shown.length - 1];
    if (last) {
      const t0 = S.at(last), size = 64, sz = texSize(last.tex, size), k = Math.min(1, (inner.w - 60) / Math.max(1, sz.w));
      tex(last.tex, inner.x + inner.w / 2, inner.y + inner.h / 2 + sz.h * k / 2.6, { size: size * k, align: 'center', progress: eo(prog(t, t0, 0.8)) });
    }
  } else if (S.bk && !portrait) {
    bk(box.x + box.w - 120, box.y + box.h + 20, 380, 'calm', { alpha: fade(t, 0.3, 0.4) });
  }
}

// ---------- board ----------
function board(S) {
  const { t, lang, box } = S, sc = S.sc;
  header(S);
  const inner = figureCard(box.x, box.y, box.w, box.h, { grid: S.grid, alpha: fade(t, 0, 0.3) });
  const steps = sc.steps || [], size = S.portrait ? 54 : 60, gap = 34, padX = 56;
  const rows = steps.map((st) => {
    const sz = st.tex ? texSize(st.tex, size) : { w: 0, h: size };
    const k = st.tex ? Math.min(1, (inner.w * (S.portrait ? 0.92 : 0.66)) / Math.max(1, sz.w)) : 1;
    return { st, k, h: Math.max(st.tex ? sz.h * k : 64, 64) + 28 };
  });
  let total = 0, latest = -1;
  rows.forEach((r, i) => { r.y = total; total += r.h + gap; if (t >= S.at(r.st)) latest = i; });
  const visBottom = latest >= 0 ? rows[latest].y + rows[latest].h : 0;
  const tScroll = latest >= 0 ? S.at(rows[latest].st) : 0;
  const want = Math.max(0, visBottom - (inner.h - 70));
  const prevWant = latest > 0 ? Math.max(0, rows[latest - 1].y + rows[latest - 1].h - (inner.h - 70)) : 0;
  const scroll = prevWant + (want - prevWant) * eo(prog(t, tScroll - 0.1, 0.5));
  ctx.save(); rr(inner.x, inner.y, inner.w, inner.h, 22); ctx.clip();
  rows.forEach((r, i) => {
    const t0 = S.at(r.st); if (t < t0) return;
    const y = inner.y + 44 + r.y - scroll, x = inner.x + padX;
    if (r.st.key) {
      const bw = (r.st.tex ? texSize(r.st.tex, size).w * r.k : measure(tr(r.st.text, lang), 48, 600, false)) + 56;
      ctx.save(); ctx.globalAlpha = fade(t, t0 + 0.5, 0.3);
      rr(x - 28, y - 6, bw, r.h - 4, 22); ctx.fillStyle = C.primarySoft; ctx.fill(); ctx.lineWidth = 4; ctx.strokeStyle = C.primary; ctx.stroke();
      ctx.restore();
    }
    if (r.st.tex) tex(r.st.tex, x, y + r.h - 32, { size: size * r.k, color: C.ink, progress: eo(prog(t, t0, 0.8)) });
    const note = tr(r.st.text, lang);
    if (note && r.st.tex && !S.portrait) text(note, inner.x + inner.w - padX, y + r.h / 2 + 8, { size: 36, weight: 500, display: false, color: C.muted, align: 'right', alpha: fade(t, t0 + 0.6, 0.3), maxW: inner.w * 0.3 });
    else if (note && !r.st.tex) text(note, x, y + r.h / 2 + 14, { size: 48, weight: 600, display: false, color: C.ink2, alpha: fade(t, t0, 0.3), maxW: inner.w - 2 * padX });
  });
  ctx.restore();
}

// ---------- figure ----------
function figure(S) {
  const { t, lang, box, portrait } = S, sc = S.sc;
  header(S);
  const side = (sc.points || []).length > 0;
  const fw = portrait || !side ? box.w : box.w * 0.64, fh = portrait && side ? box.h * 0.62 : box.h;
  const inner = figureCard(box.x, box.y, fw, fh, { grid: S.grid, alpha: fade(t, 0, 0.3) });
  drawShapes(sc.shapes || [], { x: inner.x + 30, y: inner.y + 30, w: inner.w - 60, h: inner.h - 60 }, t, S.at);
  if (side) {
    const x = portrait ? box.x : box.x + fw + 48, w = portrait ? box.w : box.w - fw - 48;
    let y = portrait ? box.y + fh + 40 : box.y + 10;
    (sc.points || []).forEach((p, i) => {
      const a = fade(t, S.at(p), 0.3); if (a <= 0) return;
      chip(i + 1, x + 30, y + 30, { r: 28, alpha: a });
      const h = para(tr(p.text, lang), x + 80, y + 44, w - 90, { size: 40, color: C.ink2, alpha: a });
      y += Math.max(80, h + 26);
    });
  }
}

// ---------- example ----------
function example(S) {
  const { t, lang, box, portrait } = S, sc = S.sc;
  header(S);
  const qW = portrait ? box.w : box.w * 0.42, qa = fade(t, 0.1, 0.35);
  const qLines = wrap(tr(sc.question, lang), qW - 80, 42, 500, false).slice(0, 9);
  const qH = Math.max(220, qLines.length * 60 + 150);
  card(box.x, box.y, qW, qH, { alpha: qa });
  pill(lang === 'hi' ? 'प्रश्न' : 'Question', box.x + 40, box.y + 34, { size: 28, tone: 'level', alpha: qa });
  qLines.forEach((ln, i) => text(ln, box.x + 40, box.y + 142 + i * 60, { size: 42, weight: 500, display: false, color: C.ink, alpha: qa }));
  const sx = portrait ? box.x : box.x + qW + 48, sw = portrait ? box.w : box.w - qW - 48;
  let y = portrait ? box.y + qH + 40 : box.y;
  const steps = sc.steps || [];
  const answerT = S.L(sc.lines.length - 1);
  steps.forEach((st, i) => {
    const t0 = S.at(st), a = fade(t, t0, 0.3); if (a <= 0) return;
    const s = 0.96 + 0.04 * eo(prog(t, t0, 0.3));
    ctx.save(); ctx.translate(sx, y); ctx.scale(s, s);
    chip(i + 1, 32, 40, { r: 28, alpha: a, solid: !!st.key });
    let h = 0;
    if (st.tex) { const sz = texSize(st.tex, 50), k = Math.min(1, (sw - 110) / Math.max(1, sz.w)); tex(st.tex, 84, 40 + sz.h * k * 0.32, { size: 50 * k, alpha: a, progress: eo(prog(t, t0, 0.7)) }); h = Math.max(80, sz.h * k + 20); }
    const note = tr(st.text, lang);
    if (note) h += para(note, 84, (st.tex ? h + 30 : 52), sw - 100, { size: st.tex ? 34 : 40, color: st.tex ? C.muted : C.ink2, alpha: a }) + (st.tex ? 0 : 10);
    ctx.restore();
    y += Math.max(86, h + 24);
    if (i < steps.length - 1) { ctx.fillStyle = C.line; ctx.globalAlpha = a; ctx.fillRect(sx + 84, y - 14, sw - 100, 2); ctx.globalAlpha = 1; }
  });
  const ans = tr(sc.answer, lang), at0 = Math.max(answerT, steps.length ? S.at(steps[steps.length - 1]) + 0.6 : 0);
  if ((ans || sc.answer_tex) && t >= at0) {
    const a = fade(t, at0, 0.3), ay = portrait ? Math.min(y + 20, box.y + box.h - 170) : Math.min(box.y + qH + 40, box.y + box.h - 170), ax = portrait ? box.x : box.x, aw = portrait ? box.w : qW;
    ctx.save(); ctx.globalAlpha = a;
    rr(ax, ay, aw, 150, 24); ctx.fillStyle = C.goodBg; ctx.fill(); ctx.lineWidth = 3; ctx.strokeStyle = C.goodLine; ctx.stroke();
    ctx.restore();
    iconCircle('check', ax + 62, ay + 75, 30, C.good, '#fff');
    text(lang === 'hi' ? 'उत्तर' : 'Answer', ax + 116, ay + 58, { size: 34, weight: 700, color: C.goodInk, alpha: a });
    if (sc.answer_tex) tex(sc.answer_tex, ax + 116, ay + 122, { size: 44, color: C.goodInk, alpha: a });
    else text(ans, ax + 116, ay + 116, { size: 40, weight: 600, display: false, color: C.goodInk, alpha: a, maxW: aw - 140 });
  }
}

// ---------- check (pause-to-check; the player stops here and asks for real) ----------
function check(S) {
  const { W, t, lang, box, portrait } = S, sc = S.sc;
  header(S, { noTitle: true });
  const qSize = portrait ? 58 : 62, ql = wrap(tr(sc.question, lang), box.w - (portrait ? 0 : 260), qSize, 700, true).slice(0, 3);
  ql.forEach((ln, i) => text(ln, box.x, (portrait ? 250 : 222) + i * qSize * 1.15, { size: qSize, weight: 700, alpha: fade(t, 0, 0.35) }));
  const opts = sc.options || [], reveal = S.L(1), pauseA = S.Le(0), revealed = t >= reveal;
  const oy = (portrait ? 250 : 222) + ql.length * qSize * 1.15 + 10, cols = portrait ? 1 : 2, gap = 30;
  const ow = (box.w - gap * (cols - 1)) / cols, oh = portrait ? 132 : 140;
  opts.forEach((op, i) => {
    const t0 = 0.4 + i * 0.15, a = fade(t, t0, 0.3); if (a <= 0) return;
    const x = box.x + (i % cols) * (ow + gap), y = oy + Math.floor(i / cols) * (oh + gap + 6);
    const right = revealed && i === sc.correct, dim = revealed && !right;
    const shakeIn = right ? spring(prog(t, reveal, 0.5)) : 1;
    card(x, y, ow, oh, { alpha: a * (dim ? 0.55 : 1), fill: right ? C.goodBg : C.surface, stroke: right ? C.good : C.line,
      ledgeColor: right ? C.good : C.line2, border: right ? 4 : 2, radius: 28 });
    ctx.save(); ctx.globalAlpha = a * (dim ? 0.55 : 1);
    if (right) iconCircle('check', x + 64, y + oh / 2, 30 * shakeIn, C.good, '#fff');
    else chip('ABCD'[i], x + 64, y + oh / 2, { r: 30 });
    ctx.restore();
    text(tr(op, lang), x + 120, y + oh / 2 + 15, { size: 42, weight: 500, display: false, color: right ? C.goodInk : C.ink, alpha: a * (dim ? 0.55 : 1), maxW: ow - 150 });
  });
  // the pause: a gold countdown ring and Bal Krishna's hint
  if (t >= pauseA - 0.2 && !revealed) {
    const total = Math.max(1, reveal - pauseA), left = clamp((reveal - t) / total), secs = Math.ceil(Math.max(0, reveal - t));
    const cx = W - S.M - 70, cy = 230, a = fade(t, pauseA - 0.2, 0.3);
    ctx.save(); ctx.globalAlpha = a;
    ctx.beginPath(); ctx.arc(cx, cy, 64, 0, Math.PI * 2); ctx.fillStyle = C.goldBg; ctx.fill();
    ctx.lineWidth = 10; ctx.strokeStyle = C.goldLine; ctx.stroke();
    ctx.beginPath(); ctx.arc(cx, cy, 64, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * left); ctx.strokeStyle = C.goldDeep; ctx.lineCap = 'round'; ctx.stroke();
    ctx.restore();
    text(String(secs), cx, cy + 22, { size: 64, weight: 800, color: C.goldInk, align: 'center', alpha: a });
    if (S.bk && tr(sc.hint, lang) && t > pauseA + total * 0.35) {
      const ha = fade(t, pauseA + total * 0.35, 0.3), bx = portrait ? W - 200 : W - 230, by = S.H - (S.captions ? (portrait ? 330 : 190) : 90);
      bk(bx, by, portrait ? 300 : 320, 'calm', { alpha: ha });
      bubble((lang === 'hi' ? 'संकेत: ' : 'Hint: ') + tr(sc.hint, lang), bx - 100, by - 230, { side: 'left', size: 36, maxW: 620, alpha: ha });
    }
  }
  if (revealed && tr(sc.explain, lang)) {
    const a = fade(t, reveal + 0.8, 0.3), rows = Math.ceil(opts.length / cols), ey = oy + rows * (oh + gap + 6) + 4;
    const h = Math.min(box.y + box.h - ey, 190);
    if (h > 80) {
      ctx.save(); ctx.globalAlpha = a; rr(box.x, ey, box.w, h, 24); ctx.fillStyle = C.goodBg; ctx.fill(); ctx.lineWidth = 3; ctx.strokeStyle = C.goodLine; ctx.stroke(); ctx.restore();
      iconCircle('info', box.x + 58, ey + 58, 26, C.good, '#fff');
      para(tr(sc.explain, lang), box.x + 108, ey + 70, box.w - 140, { size: 38, color: C.goodInk, alpha: a, maxLines: Math.max(1, Math.floor((h - 30) / 54)) });
    }
  }
}

// ---------- summary ----------
function summary(S) {
  const { W, H, t, lang, box, portrait } = S, sc = S.sc;
  header(S);
  const pts = (sc.points || []).slice(0, 4), n = pts.length || 1;
  const cols = portrait ? 1 : Math.min(n, 2), gap = 32, cw = portrait ? box.w : (box.w - (S.bk ? 420 : 0) - gap * (cols - 1)) / cols;
  const ch = portrait ? 200 : Math.min(260, (box.h - gap) / Math.ceil(n / cols));
  pts.forEach((p, i) => {
    const t0 = S.at(p) || 0.5 + i * 0.5, a = fade(t, t0, 0.3); if (a <= 0) return;
    const x = box.x + (i % cols) * (cw + gap), y = box.y + Math.floor(i / cols) * (ch + gap);
    const s = 0.96 + 0.04 * eo(prog(t, t0, 0.3));
    ctx.save(); ctx.translate(x + cw / 2, y + ch / 2); ctx.scale(s, s); ctx.translate(-x - cw / 2, -y - ch / 2);
    card(x, y, cw, ch, { alpha: a, radius: 24 });
    ctx.restore();
    iconCircle('star', x + 64, y + 66, 32, C.goldBg, C.goldDeep);
    para(tr(p.text, lang), x + 116, y + 80, cw - 150, { size: 40, color: C.ink2, alpha: a, maxLines: Math.max(2, Math.floor((ch - 60) / 56)) });
  });
  if (S.bk) {
    const end = S.dur, cheerT = Math.max(0.5, end - 3.2);
    const hop = Math.abs(Math.sin(prog(t, cheerT, 0.9) * Math.PI * 2)) * 28 * (t < cheerT + 0.9 && t > cheerT ? 1 : 0);
    const bx = portrait ? W - 220 : W - 300, by = S.H - (S.captions ? (portrait ? 330 : 190) : 90);
    bk(bx, by, portrait ? 360 : 420, 'wave', { alpha: fade(t, 0.2, 0.35), hop });
    const nx = tr(sc.next, lang);
    if (nx && t > cheerT) bubble(nx, bx - 110, by - (portrait ? 290 : 340), { side: 'left', size: 36, maxW: portrait ? 640 : 560, alpha: fade(t, cheerT, 0.3) });
  }
}

export const TEMPLATES = { title, concept, board, figure, example, check, summary };

// every LaTeX string a template scene may draw, with its colour (prepared before frames are drawn)
export function sceneTex(sc) {
  const out = [];
  (sc.points || []).forEach((p) => p.tex && out.push([p.tex, C.ink]));
  (sc.steps || []).forEach((s) => s.tex && out.push([s.tex, C.ink]));
  if (sc.answer_tex) out.push([sc.answer_tex, C.goodInk]);
  return out;
}
