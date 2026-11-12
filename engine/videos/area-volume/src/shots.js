// CYLINDER KA AREA 2πrh KYUN? (Deep Dive 3D, Hinglish): the shot list.
// Real world: a tin can on the kitchen counter; its label is cut, peels off, unrolls and lies flat (a 2πr × h rectangle);
// coins stack into the can's shape (πr²h). X-ray stage: glass shapes whose surfaces open into glowing nets
// (cylinder → rectangle + 2 lids, cone → sector + base), and three cones of water fill one cylinder (⅓πr²h).
// Every surface that opens is ONE mesh whose vertices are a pure function of an "open" amount k (0 wrapped → 1 flat).
import * as THREE from 'three';
import { ctx, W, H, clamp, lerp, seg, eo, eio, eob } from './core/lib.js';
import { L, T, lineWords } from './core/timing.js';
import { camera } from './core/engine.js';
import * as SETS from './core/sets.js';
import { label, pill } from './core/look2d.js';

const V3 = (x, y, z) => new THREE.Vector3(x, y, z);
const lerpV = (a, b, k) => a.clone().lerp(b, k);
const PI = Math.PI, TAU = PI * 2;
function screen(p, cam) { const v = p.clone().project(cam); return [(v.x + 1) / 2 * W, (1 - v.y) / 2 * H]; }
const YEL = '#FFD43B', CYAN = '#4FD1E8';

// ═══════════════ textures ═══════════════
function tex(w, h, draw, flipX = false) { const c = document.createElement('canvas'); c.width = w; c.height = h; draw(c.getContext('2d'), w, h); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; if (flipX) { t.wrapS = THREE.RepeatWrapping; t.repeat.x = -1; } return t; }
const FONT = (wt, px) => `${wt} ${px}px Inter, "Nirmala UI", sans-serif`;
/** the soup-can label (an invented brand) */
const labelTex = () => tex(2048, 640, (g, w, h) => {
  g.fillStyle = '#F4EBDD'; g.fillRect(0, 0, w, h);
  g.fillStyle = '#C8372D'; g.fillRect(0, 0, w, 150); g.fillRect(0, h - 150, w, 150);
  g.fillStyle = '#E8B04A'; g.fillRect(0, 150, w, 16); g.fillRect(0, h - 166, w, 16);
  for (const x0 of [0, w / 2]) {
    g.fillStyle = '#C8372D'; g.font = FONT(900, 150); g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText('MATH SOUP', x0 + w / 4, h / 2 - 10);
    g.fillStyle = '#3B2A20'; g.font = FONT(800, 46); g.fillText('CREAMY  ·  π  FLAVOUR', x0 + w / 4, h / 2 + 105);
    g.fillStyle = '#FFFFFF'; g.font = FONT(900, 60); g.fillText('★ ★ ★', x0 + w / 4, 78); g.fillText('NET WT 400 g', x0 + w / 4, h - 76);
  }
}, true);
/** a glowing glass net panel: faint cyan fill, bright border, light grid */
const glassTex = (grid = 10, gy = 4) => tex(1024, 512, (g, w, h) => {
  g.fillStyle = 'rgba(79,209,232,0.16)'; g.fillRect(0, 0, w, h);
  g.strokeStyle = 'rgba(79,209,232,0.35)'; g.lineWidth = 3; for (let i = 1; i < grid; i++) { g.beginPath(); g.moveTo(i * w / grid, 0); g.lineTo(i * w / grid, h); g.stroke(); } for (let i = 1; i < gy; i++) { g.beginPath(); g.moveTo(0, i * h / gy); g.lineTo(w, i * h / gy); g.stroke(); }
  g.strokeStyle = '#BFF6FF'; g.lineWidth = 22; g.strokeRect(0, 0, w, h);
});
const discTex = () => tex(512, 512, (g, w) => { g.fillStyle = 'rgba(79,209,232,0.2)'; g.beginPath(); g.arc(w / 2, w / 2, w / 2 - 12, 0, TAU); g.fill(); g.strokeStyle = '#BFF6FF'; g.lineWidth = 20; g.stroke(); g.strokeStyle = 'rgba(79,209,232,0.4)'; g.lineWidth = 3; g.beginPath(); g.moveTo(w / 2, 12); g.lineTo(w / 2, w - 12); g.moveTo(12, w / 2); g.lineTo(w - 12, w / 2); g.stroke(); });
const gridTex = () => tex(1024, 320, (g, w, h) => { g.strokeStyle = YEL; g.lineWidth = 5; for (let i = 0; i <= 16; i++) { g.beginPath(); g.moveTo(i * w / 16, 0); g.lineTo(i * w / 16, h); g.stroke(); } for (let i = 0; i <= 5; i++) { g.beginPath(); g.moveTo(0, i * h / 5); g.lineTo(w, i * h / 5); g.stroke(); } g.lineWidth = 16; g.strokeRect(0, 0, w, h); });
const glow = (map, opacity = 1) => new THREE.MeshBasicMaterial({ map, transparent: true, opacity, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });

// ═══════════════ surfaces that open ═══════════════
/** a cylinder's side as one sheet. k = 0: wrapped round a cylinder of radius R; 1: flat (Lw = 2πR wide, Lh tall).
 *  Origin = the middle of its bottom edge (the point that stays put); sign +1 = the cylinder's axis is at +z of it. */
