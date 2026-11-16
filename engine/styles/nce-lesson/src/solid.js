// 3D solids (roadmap phase 2): "solid" scenes render a three.js scene into a hidden WebGL canvas, which is copied
// under the 2D layer (labels, dimension lines, rims and the side points are crisp 2D on top).
// The scene is a pure function of scene time: every frame rebuilds the solid's geometry from the move timeline
//   moves: [{do: revolve | unroll | fill | cut | orbit | show | paint, line, word, len?, ...}]
// Any WebGL problem (no context, a blank frame twice in a row) draws the 2D figure of the same solid instead.
import * as K from './kit.js';
import { drawShapes } from './figure.js';

let THREE = null, R = null, GLC = null, PROBE = null, PCTX = null;
export const GL = { ok: false, error: '', blank: 0, frames: 0, redraws: 0 };

// three.js is only loaded when a lesson has a solid scene
export async function loadSolids() {
  try {
    THREE = await import('../vendor/three.module.js');
    GLC = document.createElement('canvas');
    R = new THREE.WebGLRenderer({ canvas: GLC, antialias: true, alpha: true, preserveDrawingBuffer: true });
    R.setPixelRatio(1); R.setSize(K.W, K.H, false); R.setClearColor(0x000000, 0);
    R.outputColorSpace = THREE.SRGBColorSpace; R.localClippingEnabled = true;
    R.shadowMap.enabled = true; R.shadowMap.type = THREE.PCFSoftShadowMap;
    PROBE = document.createElement('canvas'); PROBE.width = 48; PROBE.height = 32;
    PCTX = PROBE.getContext('2d', { willReadFrequently: true });
    GL.ok = true;
  } catch (e) { GL.ok = false; GL.error = String(e && e.message || e); }
}

const TAU = Math.PI * 2, PHI0 = Math.PI / 2;    // revolve starts from the profile on the right-hand side
const LEN = { revolve: 3, unroll: 3.2, fill: 3, cut: 1.6, orbit: 5, show: 0.5, paint: 0.7 };
const num = (v, d) => (Number.isFinite(+v) && +v > 0 ? +v : d);

// ---------- dimensions (world units: the solid's largest extent is 2) ----------
function dims(so) {
  const shape = so.shape === 'cube' ? 'cuboid' : so.shape;
  let r = num(so.r, 3.5), h = num(so.h, shape === 'sphere' ? 2 * r : shape === 'hemisphere' ? r : 2 * r);
  let r2 = Math.min(num(so.r2, r / 2), r), L = num(so.l, 4), B = num(so.b, so.shape === 'cube' ? L : 3);
  if (so.shape === 'cube') { h = L; B = L; } else if (shape === 'cuboid') h = num(so.h, 2.5);
  if (shape === 'sphere') h = 2 * r; if (shape === 'hemisphere') h = r;
  const ext = shape === 'cuboid' ? Math.max(L, B, h) : Math.max(2 * r, h);
  const k = 2 / ext;
  return { shape, k, r: r * k, r2: r2 * k, H: h * k, L: L * k, B: B * k, raw: { r, r2, h, l: shape === 'cone' ? Math.hypot(r, h) : L, b: B } };
}

// radius of the solid at height y (solids of revolution)
function radiusAt(d, y) {
  const { shape, r, r2, H } = d, f = K.clamp(y / H);
  if (shape === 'cylinder') return r;
  if (shape === 'cone') return r * (1 - f);
  if (shape === 'frustum') return K.lerp(r, r2, f);
  if (shape === 'sphere') return Math.sqrt(Math.max(0, r * r - (y - r) * (y - r)));
  if (shape === 'hemisphere') return Math.sqrt(Math.max(0, r * r - y * y));
  return 0;
}
// the profile curve (ρ, y) for v in 0..1, from the bottom rim to the top
function profile(d, v) {
  const { shape, r, r2, H } = d;
  if (shape === 'sphere') { const b = Math.PI * v; return [r * Math.sin(b), r - r * Math.cos(b)]; }
  if (shape === 'hemisphere') { const b = (Math.PI / 2) * v; return [r * Math.cos(b), r * Math.sin(b)]; }
  if (shape === 'cone') return [r * (1 - v), H * v];
  if (shape === 'frustum') return [K.lerp(r, r2, v), H * v];
  return [r, H * v];
}
const caps = (d) => ({ cylinder: [[0, d.r], [d.H, d.r]], cone: [[0, d.r]], frustum: [[0, d.r], [d.H, d.r2]], hemisphere: [[0, d.r]] }[d.shape] || []);

