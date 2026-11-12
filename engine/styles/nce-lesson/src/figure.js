// Labelled drawings from the script's `shapes` (schema.Shape): a 160 × 90 unit box mapped into a paper area.
// Each shape is drawn on (stroke progress) from its anchor time; labels fade in after the stroke.
import { C, NAMED, clamp, eo, prog, line, arrow, circle, arc, polyline, rect, ellipse, text, tex, ctx } from './kit.js';

const UNIT_W = 160, UNIT_H = 90;

export function fitBox(area) {
  const k = Math.min(area.w / UNIT_W, area.h / UNIT_H);
  const ox = area.x + (area.w - UNIT_W * k) / 2, oy = area.y + (area.h - UNIT_H * k) / 2;
  return { k, X: (x) => ox + x * k, Y: (y) => oy + y * k, S: (v) => v * k };
}

function lbl(s, x, y, color, a, k) {
  if (!s) return;
  if (/[\\^_{}]/.test(s)) tex(s, x, y, { size: Math.max(46, 6.2 * k), color, align: 'center', alpha: a });
  else text(s, x, y, { size: Math.max(46, 6.2 * k), weight: 700, color, align: 'center', alpha: a });
}

export function drawShapes(shapes, area, t, at) {
  const B = fitBox(area), { X, Y, S, k } = B;
  shapes.forEach((sh, i) => {
    const t0 = at(sh), p = eo(prog(t, t0, 0.9)), la = eo(prog(t, t0 + 0.5, 0.35));
    if (p <= 0) return;
    const color = NAMED[sh.color] || C.ink, width = Math.max(4, k * 0.9);
    const o = { color, width, progress: p, dash: sh.dashed ? [width * 3, width * 2.5] : null,
      fill: sh.fill ? hexA(color, 0.14) : null };
    const x = X(sh.x), y = Y(sh.y), x2 = X(sh.x2), y2 = Y(sh.y2), r = S(sh.r), w = S(sh.w), h = S(sh.h);
    switch (sh.type) {
      case 'point': {
        ctx.save(); ctx.globalAlpha = p; ctx.beginPath(); ctx.arc(x, y, width * 1.6, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill(); ctx.restore();
        lbl(sh.label, x + width * 4, y - width * 3, color, la, k); break;
      }
      case 'segment': case 'line': {
        line(x, y, x2, y2, o);
        { const nx = -(y2 - y), ny = x2 - x, L = Math.hypot(nx, ny) || 1, s = ny / L > 0 ? -1 : 1, off = Math.max(34, 7 * k);
          lbl(sh.label, (x + x2) / 2 + s * nx / L * off, (y + y2) / 2 + s * ny / L * off + off * 0.35, color, la, k); }
        break;
      }
      case 'arrow': arrow(x, y, x2, y2, o); lbl(sh.label, x2, y2 - width * 4, color, la, k); break;
      case 'circle': circle(x, y, r, o); lbl(sh.label, x, y - r - width * 3, color, la, k); break;
      case 'arc': arc(x, y, r, sh.a1 * Math.PI / 180, sh.a2 * Math.PI / 180, o); lbl(sh.label, x, y - r - width * 3, color, la, k); break;
      case 'rect': rect(x, y, w, h, o); lbl(sh.label, x + w / 2, y - width * 3, color, la, k); break;
      case 'polygon': case 'curve': {
        const pts = (sh.pts || []).map(([a, b]) => [X(a), Y(b)]);
        polyline(pts, { ...o, close: sh.type === 'polygon', fill: sh.type === 'polygon' ? o.fill : null });
        if (pts.length) lbl(sh.label, pts[0][0], pts[0][1] - width * 4, color, la, k); break;
      }
      case 'cylinder': {           // x,y = centre of the base ellipse, r radius, h height (up)
        const ry = r * 0.28;
        ellipse(x, y, r, ry, { ...o, dash: null }, 0, Math.PI);
        ellipse(x, y, r, ry, { ...o, dash: [width * 2, width * 2], fill: null }, Math.PI, Math.PI * 2);
        line(x - r, y, x - r, y - h, o); line(x + r, y, x + r, y - h, o);
        ellipse(x, y - h, r, ry, o);
        lbl(sh.label, x, y - h - ry - width * 4, color, la, k); break;
      }
      case 'cone': {
        const ry = r * 0.28;
        ellipse(x, y, r, ry, { ...o, dash: null }, 0, Math.PI);
        ellipse(x, y, r, ry, { ...o, dash: [width * 2, width * 2], fill: null }, Math.PI, Math.PI * 2);
        line(x - r, y, x, y - h, o); line(x + r, y, x, y - h, o);
        lbl(sh.label, x, y - h - width * 4, color, la, k); break;
      }
      case 'sphere': {
        circle(x, y, r, o);
        ellipse(x, y, r, r * 0.28, { ...o, dash: null, fill: null }, 0, Math.PI);
        ellipse(x, y, r, r * 0.28, { ...o, dash: [width * 2, width * 2], fill: null }, Math.PI, Math.PI * 2);
        lbl(sh.label, x, y - r - width * 3, color, la, k); break;
      }
      case 'hemisphere': {
        const ry = r * 0.28;
        arc(x, y, r, Math.PI, Math.PI * 2, o);
        ellipse(x, y, r, ry, { ...o, fill: null });
        lbl(sh.label, x, y - r - width * 3, color, la, k); break;
      }
      case 'cuboid': {             // x,y = front-bottom-left, w,h front face, r depth
        const d = r * 0.5;
        rect(x, y - h, w, h, o);
        polyline([[x, y - h], [x + d, y - h - d], [x + w + d, y - h - d], [x + w, y - h]], { ...o, fill: null });
        polyline([[x + w + d, y - h - d], [x + w + d, y - d], [x + w, y]], { ...o, fill: null });
        polyline([[x, y], [x + d, y - d], [x + w + d, y - d]], { ...o, fill: null, dash: [width * 2, width * 2] });
        line(x + d, y - d, x + d, y - h - d, { ...o, dash: [width * 2, width * 2] });
        lbl(sh.label, x + w / 2, y - h - d - width * 3, color, la, k); break;
      }
      case 'angle': {
        arc(x, y, r || S(8), -sh.a1 * Math.PI / 180, -sh.a2 * Math.PI / 180, { ...o, fill: null });
        const mid = -(sh.a1 + sh.a2) / 2 * Math.PI / 180, rr = (r || S(8)) + width * 6;
        lbl(sh.label, x + Math.cos(mid) * rr, y + Math.sin(mid) * rr + width * 2, color, la, k); break;
      }
      case 'axes': {
        arrow(x, y + h, x + w, y + h, { ...o, color: C.ink2 }); arrow(x, y + h, x, y, { ...o, color: C.ink2 });
        lbl(sh.label, x + w, y + h + width * 9, C.ink2, la, k); break;
      }
      case 'label': lbl(sh.label, x, y, color, eo(prog(t, t0, 0.35)), k); break;
      case 'brace': case 'dim': {
        const nx = -(y2 - y), ny = x2 - x, L = Math.hypot(nx, ny) || 1, off = width * 4;
        const ux = nx / L * off, uy = ny / L * off;
        line(x + ux, y + uy, x2 + ux, y2 + uy, { ...o, color: C.muted, width: width * 0.7 });
        line(x, y, x + ux * 1.6, y + uy * 1.6, { ...o, color: C.muted, width: width * 0.7 });
        line(x2, y2, x2 + ux * 1.6, y2 + uy * 1.6, { ...o, color: C.muted, width: width * 0.7 });
        lbl(sh.label, (x + x2) / 2 + ux * 2.6, (y + y2) / 2 + uy * 2.6 + width * 3, color === C.ink ? C.primary : color, la, k); break;
      }
    }
  });
}

function hexA(hex, a) { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; }
export const shapeTex = (shapes) => shapes.filter((s) => s.label && /[\\^_{}]/.test(s.label)).map((s) => [s.label, NAMED[s.color] || C.ink]);