function wrapSheet(R, Lh, mat, sign = 1) {
  const geo = new THREE.PlaneGeometry(1, 1, 160, 4), uv = geo.attributes.uv, pos = geo.attributes.position, Lw = TAU * R;
  const m = new THREE.Mesh(geo, mat); m.castShadow = true; m.receiveShadow = true;
  m.userData.set = (k) => {
    k = clamp(k, 0, 1); const rho = k > 0.9995 ? Infinity : R / (1 - k);
    for (let i = 0; i < pos.count; i++) {
      const s = (uv.getX(i) - 0.5) * Lw, y = uv.getY(i) * Lh;
      if (rho === Infinity) pos.setXYZ(i, s, y, 0);
      else { const f = s / rho; pos.setXYZ(i, rho * Math.sin(f), y, sign * rho * (1 - Math.cos(f))); }
    }
    pos.needsUpdate = true; geo.computeVertexNormals(); geo.computeBoundingSphere();
  };
  m.userData.set(0); return m;
}
/** a cone's side as one sheet (apex at the origin, opening downward). k = 0: the cone (base radius r, height h);
 *  1: flat sector of radius l = slant height and angle 2πr/l, lying in the xz-plane. Same paper all the way. */
function coneSheet(r, h, mat) {
  const l = Math.hypot(r, h), phi = TAU * r / l;
  const geo = new THREE.PlaneGeometry(1, 1, 120, 24), uv = geo.attributes.uv, pos = geo.attributes.position;
  const m = new THREE.Mesh(geo, mat);
  m.userData.l = l; m.userData.phi = phi;
  m.userData.set = (k) => {
    const sb = lerp(r / l, 1, clamp(k)), cb = Math.sqrt(Math.max(0, 1 - sb * sb)), th = phi / sb;
    for (let i = 0; i < pos.count; i++) { const a = (uv.getX(i) - 0.5) * th, s = (1 - uv.getY(i)) * l; pos.setXYZ(i, s * sb * Math.sin(a), -s * cb, s * sb * Math.cos(a)); }
    pos.needsUpdate = true; geo.computeVertexNormals(); geo.computeBoundingSphere();
  };
  m.userData.set(0); return m;
}