// ---------- the move timeline at scene time t ----------
function timeline(S) {
  const moves = (S.sc.moves || []).map((m) => ({ ...m, t0: S.at(m), len: num(m.len, LEN[m.do] || 1) }));
  const k = (type) => moves.filter((m) => m.do === type).reduce((a, m) => Math.max(a, K.eio(K.prog(S.t, m.t0, m.len))), 0);
  const last = (type) => moves.filter((m) => m.do === type && S.t >= m.t0).pop();
  const has = (type) => moves.some((m) => m.do === type);
  const orbit = moves.filter((m) => m.do === 'orbit').reduce((a, m) => a + (Number.isFinite(+m.turn) ? +m.turn : 360) * Math.PI / 180 * K.eio(K.prog(S.t, m.t0, m.len)), 0);
  const fillM = last('fill') || moves.find((m) => m.do === 'fill'), cutM = last('cut') || moves.find((m) => m.do === 'cut');
  const paints = moves.filter((m) => m.do === 'paint').map((m) => ({ part: m.part || 'curved', color: K.NAMED[m.color] || K.C.goldDeep, a: K.eo(K.prog(S.t, m.t0, m.len)) }));
  const shows = moves.filter((m) => m.do === 'show').map((m) => ({ dims: m.dims && m.dims.length ? m.dims : null, a: K.eo(K.prog(S.t, m.t0, m.len)) }));
  return { moves, orbit, paints, shows,
    rev: has('revolve') ? k('revolve') : 1, revStarted: has('revolve') ? S.t >= Math.min(...moves.filter((m) => m.do === 'revolve').map((m) => m.t0)) : true,
    un: k('unroll'), fill: k('fill') * K.clamp(fillM ? num(fillM.level, 1) : 1, 0.02, 1), filling: has('fill') && k('fill') > 0,
    cut: k('cut'), cutAt: K.clamp(cutM ? (Number.isFinite(+cutM.at) ? +cutM.at : 0.5) : 0.5, 0.1, 0.9), cutAxis: cutM && cutM.axis === 'v' ? 'v' : 'h' };
}

// ---------- geometry: fixed meshes whose vertices are rewritten each frame ----------
// (Creating and disposing GPU buffers every frame made meshes drop out of random frames on the L4 / ANGLE GL-EGL:
// every mesh is made once per scene and only its vertex positions change.)
function grid(nu, nv) {
  const pos = new Float32Array((nu + 1) * (nv + 1) * 3), idx = [];
  for (let j = 0; j < nv; j++) for (let i = 0; i < nu; i++) { const a = j * (nu + 1) + i, b = a + 1, c = a + nu + 1, e = c + 1; idx.push(a, c, b, b, c, e); }
  const g = new THREE.BufferGeometry(), attr = new THREE.BufferAttribute(pos, 3);
  attr.setUsage(THREE.DynamicDrawUsage); g.setAttribute('position', attr); g.setIndex(idx);
  g.userData = { nu, nv };
  return g;
}
// write f(u, v) → [x, y, z] into a grid geometry
function fill(g, f) {
  const { nu, nv } = g.userData, pos = g.attributes.position.array; let n = 0;
  for (let j = 0; j <= nv; j++) for (let i = 0; i <= nu; i++) { const p = f(i / nu, j / nv); pos[n++] = p[0]; pos[n++] = p[1]; pos[n++] = p[2]; }
  g.attributes.position.needsUpdate = true; g.computeVertexNormals(); g.computeBoundingSphere();
  if (g.attributes.normal) g.attributes.normal.needsUpdate = true;
}