export function buildShots(E) {
  const S = [], CUES = [], add = (o) => (S.push(o), o), cue = (t, type, o = {}) => CUES.push({ t: +Math.max(0, t).toFixed(3), type, ...o });
  const cut = (i) => (i === 0 ? 0 : L(i) - 0.08);
  const Wi = (line, i) => { const ws = lineWords(line); return ws[Math.min(i, ws.length - 1)].s; };   // spoken word i of a line
  const shotEnd = (i) => (i + 1 < T.lines.length ? cut(i + 1) : T.dur);
  const cam = camera(30);
  const KLOOK = { aperture: 0.0025, maxblur: 0.008, bloom: 0.22 }, XLOOK = { aperture: 0.001, maxblur: 0.005, bloom: 0.75, bloomThreshold: 0.25, vignette: 0.45 };

  // ═══════════════ the kitchen: the can, its label, coins ═══════════════
  const K = SETS.kitchen(E);
  const Y0 = 0.955, CX = -0.25, CZ = -1.96, R = 0.12, CH = 0.3, LR = R + 0.004, LY = 0.03, LH = 0.24;   // can + label
  const SX = CX, SZ = -1.64;                                                                                // where the flat label lies
  const metal = new THREE.MeshStandardMaterial({ color: '#C9CED4', metalness: 0.92, roughness: 0.28 });
  const can = new THREE.Group(); can.position.set(CX, Y0, CZ); K.scene.add(can);
  const body = new THREE.Mesh(new THREE.CylinderGeometry(R, R, CH, 96), metal); body.position.y = CH / 2; body.castShadow = body.receiveShadow = true; can.add(body);
  const rimMat = new THREE.MeshStandardMaterial({ color: '#D7DCE2', metalness: 0.95, roughness: 0.22, emissive: YEL, emissiveIntensity: 0 });
  const rimTop = new THREE.Mesh(new THREE.TorusGeometry(R, 0.008, 12, 96), rimMat); rimTop.rotation.x = PI / 2; rimTop.position.y = CH; can.add(rimTop);
  const rimBot = new THREE.Mesh(new THREE.TorusGeometry(R, 0.008, 12, 96), metal); rimBot.rotation.x = PI / 2; rimBot.position.y = 0.004; can.add(rimBot);
  const lid = new THREE.Mesh(new THREE.CircleGeometry(R - 0.004, 96), new THREE.MeshStandardMaterial({ color: '#B9BEC4', metalness: 0.9, roughness: 0.35 })); lid.rotation.x = -PI / 2; lid.position.y = CH - 0.006; can.add(lid);
  const paper = new THREE.MeshStandardMaterial({ map: labelTex(), roughness: 0.6, side: THREE.DoubleSide });
  const labelG = new THREE.Group(), sheet = wrapSheet(LR, LH, paper, 1); labelG.add(sheet); K.scene.add(labelG);
  const cutLine = new THREE.Mesh(new THREE.BoxGeometry(0.006, 1, 0.004), new THREE.MeshBasicMaterial({ color: new THREE.Color('#FF4A3D').multiplyScalar(2.2) }));
  K.scene.add(cutLine);
  const gridM = new THREE.MeshBasicMaterial({ map: gridTex(), transparent: true, opacity: 0, depthWrite: false });
  const grid = new THREE.Mesh(new THREE.PlaneGeometry(TAU * LR, LH), gridM); grid.rotation.x = -PI / 2; grid.position.set(SX, Y0 + 0.006, SZ); K.scene.add(grid);
  const edgeM = new THREE.MeshBasicMaterial({ color: new THREE.Color(YEL).multiplyScalar(1.6), transparent: true, opacity: 0 });
  const edge = new THREE.Mesh(new THREE.BoxGeometry(TAU * LR, 0.006, 0.01), edgeM); edge.position.set(SX, Y0 + 0.006, SZ - LH / 2); K.scene.add(edge);
  // coins: 27 of them make a stack exactly as tall as the can
  const NC = 27, CT = CH / NC, coinM = new THREE.MeshStandardMaterial({ color: '#E2B04E', metalness: 0.88, roughness: 0.3 });
  const coinX = CX + 0.4, coinZ = -1.72, coins = [];
  for (let i = 0; i < NC; i++) { const c = new THREE.Mesh(new THREE.CylinderGeometry(R, R, CT * 0.92, 64), coinM); c.castShadow = c.receiveShadow = true; c.visible = false; K.scene.add(c); coins.push(c); }

  /** pose the label: lift, open k, spin to face the camera, move + lay flat on the counter. All 0..1. */
  function poseLabel({ lift = 0, k = 0, spin = 0, lay = 0 } = {}) {
    sheet.userData.set(k);
    const a = V3(CX, Y0 + LY + 0.36 * lift, CZ - LR), b = V3(SX, Y0 + 0.004, SZ + LH / 2);
    labelG.position.copy(lerpV(a, b, lay)); labelG.rotation.set(-PI / 2 * lay, PI * spin, 0);
  }
  // the label's timeline, on the narration: cut on "काट", lift on "लेबल", open on "खोलो", lay on "बिछा"
  const tCut = Wi(1, 7), tLift = Wi(2, 1), tOpen = Wi(2, 2), tLay = Wi(2, 5);
  const labelAt = (t) => ({ lift: eio(seg(t, tLift - 0.15, tLift + 0.35)), k: eio(seg(t, tOpen - 0.1, tOpen + 0.8)), spin: eio(seg(t, tOpen - 0.05, tOpen + 0.8)), lay: eio(seg(t, Math.min(tLay - 0.25, tOpen + 0.7), tLay + 0.45)) });
  const kitchenReset = (t) => {
    poseLabel(labelAt(t)); sheet.visible = true; cutLine.visible = false; gridM.opacity = 0; edgeM.opacity = 0; rimMat.emissiveIntensity = 0; coins.forEach((c) => (c.visible = false));
  };
  const kRender = (target, extra = {}) => E.render(K.scene, cam, { ...KLOOK, focus: cam.position.distanceTo(target), ...extra });
  const CAN = V3(CX, Y0 + CH * 0.55, CZ), SHEET = V3(SX, Y0, SZ);

  // ═══════════════ the x-ray stage: glass nets + pouring ═══════════════
  const X = SETS.xrayStage(E), XE = 0.8;                          // everything sits 0.8 above the grid floor
  const XR = 0.35, XH = 0.9, CR = 0.35, CHc = 0.9;
  const net = new THREE.Group(); net.position.y = XE; X.scene.add(net);
  const xSide = wrapSheet(XR, XH, glow(glassTex(16, 4)), -1); xSide.position.set(0, 0, XR); net.add(xSide);
  const lidT = new THREE.Mesh(new THREE.CircleGeometry(XR, 96), glow(discTex())), lidB = lidT.clone(); net.add(lidT, lidB);
  const coneG = new THREE.Group(); coneG.position.set(0, XE + CHc, 0); X.scene.add(coneG);
  const cSide = coneSheet(CR, CHc, glow(glassTex(12, 4))); coneG.add(cSide);
  const cBase = new THREE.Mesh(new THREE.CircleGeometry(CR, 96), glow(discTex())); X.scene.add(cBase);
  // pouring: a glass cylinder + a glass cone cup (same base, same height), cyan water
  const xm = SETS.xrayMaterial(CYAN, 0.7), water = new THREE.MeshStandardMaterial({ color: '#2FB8D6', emissive: '#1BA3C2', emissiveIntensity: 0.35, transparent: true, opacity: 0.85, roughness: 0.2 });
  const pour = new THREE.Group(); pour.position.y = 0.0; X.scene.add(pour);
  const PR = 0.3, PH = 0.8, PX = 0.32;
  const pCyl = new THREE.Mesh(new THREE.CylinderGeometry(PR, PR, PH, 64, 1, true), xm); pCyl.position.set(PX, PH / 2, 0); pour.add(pCyl);
  const pRim = new THREE.Mesh(new THREE.TorusGeometry(PR, 0.008, 8, 64), new THREE.MeshBasicMaterial({ color: '#BFF6FF' })); pRim.rotation.x = PI / 2; pRim.position.set(PX, PH, 0); pour.add(pRim);
  const pWater = new THREE.Mesh(new THREE.CylinderGeometry(PR * 0.97, PR * 0.97, 1, 64), water); pour.add(pWater);
  const cup = new THREE.Group(); pour.add(cup);                                 // the cone cup: apex down, opening up
  const cupGlass = new THREE.Mesh(new THREE.ConeGeometry(PR, PH, 64, 1, true), xm); cupGlass.rotation.x = PI; cupGlass.position.y = PH / 2; cup.add(cupGlass);
  const cupWater = new THREE.Mesh(new THREE.ConeGeometry(PR * 0.95, PH * 0.95, 48), water); cupWater.rotation.x = PI; cupWater.position.y = PH * 0.95 / 2; cup.add(cupWater);
  const stream = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.035, 1, 16), water); pour.add(stream);
  const xReset = () => { net.visible = coneG.visible = cBase.visible = pour.visible = false; };
  const xRender = (target, extra = {}) => E.render(X.scene, cam, { ...XLOOK, focus: cam.position.distanceTo(target), ...extra });
  /** the cylinder net: open 0..1 (side unrolls, lids swing out to sit above + below the rectangle) */
  function poseNet(open) {
    net.visible = true; xSide.userData.set(open);
    const p = eio(clamp(open));
    lidT.position.copy(lerpV(V3(0, XH, 0), V3(0, XH + XR + 0.01, XR), p)); lidT.rotation.set(lerp(-PI / 2, 0, p), 0, 0);
    lidB.position.copy(lerpV(V3(0, 0, 0), V3(0, -XR - 0.01, XR), p)); lidB.rotation.set(lerp(PI / 2, 0, p), 0, 0);
  }
  /** the cone: open 0..1 (side flattens to a sector), stand 0..1 (the sector turns to face us), base drops below */
  function poseCone(open, stand) {
    coneG.visible = cBase.visible = true; cSide.userData.set(open); coneG.rotation.x = PI / 2 * stand;
    const l = cSide.userData.l, p = eio(clamp(open));
    cBase.position.copy(lerpV(V3(0, XE, 0), V3(0, XE + CHc - l - CR - 0.08, 0.02), p)); cBase.rotation.set(lerp(-PI / 2, 0, p), 0, 0);
  }
  /** pouring state: level 0..1 in the cylinder, cup position/tilt, cup water, stream on/off */
  function posePour(t0, t1, t) {
    pour.visible = true; const per = (t1 - t0) / 3; let level = 0, cupFill = 1, tilt = 0, move = 0, flow = 0, n = 0;
    for (let i = 0; i < 3; i++) {
      const a = t0 + i * per, up = seg(t, a, a + per * 0.3), tl = seg(t, a + per * 0.25, a + per * 0.45), fl = seg(t, a + per * 0.4, a + per * 0.8), back = seg(t, a + per * 0.8, a + per);
      if (t >= a) { n = i + 1; move = eio(up) * (1 - eio(back)); tilt = eio(tl) * (1 - eio(back)); flow = fl > 0 && fl < 1 ? 1 : 0; cupFill = back > 0 ? 1 : 1 - fl; level = (i + fl) / 3; }
    }
    const rest = V3(-0.5, 0, 0), over = V3(PX - 0.36, PH + 0.22, 0);
    cup.position.copy(lerpV(rest, over, move)); cup.rotation.set(0, 0, -1.95 * tilt);
    cupWater.visible = cupFill > 0.02; cupWater.scale.set(lerp(0.35, 1, cupFill), cupFill, lerp(0.35, 1, cupFill));
    pWater.visible = level > 0.005; pWater.scale.y = Math.max(0.001, level * PH); pWater.position.set(PX, level * PH / 2, 0);
    stream.visible = flow > 0; const top = PH + 0.2, bot = level * PH; stream.scale.y = Math.max(0.01, top - bot); stream.position.set(PX - 0.06, (top + bot) / 2, 0);
    return { n: Math.min(3, n), level };
  }

  /** 2D: a yellow measuring bracket between two 3D points, with a value tag */
  function bracket(a, b, text, p, cam, side = 1, tagAt = 0.5) {
    if (p <= 0) return; const [x0, y0] = screen(a, cam), [x1, y1] = screen(b, cam), x = lerp(x0, x1, clamp(p)), y = lerp(y0, y1, clamp(p));
    const ang = Math.atan2(y1 - y0, x1 - x0), nx = -Math.sin(ang) * 18 * side, ny = Math.cos(ang) * 18 * side;
    ctx.save(); ctx.strokeStyle = YEL; ctx.lineWidth = 7; ctx.lineCap = 'round'; ctx.shadowColor = 'rgba(0,0,0,0.6)'; ctx.shadowBlur = 10;
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x, y); ctx.moveTo(x0 - nx, y0 - ny); ctx.lineTo(x0 + nx, y0 + ny); if (p >= 1) { ctx.moveTo(x1 - nx, y1 - ny); ctx.lineTo(x1 + nx, y1 + ny); } ctx.stroke(); ctx.restore();
    if (text && p >= 1) pill(text, lerp(x0, x1, tagAt) + nx * 3.2, lerp(y0, y1, tagAt) + ny * 3.2, 1, YEL, 'rgba(12,14,20,0.82)', 56);
  }
  const F = (text, y, sc, col = YEL, size = 80) => pill(text, 540, y, sc, col, 'rgba(12,14,20,0.82)', size);   // a formula pill
  const orbit = (target, dist, yaw, pitch) => { cam.position.set(target.x + Math.sin(yaw) * Math.cos(pitch) * dist, target.y + Math.sin(pitch) * dist, target.z + Math.cos(yaw) * Math.cos(pitch) * dist); cam.lookAt(target); };

  // ── 1 · HOOK: the can on the counter, the camera glides in, "2πrh ?" ───────────────────────
  const HOOK0 = { tgt: V3(CX, Y0 + 0.17, CZ), d0: 1.55, d1: 1.2, yaw0: 0.42, yaw1: 0.2, pitch: 0.2 };
  const hookCam = (k) => orbit(HOOK0.tgt, lerp(HOOK0.d0, HOOK0.d1, k), lerp(HOOK0.yaw0, HOOK0.yaw1, k), HOOK0.pitch);
  { const st = 0, d = shotEnd(0), q = Wi(0, 3) - st, why = Wi(0, 7) - st;
    add({ id: 'S01', at: st, note: 'can on the counter, slow push in, 2πrh ? pill', draw(lt, dd, t, blit) {
      kitchenReset(0); hookCam(eio(lt / d)); kRender(HOOK0.tgt); blit();
      F('2πrh', 330, eob(seg(lt, q, q + 0.25)), YEL, 110);
      if (lt > why) pill('?', 800, 300, eob(seg(lt, why, why + 0.2)), '#FFFFFF', 'rgba(214,40,57,0.92)', 100);
    } });
    cue(st + q, 'pop'); cue(st + why, 'boing', { gain: 0.5 }); }

  // ── 2 · the knife line runs down the front of the label ───────────────────────────────────
  { const st = cut(1), ct = tCut - st;
    add({ id: 'S02', at: st, note: 'close on the can, red cut line runs down the label on "काट"', draw(lt, d, t, blit) {
      kitchenReset(t);
      const p = eo(seg(lt, ct - 0.05, ct + 0.4)); cutLine.visible = p > 0; cutLine.scale.y = Math.max(0.001, LH * p); cutLine.position.set(CX, Y0 + LY + LH - LH * p / 2, CZ + LR + 0.003);
      orbit(V3(CX, Y0 + 0.15, CZ), lerp(0.95, 0.78, eio(lt / d)), lerp(-0.25, 0.08, eio(lt / d)), 0.12); kRender(V3(CX, Y0 + 0.15, CZ + R)); blit();
      if (lt > ct + 0.2) { const [x, y] = screen(V3(CX, Y0 + 0.2, CZ + LR), cam); label('CUT', x + 210, y - 160, x, y, eob(seg(lt, ct + 0.2, ct + 0.45))); }
    } });
    cue(st, 'whoosh'); cue(tCut, 'zip', { gain: 0.8 }); }

  // ── 3 · the label lifts, unrolls in mid-air, spins to face us and lies flat ───────────────
  { const st = cut(2);
    add({ id: 'S03', at: st, note: 'label lifts off, unrolls + spins, lies flat in front of the can', draw(lt, d, t, blit) {
      kitchenReset(t);
      const k = eio(lt / d), tgt = lerpV(V3(CX, Y0 + 0.42, CZ + 0.05), V3(CX, Y0 + 0.06, (CZ + SZ) / 2), k);
      orbit(tgt, lerp(2.5, 2.9, k), lerp(0.3, 0.05, k), lerp(0.1, 0.62, k)); kRender(tgt); blit();
    } });
    cue(st, 'whoosh'); cue(tLift, 'slide', { dur: 0.5, gain: 0.5 }); cue(tOpen, 'whoosh', { gain: 0.7 }); cue(tOpen + 0.1, 'slide', { dur: 0.8, gain: 0.5 }); cue(tLay + 0.4, 'thud', { gain: 0.5 }); }

  // ── 4 · "ye ban gaya ek rectangle!": high angle, outline pops ─────────────────────────────
  { const st = cut(3), rc = Wi(3, 5) - st;
    add({ id: 'S04', at: st, note: 'high angle on the flat label, RECTANGLE on "रेक्टेंगल"', draw(lt, d, t, blit) {
      kitchenReset(t); orbit(V3(SX, Y0 + 0.02, SZ - 0.06), lerp(3.2, 2.95, eio(lt / d)), lerp(-0.1, 0.06, eio(lt / d)), 0.95);
      edgeM.opacity = 0; kRender(SHEET); blit();
      if (lt > rc) { const c = [[-1, 1], [1, 1], [1, -1], [-1, -1]].map(([sx, sz]) => screen(V3(SX + sx * PI * LR, Y0 + 0.005, SZ + sz * LH / 2), cam)), p = eio(seg(lt, rc, rc + 0.45));
        ctx.save(); ctx.strokeStyle = YEL; ctx.lineWidth = 9; ctx.lineJoin = 'round'; ctx.shadowColor = 'rgba(0,0,0,0.5)'; ctx.shadowBlur = 12; ctx.beginPath(); let left = p * 4; ctx.moveTo(...c[0]);
        for (let i = 1; i <= 4 && left > 0; i++) { const a = c[i - 1], b = c[i % 4], q = Math.min(1, left); ctx.lineTo(lerp(a[0], b[0], q), lerp(a[1], b[1], q)); left -= 1; } ctx.stroke(); ctx.restore();
        pill('RECTANGLE', 540, 420, eob(seg(lt, rc + 0.1, rc + 0.35)), YEL, 'rgba(12,14,20,0.82)', 70); }
    } });
    cue(st, 'whoosh'); cue(st + rc, 'slide', { dur: 0.45, gain: 0.4 }); cue(st + rc + 0.15, 'pop'); }

  // ── 5 · height: the same h on the label and on the can ────────────────────────────────────
  { const st = cut(4), h1 = Wi(4, 1) - st, h2 = Wi(4, 4) - st, hh = Wi(4, 6) - st;
    add({ id: 'S05', at: st, note: 'brackets: label short side = can height, h', draw(lt, d, t, blit) {
      kitchenReset(t); orbit(V3(CX, Y0 + 0.08, -1.78), lerp(3.0, 2.75, eio(lt / d)), lerp(0.4, 0.3, eio(lt / d)), 0.5); kRender(V3(CX, Y0 + 0.08, -1.78)); blit();
      const x0 = SX + PI * LR + 0.03;
      bracket(V3(x0, Y0 + 0.01, SZ + LH / 2), V3(x0, Y0 + 0.01, SZ - LH / 2), lt > hh ? 'h' : null, eo(seg(lt, h1 - 0.1, h1 + 0.35)), cam, -1);
      bracket(V3(CX + R + 0.04, Y0 + LY, CZ), V3(CX + R + 0.04, Y0 + LY + LH, CZ), lt > hh ? 'h' : null, eo(seg(lt, h2 - 0.1, h2 + 0.35)), cam, -1);
    } });
    cue(st, 'whoosh'); cue(st + h1, 'slide', { dur: 0.35, gain: 0.4 }); cue(st + h2, 'slide', { dur: 0.35, gain: 0.4 }); cue(st + hh, 'pop'); }

  // ── 6 · length: the label's long edge = the rim it was wrapped round ─────────────────────
  { const st = cut(5), ln = Wi(5, 2) - st, ar = Wi(5, 8) - st;
    add({ id: 'S06', at: st, note: 'long edge glows on "लंबाई", can rim glows on "चारों तरफ़"', draw(lt, d, t, blit) {
      kitchenReset(t); edgeM.opacity = eo(seg(lt, ln - 0.1, ln + 0.3)) * (0.75 + 0.25 * Math.sin(lt * 9));
      rimMat.emissiveIntensity = lt > ar ? 2.2 * eo(seg(lt, ar, ar + 0.3)) * (0.75 + 0.25 * Math.sin(lt * 9)) : 0;
      orbit(V3(CX, Y0 + 0.08, -1.78), lerp(3.0, 2.7, eio(lt / d)), lerp(-0.3, -0.1, eio(lt / d)), 0.55); kRender(V3(CX, Y0 + 0.08, -1.78)); blit();
      if (lt > ar + 0.2) { const [x, y] = screen(V3(CX - R * 0.7, Y0 + CH, CZ + R * 0.7), cam); label('RIM', x - 170, y - 170, x, y, eob(seg(lt, ar + 0.2, ar + 0.45))); }
    } });
    cue(st, 'whoosh'); cue(st + ln, 'sparkle', { dur: 0.6, gain: 0.5 }); cue(st + ar, 'sparkle', { dur: 0.8, gain: 0.5 }); }

  // ── 7 · …circumference, 2πr ───────────────────────────────────────────────────────────────
  { const st = cut(6), tw = Wi(6, 2) - st;
    add({ id: 'S07', at: st, note: 'bracket along the long edge: 2πr', draw(lt, d, t, blit) {
      kitchenReset(t); edgeM.opacity = 0.9; rimMat.emissiveIntensity = 1.6;
      orbit(V3(SX, Y0 + 0.04, -1.72), lerp(3.0, 2.8, eio(lt / d)), lerp(0.1, -0.06, eio(lt / d)), 0.7); kRender(V3(SX, Y0, -1.7)); blit();
      bracket(V3(SX - PI * LR, Y0 + 0.01, SZ + LH / 2 + 0.05), V3(SX + PI * LR, Y0 + 0.01, SZ + LH / 2 + 0.05), lt > tw ? '2πr' : null, eo(seg(lt, 0.05, Math.max(0.3, tw))), cam, 1);
    } });
    cue(st, 'whoosh'); cue(st + 0.05, 'slide', { dur: 0.5, gain: 0.4 }); cue(st + tw, 'pop'); }

  // ── 8 · area = length × height = 2πrh: a grid fills the label ─────────────────────────────
  { const st = cut(7), ar = Wi(7, 3) - st;
    add({ id: 'S08', at: st, note: 'yellow grid sweeps over the label, 2πr × h = 2πrh', draw(lt, d, t, blit) {
      kitchenReset(t); const p = eio(seg(lt, 0.05, Math.max(0.6, ar)));
      gridM.opacity = p > 0 ? 0.95 : 0; grid.scale.x = Math.max(0.001, p); grid.position.x = SX - PI * LR * (1 - p);
      orbit(V3(SX, Y0 + 0.02, SZ - 0.04), lerp(3.1, 2.9, eio(lt / d)), lerp(-0.08, 0.08, eio(lt / d)), 1.0); kRender(SHEET); blit();
      F('2πr × h', 380, eob(seg(lt, 0.15, 0.4)), '#FFFFFF', 76);
      if (lt > ar) F('= 2πrh', 520, eob(seg(lt, ar, ar + 0.25)), YEL, 110);
    } });
    cue(st, 'whoosh'); cue(st + 0.05, 'slide', { dur: 0.7, gain: 0.45 }); cue(st + ar, 'sparkle', { dur: 1, gain: 0.6 }); cue(st + ar, 'pop'); }

  // ── 9 · x-ray: the glass cylinder opens into its net, lids swing out ─────────────────────
  const NET = V3(0, XE + XH / 2, XR);
  { const st = cut(8), lids = Wi(8, 4) - st, each = Wi(8, 6) - st;
    add({ id: 'S09', at: st, note: 'glass cylinder → net (rectangle + 2 lids), πr² on each lid', draw(lt, d, t, blit) {
      xReset(); const open = eio(seg(lt, 0.1, Math.max(1.2, lids + 0.5))); poseNet(open);
      orbit(V3(0, XE + XH / 2, lerp(0, XR, open)), lerp(5.2, 8.2, eio(seg(lt, 0, lids + 0.6))), lerp(0.55, 0.0, eio(lt / d)), lerp(0.35, 0.04, eio(lt / d))); xRender(NET); blit();
      if (lt > each) { for (const y of [XH + XR, -XR]) { const [x, yy] = screen(V3(0, XE + y, XR), cam); pill('πr²', x + 260, yy, eob(seg(lt, each, each + 0.25)), CYAN, 'rgba(8,16,28,0.85)', 58); } }
    } });
    cue(st, 'whoosh'); cue(st + 0.1, 'slide', { dur: 1.1, gain: 0.5 }); cue(st + lids, 'pop', { gain: 0.6 }); cue(st + lids + 0.15, 'pop', { gain: 0.6 }); cue(st + each, 'sparkle', { dur: 0.6, gain: 0.5 }); }

  // ── 10 · total = 2πrh + 2πr² ──────────────────────────────────────────────────────────────
  { const st = cut(9), plus = Wi(9, 6) - st;
    add({ id: 'S10', at: st, note: 'full net glows, total formula', draw(lt, d, t, blit) {
      xReset(); poseNet(1); orbit(NET, lerp(8.0, 7.4, eio(lt / d)), lerp(-0.12, 0.1, eio(lt / d)), 0.05); xRender(NET); blit();
      const [rx, ry] = screen(V3(0, XE + XH / 2, XR), cam); pill('2πrh', rx, ry, eob(seg(lt, 0.15, 0.4)), YEL, 'rgba(8,16,28,0.85)', 62);
      F('2πrh + 2πr²', 330, eob(seg(lt, plus - 0.1, plus + 0.2)), YEL, 92);
    } });
    cue(st, 'whoosh'); cue(st + 0.15, 'pop', { gain: 0.5 }); cue(st + plus, 'stamp', { gain: 0.6 }); }

  // ── 11 · the glass cone opens into a sector ───────────────────────────────────────────────
  const CONE = V3(0, XE + CHc / 2, 0);
  { const st = cut(10), op = Wi(10, 3) - st, sec = Wi(10, 8) - st;
    add({ id: 'S11', at: st, note: 'glass cone splits, flattens into a sector, stands to face us', draw(lt, d, t, blit) {
      xReset(); const open = eio(seg(lt, op - 0.1, Math.max(op + 0.9, sec))), stand = eio(seg(lt, op + 0.3, Math.max(op + 1.2, sec + 0.2)));
      poseCone(open, stand); orbit(CONE, lerp(4.6, 6.0, open), lerp(0.6, 0.0, eio(lt / d)), lerp(0.42, 0.05, stand)); xRender(CONE); blit();
      if (lt > sec) { const [x, y] = screen(V3(0, XE + CHc - cSide.userData.l * 0.6, 0), cam); label('SECTOR', 790, 560, x, y, eob(seg(lt, sec, sec + 0.25))); }
    } });
    cue(st, 'whoosh'); cue(st + op, 'zip', { gain: 0.6 }); cue(st + op + 0.1, 'slide', { dur: 1.0, gain: 0.5 }); cue(st + sec, 'pop'); }

  // ── 12 · its area is πrl (l = slant height) ───────────────────────────────────────────────
  { const st = cut(11), pi = Wi(11, 3) - st, sl = Wi(11, 8) - st;
    add({ id: 'S12', at: st, note: 'sector: πrl on "पाई", slant edge bracket l on "स्लांट"', draw(lt, d, t, blit) {
      xReset(); poseCone(1, 1); orbit(CONE, lerp(6.0, 5.5, eio(lt / d)), lerp(0.1, -0.08, eio(lt / d)), 0.05); xRender(CONE); blit();
      const l = cSide.userData.l, half = cSide.userData.phi / 2, apex = V3(0, XE + CHc, 0), end = V3(-Math.sin(half) * l, XE + CHc - Math.cos(half) * l, 0);
      bracket(apex, end, lt > sl ? 'l' : null, eo(seg(lt, sl - 0.2, sl + 0.25)), cam, 1);
      F('πrl', 360, eob(seg(lt, pi, pi + 0.25)), YEL, 120);
    } });
    cue(st, 'whoosh'); cue(st + pi, 'pop'); cue(st + sl, 'slide', { dur: 0.4, gain: 0.45 }); }

  // ── 13 · volume: the can is a stack of coins ──────────────────────────────────────────────
  { const st = cut(12), drop0 = Wi(12, 4) - st - 0.1;
    const coinState = (lt, d) => { const span = Math.max(0.8, d - drop0 - 0.25); return coins.map((c, i) => { const a = drop0 + i * span / NC, p = seg(lt, a, a + 0.22); return p; }); };
    const placeCoins = (ps) => coins.forEach((c, i) => { const p = ps[i], y = Y0 + CT * (i + 0.5); c.visible = p > 0; c.position.set(coinX, y + 0.35 * (1 - eo(p)), coinZ); c.rotation.set(0.4 * (1 - p), 0, 0.3 * (1 - p)); });
    const D13 = shotEnd(12) - st;
    add({ id: 'S13', at: st, note: 'back in the kitchen, coins drop and stack beside the can', draw(lt, d, t, blit) {
      kitchenReset(t); sheet.visible = false; placeCoins(coinState(lt, d));
      orbit(V3(CX + 0.2, Y0 + 0.17, -1.82), lerp(2.75, 2.45, eio(lt / d)), lerp(0.3, 0.15, eio(lt / d)), 0.22); kRender(V3(CX + 0.2, Y0 + 0.15, -1.8)); blit();
      if (lt < drop0 + 0.4) pill('VOLUME ?', 540, 380, eob(seg(lt, 0.05, 0.3)), '#FFFFFF', 'rgba(12,14,20,0.82)', 70);
    } });
    cue(st, 'whoosh'); for (let i = 0; i < NC; i += 3) { const span = Math.max(0.8, D13 - drop0 - 0.25); cue(st + drop0 + i * span / NC + 0.2, 'tock', { gain: 0.5 }); }

    // ── 14 · each coin πr², h high → πr²h ───────────────────────────────────────────────────
    const st2 = cut(13), c1 = Wi(13, 2) - st2, hh = Wi(13, 5) - st2, tot = Wi(13, 9) - st2;
    add({ id: 'S14', at: st2, note: 'top coin πr², bracket h, πr²h', draw(lt, d, t, blit) {
      kitchenReset(t); sheet.visible = false; placeCoins(coins.map(() => 1));
      orbit(V3(CX + 0.3, Y0 + 0.17, -1.82), lerp(2.85, 2.65, eio(lt / d)), lerp(0.1, -0.06, eio(lt / d)), 0.26); kRender(V3(coinX, Y0 + 0.15, coinZ)); blit();
      if (lt > c1) { const [x, y] = screen(V3(coinX, Y0 + CH, coinZ), cam); label('πr²', x - 150, y - 200, x, y, eob(seg(lt, c1, c1 + 0.25))); }
      bracket(V3(coinX + R + 0.04, Y0, coinZ), V3(coinX + R + 0.04, Y0 + CH, coinZ), lt > hh + 0.3 ? 'h' : null, eo(seg(lt, hh - 0.1, hh + 0.3)), cam, -1);
      if (lt > tot) F('πr²h', 330, eob(seg(lt, tot, tot + 0.25)), YEL, 120);
    } });
    cue(st2, 'whoosh'); cue(st2 + c1, 'pop'); cue(st2 + hh, 'slide', { dur: 0.35, gain: 0.4 }); cue(st2 + tot, 'sparkle', { dur: 0.8, gain: 0.6 }); }

  // ── 15 · three cones of water fill one cylinder ───────────────────────────────────────────
  const POUR = V3(-0.08, 0.6, 0), PLOOK = { bloom: 0.35, bloomThreshold: 0.55 };
  { const st = cut(14), p0 = 0.15, p1 = Math.max(2.4, shotEnd(14) - st - 0.15);
    add({ id: 'S15', at: st, note: 'glass cone pours into glass cylinder 3 times: 1, 2, 3', draw(lt, d, t, blit) {
      xReset(); const { n } = posePour(p0, p1, lt);
      orbit(POUR, lerp(6.4, 5.8, eio(lt / d)), lerp(0.3, 0.12, eio(lt / d)), 0.16); xRender(POUR, PLOOK); blit();
      if (n > 0) pill(`${n} / 3`, 540, 380, 1, CYAN, 'rgba(8,16,28,0.85)', 80);
    } });
    cue(st, 'whoosh'); const per = (p1 - p0) / 3; for (let i = 0; i < 3; i++) { cue(st + p0 + i * per + per * 0.4, 'bubbles', { dur: per * 0.4, gain: 0.5 }); cue(st + p0 + i * per + per * 0.8, 'pop', { gain: 0.4 }); } }

  // ── 16 · so the cone is ⅓ πr²h, then the camera finds the can again (loop) ────────────────
  { const st = cut(15), th = Wi(15, 4) - st, D = T.dur - st, back = Math.max(th + 1.0, D - 0.9);
    add({ id: 'S16', at: st, note: 'full cylinder + empty cone, ⅓ πr²h stamp; last 0.9 s: the can again (loops to frame 0)', draw(lt, d, t, blit) {
      if (lt < back) {
        xReset(); posePour(-3, -0.01, 0); orbit(POUR, lerp(5.8, 5.3, eio(lt / back)), lerp(0.12, -0.1, eio(lt / back)), 0.16); xRender(POUR, PLOOK); blit();
        F('Cone = ⅓ πr²h', 380, eob(seg(lt, th, th + 0.25)), YEL, 96);
      } else { const k = eio(seg(lt, back, D)); kitchenReset(0); orbit(HOOK0.tgt, lerp(HOOK0.d0 + 0.35, HOOK0.d0, k), lerp(HOOK0.yaw0 + 0.25, HOOK0.yaw0, k), HOOK0.pitch); kRender(HOOK0.tgt); blit(); }
    } });
    cue(st, 'whoosh'); cue(st + th, 'stamp'); cue(st + th + 0.05, 'thud', { gain: 0.5 }); cue(st + back, 'whoosh', { gain: 0.7 }); }

  return { shots: S, cues: CUES };
}