// the curved surface; `un` unrolls a cylinder into a rectangle and a cone into a sector (arc length is kept)
function lateralF(d, T) {
  if (T.un > 0 && d.shape === 'cylinder') {
    const Rr = d.r / Math.max(1e-4, 1 - T.un);
    return (u, v) => { const a = ((u - 0.5) * TAU * d.r) / Rr; return [Rr * Math.sin(a), d.H * v, d.r - Rr + Rr * Math.cos(a)]; };
  }
  if (T.un > 0 && d.shape === 'cone') {
    const l = Math.hypot(d.r, d.H), rho = K.lerp(d.r, l, T.un), hk = Math.sqrt(Math.max(0, l * l - rho * rho)), th = T.un * Math.PI / 2;
    const c = Math.cos(th), s = Math.sin(th);
    return (u, v) => {
      const a = ((u - 0.5) * TAU * d.r) / rho, q = 1 - v;
      const x = q * rho * Math.sin(a), y = -q * hk, z = q * rho * Math.cos(a);
      return [x, d.H + y * c - z * s, y * s + z * c];
    };
  }
  const span = TAU * T.rev;
  return (u, v) => { const [rho, y] = profile(d, v), p = PHI0 - span * u; return [rho * Math.sin(p), y, rho * Math.cos(p)]; };
}
// a flat disk in the XZ plane (faces up), swept like the surface
const diskF = (rho, span) => (u, v) => { const p = PHI0 - span * u; return [rho * v * Math.sin(p), 0, rho * v * Math.cos(p)]; };
// liquid up to height lv: the surface of revolution below lv
const liquidF = (d, lv) => (u, v) => { const y = lv * v, rho = radiusAt(d, y) * 0.985, p = TAU * u; return [rho * Math.sin(p), y + 0.003, rho * Math.cos(p)]; };
// the flat generating shape, in the plane through the axis (x = distance from the axis)
const profileF = (d) => (u, v) => { const [rho, y] = profile(d, u); return [rho * v, y, 0]; };
// a cut face: horizontal at height y (disk / rectangle, XZ plane) or vertical through the axis (XY plane, x = across)
function sectionF(d, axis, y) {
  if (axis === 'h') {
    if (d.shape === 'cuboid') return (u, v) => [(u - 0.5) * d.L, 0, (v - 0.5) * d.B];
    const rho = radiusAt(d, y); return (u, v) => [rho * v * Math.sin(u * TAU), 0, rho * v * Math.cos(u * TAU)];
  }
  if (d.shape === 'cuboid') return (u, v) => [(v - 0.5) * d.B, u * d.H, 0];
  return (u, v) => { const [rho, yy] = profile(d, u); return [(2 * v - 1) * rho, yy, 0]; };
}

// ---------- the per-scene world: lights, ground, materials and all meshes, made once ----------
const WORLDS = new WeakMap();
function tint(hex, w) { return new THREE.Color(hex).lerp(new THREE.Color('#ffffff'), w); }

function world(sc) {
  if (WORLDS.has(sc)) return WORLDS.get(sc);
  const scene = new THREE.Scene(), cam = new THREE.PerspectiveCamera(30, 1.5, 0.05, 100);
  scene.add(new THREE.HemisphereLight('#ffffff', '#c9cce0', 1.6));
  const key = new THREE.DirectionalLight('#ffffff', 2.1); key.position.set(3, 6, 5); key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024); key.shadow.radius = 5; key.shadow.bias = -0.0005;
  Object.assign(key.shadow.camera, { left: -4, right: 4, top: 4, bottom: -4, near: 0.5, far: 20 }); key.shadow.camera.updateProjectionMatrix();
  scene.add(key);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(30, 30), new THREE.ShadowMaterial({ opacity: 0.14 }));
  ground.rotation.x = -Math.PI / 2; ground.position.y = -0.002; ground.receiveShadow = true; scene.add(ground);
  const plane = () => new THREE.Plane(new THREE.Vector3(0, -1, 0), 1e6);
  const pA = plane(), pB = plane();
  const base = K.NAMED[sc.solid && sc.solid.color] || K.C.primary;
  const mat = (col, clip, o = {}) => new THREE.MeshStandardMaterial({ color: col, roughness: 0.62, metalness: 0, side: THREE.DoubleSide, ...(clip ? { clippingPlanes: [clip], clipShadows: true } : {}), ...o });
  const W = { scene, cam, ground, pA, pB, base, dyn: new THREE.Group(),
    sideA: mat(tint(base, 0.32), pA), capA: mat(tint(base, 0.12), pA), sideB: mat(tint(base, 0.32), pB), capB: mat(tint(base, 0.12), pB),
    liquid: mat(tint('#3D8BFF', 0.25), null, { transparent: true, opacity: 0.9 }),
    section: mat(tint(K.C.gold, 0.15), null, { roughness: 0.7 }),
    prof: mat(tint(K.C.flame, 0.2), null, { roughness: 0.7, transparent: true }) };
  scene.add(W.dyn);
  const mesh = (parent, geo, m, shadow = true) => { const x = new THREE.Mesh(geo, m); x.castShadow = shadow; x.frustumCulled = false; x.visible = false; parent.add(x); return x; };
  const piece = (side, cap) => {
    const g = new THREE.Group(); W.dyn.add(g);
    const box = new THREE.BoxGeometry(1, 1, 1); box.translate(0, 0.5, 0);
    return { g, lat: mesh(g, grid(128, 48), side), cap0: mesh(g, grid(96, 2), cap), cap1: mesh(g, grid(96, 2), cap), box: mesh(g, box, side) };
  };
  W.A = piece(W.sideA, W.capA); W.B = piece(W.sideB, W.capB);
  W.liq = { lat: mesh(W.dyn, grid(96, 24), W.liquid, false), top: mesh(W.dyn, grid(96, 2), W.liquid, false), box: mesh(W.dyn, W.A.box.geometry, W.liquid, false) };
  W.prof = mesh(W.dyn, grid(64, 2), W.prof, false);
  W.secA = mesh(W.dyn, grid(96, 2), W.section, false); W.secB = mesh(W.dyn, grid(96, 2), W.section, false);
  WORLDS.set(sc, W);
  return W;
}

// pose one piece of the solid (curved surface + flat faces) for this frame
function posePiece(P, d, T) {
  P.g.visible = true;
  if (d.shape === 'cuboid') { P.box.visible = true; P.box.scale.set(d.L, d.H, d.B); return; }
  P.lat.visible = true; fill(P.lat.geometry, lateralF(d, T));
  const span = TAU * T.rev;
  caps(d).forEach(([y, rho], i) => {
    const m = i ? P.cap1 : P.cap0, top = i > 0; m.visible = true;
    if (T.un > 0 && (d.shape === 'cylinder' || d.shape === 'cone')) {
      // the flat faces swing out to touch the net (the textbook net picture)
      const e = T.un;
      fill(m.geometry, diskF(rho, TAU));
      if (d.shape === 'cylinder') m.position.set(0, top ? K.lerp(d.H, d.H + d.r, e) : K.lerp(0, -d.r, e), K.lerp(0, d.r, e));
      else m.position.set(0, K.lerp(0, d.H - Math.hypot(d.r, d.H) - d.r, e), 0);
      m.rotation.set(K.lerp(0, Math.PI / 2, e), 0, 0);
    } else { fill(m.geometry, diskF(rho, span)); m.position.set(0, y, 0); m.rotation.set(0, 0, 0); }
  });
}

// ---------- camera framing: fit the current content (solid, net, or cut pieces) ----------
function contentBox(d, T) {
  const wS = d.shape === 'cuboid' ? Math.hypot(d.L, d.B) : 2 * d.r, box = { cx: 0, cy: d.H / 2, w: wS, h: d.H };
  if (T.un > 0 && d.shape === 'cylinder') { const n = { cx: 0, cy: d.H / 2, w: TAU * d.r, h: d.H + 4 * d.r }; return mixBox(box, n, T.un); }
  if (T.un > 0 && d.shape === 'cone') {
    const l = Math.hypot(d.r, d.H), th = (TAU * d.r) / l, wN = th >= Math.PI ? 2 * l : 2 * l * Math.sin(th / 2);
    const top = th > Math.PI ? l * -Math.cos(th / 2) : 0, hN = l + 2 * d.r + Math.max(0, top);
    return mixBox(box, { cx: 0, cy: d.H + top - hN / 2, w: wN, h: hN }, T.un);
  }
  if (T.cut > 0) { const g = gap(d, T); return T.cutAxis === 'h' ? { ...box, cy: box.cy + g / 2, h: box.h + g } : { ...box, cx: g / 2, w: box.w + g }; }
  return box;
}
const mixBox = (a, b, e) => ({ cx: K.lerp(a.cx, b.cx, e), cy: K.lerp(a.cy, b.cy, e), w: K.lerp(a.w, b.w, e), h: K.lerp(a.h, b.h, e) });
const gap = (d, T) => 0.45 * T.cut * (T.cutAxis === 'h' ? 1 : 1.2);

// ---------- 2D overlays ----------
function projector(W, area) {
  const v = new THREE.Vector3();
  return (p) => { v.set(p[0], p[1], p[2]).applyMatrix4(W.dyn.matrixWorld).project(W.cam); return [area.x + (v.x + 1) / 2 * area.w, area.y + (1 - v.y) / 2 * area.h]; };
}
function depth(W, p) { const v = new THREE.Vector3(...p).applyMatrix4(W.dyn.matrixWorld).applyMatrix4(W.cam.matrixWorldInverse); return v.z; }

// rims (the textbook look): the back half of a bottom rim is dashed
function drawRims(W, d, P, a) {
  if (a <= 0.01 || d.shape === 'cuboid') return;
  const c = K.ctx, rims = caps(d).map(([y, rho], i) => ({ y, rho, top: i > 0 }));
  if (d.shape === 'sphere') rims.push({ y: d.r, rho: d.r, top: false });
  c.save(); c.globalAlpha = a * 0.75; c.strokeStyle = K.C.ink2; c.lineWidth = 3; c.lineCap = 'round';
  for (const rm of rims) {
    const zc = depth(W, [0, rm.y, 0]);
    for (const back of [false, true]) {
      if (back && rm.top) continue;
      c.setLineDash(back ? [10, 10] : []); c.beginPath(); let on = false;
      for (let i = 0; i <= 96; i++) {
        const ph = (i / 96) * TAU, p = [rm.rho * Math.sin(ph), rm.y, rm.rho * Math.cos(ph)];
        const isBack = !rm.top && depth(W, p) < zc;
        if (isBack !== back && !rm.top) { on = false; continue; }
        const [x, y] = P(p); if (!on) { c.moveTo(x, y); on = true; } else c.lineTo(x, y);
      }
      c.stroke();
    }
  }
  c.restore();
}

function dimSegments(d) {
  const f = 0.85;   // front-ish angle for radius / slant lines
  if (d.shape === 'cuboid') return {
    l: [[-d.L / 2, 0, d.B / 2], [d.L / 2, 0, d.B / 2]], b: [[d.L / 2, 0, d.B / 2], [d.L / 2, 0, -d.B / 2]], h: [[d.L / 2, 0, d.B / 2], [d.L / 2, d.H, d.B / 2]] };
  if (d.shape === 'sphere') return { r: [[0, d.r, 0], [d.r * Math.sin(f), d.r, d.r * Math.cos(f)]] };
  const out = { r: [[0, 0, 0], [d.r * Math.sin(f), 0, d.r * Math.cos(f)]] };
  if (d.shape !== 'hemisphere') out.h = [[0, 0, 0], [0, d.H, 0]];
  if (d.shape === 'cone') out.l = [[0, d.H, 0], [d.r * Math.sin(-f), 0, d.r * Math.cos(-f)]];
  if (d.shape === 'frustum') out.r2 = [[0, d.H, 0], [d.r2 * Math.sin(f), d.H, d.r2 * Math.cos(f)]];
  return out;
}
const fmt = (x) => String(Math.round(x * 10) / 10);
function dimLabel(so, d, key) {
  if (so.labels && so.labels[key]) return so.labels[key];
  const raw = d.raw[key], unit = so.unit || '';
  return raw ? `${key} = ${fmt(raw)}${unit ? ' ' + unit : ''}` : key;
}

function drawDims(W, d, so, P, T, a0) {
  const segs = dimSegments(d), c = K.ctx, ctr = P([0, d.H / 2, 0]);
  const want = {}, placed = [];
  T.shows.forEach((s) => { (s.dims || Object.keys(segs)).forEach((k) => { want[k] = Math.max(want[k] || 0, s.a); }); });
  for (const [key, a1] of Object.entries(want)) {
    const seg = segs[key], a = a1 * a0; if (!seg || a <= 0.01) continue;
    const [x1, y1] = P(seg[0]), [x2, y2] = P(seg[1]), inner = key === 'h' && d.shape !== 'cuboid';
    c.save(); c.globalAlpha = a; c.strokeStyle = K.C.primary; c.lineWidth = 5; c.lineCap = 'round'; c.setLineDash(inner ? [14, 10] : []);
    c.beginPath(); c.moveTo(x1, y1); c.lineTo(K.lerp(x1, x2, K.eo(a1)), K.lerp(y1, y2, K.eo(a1))); c.stroke();
    c.setLineDash([]); c.fillStyle = K.C.primary;
    for (const [x, y] of [[x1, y1], [x2, y2]]) { c.beginPath(); c.arc(x, y, 7, 0, TAU); c.fill(); }
    c.restore();
    // labels sit outside the solid, away from its centre; the height label sits just right of the axis
    const txt = dimLabel(so, d, key), size = 40, w = K.measure(txt, size, 700) + 36;
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2, dx = mx - ctr[0], dy = my - ctr[1], n = Math.hypot(dx, dy) || 1;
    const lx = inner ? mx + 22 + w / 2 : mx + (dx / n) * (30 + w / 2);
    let ly = inner ? my : my + (dy / n) * 46;
    // labels never sit on each other: move down past any label already placed
    const hits = (y) => placed.some((b) => Math.abs(b.x - lx) < (b.w + w) / 2 + 6 && Math.abs(b.y - y) < 70);
    for (let k = 0; k < 6 && hits(ly); k++) ly += 72;
    placed.push({ x: lx, y: ly, w });
    c.save(); c.globalAlpha = a; K.rr(lx - w / 2, ly - 34, w, 64, 32); c.fillStyle = K.C.surface; c.fill(); c.lineWidth = 3; c.strokeStyle = K.C.primary; c.stroke(); c.restore();
    K.text(txt, lx, ly + 13, { size, weight: 700, color: K.C.accentInk, align: 'center', alpha: a });
  }
}

// ---------- 2D fallback (no WebGL, or a blank frame) ----------
function fallback(S, area, d) {
  const type = d.shape === 'frustum' ? 'cone' : d.shape, k = 60 / Math.max(2 * d.r, d.H, d.shape === 'cuboid' ? d.L : 0);
  const sh = d.shape === 'cuboid' ? { type, x: 80 - (d.L * k) / 2, y: 74, w: d.L * k, h: d.H * k, r: d.B * k * 0.6 }
    : d.shape === 'sphere' ? { type, x: 80, y: 45, r: d.r * k } : { type, x: 80, y: 74, r: d.r * k, h: d.H * k };
  drawShapes([{ ...sh, line: 0, word: '', label: '', color: 'primary', fill: true, dashed: false, pts: [] }], area, S.t, () => 0);
}

// ---------- the frame ----------
// Is the frame missing the solid? (A safety net behind finish(): a frame with no pixels, or an empty pixel at `at`,
// a point in area pixels the solid must cover, is drawn again, and after 3 tries the 2D figure is drawn instead.)
function badFrame(w, h, at) {
  PCTX.clearRect(0, 0, PROBE.width, PROBE.height); PCTX.drawImage(GLC, 0, 0, w, h, 0, 0, PROBE.width, PROBE.height);
  const px = PCTX.getImageData(0, 0, PROBE.width, PROBE.height).data;
  let any = false;
  for (let i = 3; i < px.length; i += 4) if (px[i] > 8) { any = true; break; }
  if (!any) return true;
  if (!at) return false;
  const cx = Math.round((at[0] / w) * PROBE.width), cy = Math.round((at[1] / h) * PROBE.height);
  let best = 0;
  for (let y = cy - 1; y <= cy + 1; y++) for (let x = cx - 1; x <= cx + 1; x++) {
    if (x < 0 || y < 0 || x >= PROBE.width || y >= PROBE.height) continue;
    best = Math.max(best, px[(y * PROBE.width + x) * 4 + 3]);
  }
  return best < 40;
}

export function drawSolid(S, area) {
  const so = S.sc.solid || { shape: 'cylinder' }, d = dims(so), T = timeline(S), t = S.t;
  const appear = K.eo(K.prog(t, 0.1, 0.6));
  if (!GL.ok) { fallback(S, area, d); return false; }
  const W = world(S.sc);
  // one fixed-size drawing buffer (resizing it between scenes is another source of empty frames); render into the
  // top-left w × h of it
  const w = Math.min(GLC.width, Math.round(area.w)), h = Math.min(GLC.height, Math.round(area.h));
  R.setViewport(0, GLC.height - h, w, h); R.setScissor(0, GLC.height - h, w, h); R.setScissorTest(true);
  for (const o of W.dyn.children) o.visible = false;
  for (const P of [W.A, W.B]) for (const k of ['lat', 'cap0', 'cap1', 'box']) P[k].visible = false;

  // camera: idle drift + orbits; a revolve starts face-on to the profile; unrolling turns the net to the camera
  let yaw = -0.55 + 0.05 * t + T.orbit;
  yaw = Math.atan2(Math.sin(yaw), Math.cos(yaw));
  if (T.rev < 1) yaw = K.lerp(0, yaw, T.revStarted ? K.eio(K.prog(T.rev, 0, 1)) : 0);
  yaw = K.lerp(yaw, 0, T.un);
  W.dyn.rotation.y = yaw;
  // pieces: A is the whole solid, or the bottom / left piece of a cut; B is the top / right piece.
  // Clip planes live in world space: a vertical cut turns with the solid.
  const g = gap(d, T), cutting = T.cut > 0 && T.un === 0, cy = T.cutAt * d.H, cx = Math.cos(yaw), sx = Math.sin(yaw);
  if (cutting && T.cutAxis === 'h') { W.pA.normal.set(0, -1, 0); W.pA.constant = cy; W.pB.normal.set(0, 1, 0); W.pB.constant = -(cy + g); }
  else if (cutting) { W.pA.normal.set(-cx, 0, sx); W.pA.constant = 0; W.pB.normal.set(cx, 0, -sx); W.pB.constant = -g; }
  else { W.pA.normal.set(0, -1, 0); W.pA.constant = 1e6; }
  const revealed = T.revStarted ? T.rev : 0, Tg = { ...T, rev: Math.max(1e-3, revealed) };
  if (revealed > 0.001) {
    posePiece(W.A, d, Tg);
    if (cutting) {
      posePiece(W.B, d, Tg); W.B.g.position.set(T.cutAxis === 'h' ? 0 : g, T.cutAxis === 'h' ? g : 0, 0);
      for (const [m, off] of [[W.secA, 0.001], [W.secB, g - 0.001]]) {
        m.visible = true; fill(m.geometry, sectionF(d, T.cutAxis, cy));
        if (T.cutAxis === 'h') { m.position.set(0, cy + off, 0); m.rotation.set(0, 0, 0); }
        else { m.position.set(off, 0, 0); m.rotation.set(0, Math.PI / 2, 0); }
      }
    }
  }
  // the profile: the flat shape that sweeps round the axis
  if (T.rev < 1 && d.shape !== 'cuboid') {
    W.prof.visible = true; fill(W.prof.geometry, profileF(d));
    W.prof.material.opacity = T.revStarted ? 1 - K.prog(T.rev, 0.85, 0.15) : 1;
    W.prof.rotation.set(0, PHI0 - TAU * revealed - Math.PI / 2, 0);
  }
  // liquid filling the solid (the shell turns see-through)
  const filling = T.filling && T.un === 0 && !cutting;
  if (W.sideA.transparent !== filling) { for (const m of [W.sideA, W.capA]) { m.transparent = filling; m.depthWrite = !filling; m.needsUpdate = true; } }
  W.sideA.opacity = W.capA.opacity = filling ? K.lerp(1, 0.3, K.clamp(T.fill * 6)) : 1;
  if (filling) {
    const lv = T.fill * d.H;
    if (d.shape === 'cuboid') { W.liq.box.visible = true; W.liq.box.scale.set(d.L * 0.985, lv, d.B * 0.985); }
    else {
      W.liq.lat.visible = W.liq.top.visible = true; fill(W.liq.lat.geometry, liquidF(d, lv));
      fill(W.liq.top.geometry, diskF(radiusAt(d, lv) * 0.985, TAU)); W.liq.top.position.set(0, lv + 0.003, 0);
    }
  }
  // paint a part (curved surface, base, top, or all)
  const sideCol = tint(W.base, 0.32), capCol = tint(W.base, 0.12);
  for (const p of T.paints) {
    const to = tint(p.color, 0.1);
    if (p.part === 'curved' || p.part === 'all') sideCol.lerp(to, p.a);
    if (p.part !== 'curved') capCol.lerp(to, p.a);
  }
  W.sideA.color.copy(sideCol); W.sideB.color.copy(sideCol); W.capA.color.copy(capCol); W.capB.color.copy(capCol);

  const el = K.lerp(0.36, 0.08, T.un), box = contentBox(d, T), fov = 30 * Math.PI / 180, aspect = w / h;
  const fitV = (box.h / 2) / Math.tan(fov / 2), fitH = (box.w / 2) / (Math.tan(fov / 2) * aspect);
  const dist = Math.max(fitV, fitH) * 1.32 + Math.max(d.r, d.B || 0) + 0.4;
  W.cam.aspect = aspect; W.cam.fov = 30; W.cam.updateProjectionMatrix();
  W.cam.position.set(box.cx, box.cy + Math.sin(el) * dist, Math.cos(el) * dist); W.cam.lookAt(box.cx, box.cy, 0);
  W.ground.material.opacity = 0.14 * (1 - T.un);

  // finish() before the copy: without it, drawImage on the L4 (ANGLE GL-EGL) now and then copies a frame the GPU has
  // not finished (meshes missing, shadow there): every 4th frame in one browser, measured 2026-11-16
  const render = () => { R.render(W.scene, W.cam); R.getContext().finish(); };
  render(); GL.frames++;
  // a point the solid covers: the middle of the axis (of the lower piece when cut across), or the middle of the net
  let must = null;
  if (revealed >= 1) {
    const p = T.un > 0 && (d.shape === 'cylinder' || d.shape === 'cone') ? lateralF(d, T)(0.5, 0.5)
      : cutting && T.cutAxis === 'h' ? [0, cy * 0.5, 0] : [0, d.H / 2, 0];
    const q = new THREE.Vector3(...p).applyMatrix4(W.dyn.matrixWorld).project(W.cam);
    must = [(q.x + 1) / 2 * w, (1 - q.y) / 2 * h];
  }
  if (appear > 0.2) {
    let tries = 0;
    while (badFrame(w, h, must) && tries < 3) { render(); tries++; GL.redraws++; }
    if (tries === 3 && badFrame(w, h, must)) { GL.blank++; fallback(S, area, d); return false; }
  }
  const c = K.ctx;
  c.save(); c.globalAlpha *= appear; c.drawImage(GLC, 0, 0, w, h, area.x, area.y, area.w, area.h); c.restore();

  const P = projector(W, area), intact = (1 - T.un) * (1 - T.cut) * K.prog(T.rev, 0.9, 0.1);
  drawRims(W, d, P, appear * intact * (filling ? 0.6 : 1));
  drawDims(W, d, so, P, T, appear * (1 - T.un) * (1 - T.cut));
  return true;
}
