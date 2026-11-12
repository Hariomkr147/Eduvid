// Frame-exact capture through headless Chrome. No npm packages (Node 22+). Run from the project folder.
//   node tools/capture.mjs check                         boot, list shots + captions, report errors
//   node tools/capture.mjs cues                          write data/cues.json (the sound cues, for tools/mix.py)
//   node tools/capture.mjs sheet review/all.jpg [step=0.5] [cols=9]   contact sheet, a frame every `step` s, time-stamped
//   node tools/capture.mjs frames review/full "1.2,8.4"  full-size JPEGs of those times
//   node tools/capture.mjs video renders/out.mp4 [start end] [--draft|--best]   the film (FPS env, default 30) + data/mix.wav
//        --best = archive quality for upload: x264 preset slow, CRF 14, high profile (use with FPS=60 for the smoothest motion)
//   node tools/capture.mjs preview                       serve the project and print a URL to watch it in a browser
// CHROME=/path/to/chrome overrides the browser (Chrome, Chromium or Edge). JOBS=n sets how many browsers render frames in
// parallel (default: about half the CPU cores, max 6; 3D styles in SOFTWARE_GL default to fewer). Final renders send
// lossless PNG frames to x264; --draft uses JPEG. (Shared file: edit shared/tools/capture.mjs, run scripts/sync_shared.sh.)
import { spawn, spawnSync } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const FPS = +(process.env.FPS || 30);
const LAD = process.env.LOCALAPPDATA;
const CHROME = [process.env.CHROME, '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge', '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium',
  '/usr/bin/chromium-browser', '/snap/bin/chromium', '/usr/bin/microsoft-edge', 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe', LAD && path.join(LAD, 'Google/Chrome/Application/chrome.exe'),
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', 'C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find((p) => p && fs.existsSync(p));
const JOBS = Math.max(1, +(process.env.JOBS || Math.min(6, Math.floor(os.cpus().length / 2) || 1, process.env.SOFTWARE_GL ? 2 : 6)));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const args = process.argv.slice(2), flags = new Set(args.filter((a) => a.startsWith('--')));
const [mode, ...rest] = args.filter((a) => !a.startsWith('--'));

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.otf': 'font/otf',
  '.ttf': 'font/ttf', '.woff2': 'font/woff2', '.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.png': 'image/png', '.jpg': 'image/jpeg' };
function serve(port = 0) {
  return new Promise((res) => {
    const srv = http.createServer((req, r) => {
      const u = decodeURIComponent(req.url.split('?')[0]), f = path.join(ROOT, u === '/' ? 'index.html' : u);
      if (!f.startsWith(ROOT) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { r.writeHead(404); r.end(); return; }
      r.writeHead(200, { 'Content-Type': MIME[path.extname(f)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
      fs.createReadStream(f).pipe(r);
    });
    srv.listen(port, '127.0.0.1', () => res(srv));
  });
}

async function openPage(port) {
  if (!CHROME) throw new Error('Chrome not found: install Google Chrome or set CHROME=/path/to/chrome');
  const prof = fs.mkdtempSync(path.join(os.tmpdir(), 'fs-chrome-'));
  const chrome = spawn(CHROME, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${prof}`, '--no-first-run', '--no-default-browser-check',
    '--hide-scrollbars', '--window-size=1080,1920', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader', ...(process.env.SOFTWARE_GL ? ['--use-angle=swiftshader'] : []), ...(process.getuid?.() === 0 ? ['--no-sandbox'] : []), '--disable-background-timer-throttling', '--disable-renderer-backgrounding', 'about:blank'], { stdio: 'ignore' });
  let dbg;
  for (let i = 0; i < 200 && !dbg; i++) { try { dbg = fs.readFileSync(path.join(prof, 'DevToolsActivePort'), 'utf8').split('\n')[0].trim(); } catch { await sleep(100); } }
  if (!dbg) throw new Error('Chrome did not start');
  const r = await fetch(`http://127.0.0.1:${dbg}/json/new?${encodeURIComponent(`http://127.0.0.1:${port}/index.html?capture=1${process.env.QS || ''}`)}`, { method: 'PUT' });
  const target = await r.json();
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0; const pend = new Map(), logs = [];
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pend.has(m.id)) { const p = pend.get(m.id); pend.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); }
    else if (m.method === 'Runtime.exceptionThrown') logs.push('EXCEPTION ' + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
    else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') logs.push('ERROR ' + m.params.args.map((a) => a.value ?? a.description).join(' '));
  };
  const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; pend.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); });
  const ev = async (expr) => { const x = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true }); if (x.exceptionDetails) throw new Error(x.exceptionDetails.exception?.description || x.exceptionDetails.text); return x.result.value; };
  await send('Runtime.enable');
  for (let i = 0; ; i++) {
    const st = await ev('window.OP ? (OP.bootError ? "ERR:" + OP.bootError : OP.ready) : false').catch(() => false);
    if (st === true) break;
    if (typeof st === 'string') throw new Error('boot failed: ' + st + '\n' + logs.join('\n'));
    if (i > 1200) throw new Error('boot timeout\n' + logs.join('\n'));
    await sleep(100);
  }
  const close = () => { try { ws.close(); } catch {} chrome.kill('SIGKILL'); setTimeout(() => { try { fs.rmSync(prof, { recursive: true, force: true }); } catch {} }, 300); };
  return { ev, logs, close };
}
const jpg = (d) => Buffer.from(d.slice(d.indexOf(',') + 1), 'base64');
const FRAME = (t, q, label, fmt = 'image/jpeg') => `(() => { const d = OP.frame(${t}, ${q}, '${fmt}'); ${label ? `const cv = document.getElementById('cv'), c = cv.getContext('2d'); c.setTransform(1,0,0,1,0,0); c.fillStyle = '#000'; c.fillRect(0, 0, 250, 86); c.fillStyle = '#fff'; c.font = '700 60px sans-serif'; c.textAlign = 'left'; c.textBaseline = 'alphabetic'; c.fillText('${(+t).toFixed(2)}', 14, 64); return cv.toDataURL('image/jpeg', ${q});` : 'return d;'} })()`;

const srv = await serve(mode === 'preview' ? 8765 : 0), port = srv.address().port;
if (mode === 'preview') { console.log(`open http://127.0.0.1:${port}/  (Ctrl+C to stop)`); }
else {
  const P = await openPage(port), extra = [];
  try {
    const dur = await P.ev('OP.duration()');
    if (mode === 'check') {
      console.log(`duration ${dur.toFixed(2)} s`);
      for (const s of await P.ev('OP.shots()')) console.log(`${s.id.padEnd(5)} ${s.at.toFixed(2).padStart(6)} → ${s.end.toFixed(2).padStart(6)}  (${(s.end - s.at).toFixed(2)} s)  ${s.note}`);
      console.log('captions:'); for (const c of await P.ev('OP.captions()')) console.log(`  ${c.s.toFixed(2).padStart(6)}–${c.e.toFixed(2).padEnd(6)} ${c.text}`);
      let bad = 0; for (let t = 0; t < dur; t += 0.25) { try { await P.ev(`OP.draw(${t})`); } catch (e) { bad++; console.log(`ERROR at ${t.toFixed(2)}: ${e.message.split('\n')[0]}`); } }
      if (P.logs.length) console.log(P.logs.join('\n'));
      // automatic QA: things that are legal but usually wrong (warnings, the check still passes)
      const warn = [], shots = await P.ev('OP.shots()'), caps = await P.ev('OP.captions()');
      for (const s of shots) { const len = s.end - s.at; if (len < 1.0 || len > 4.0) warn.push(`shot ${s.id} is ${len.toFixed(2)} s (aim for 1.5-3.5 s: ${len < 1 ? 'merge it' : 'split it'})`); }
      for (const c of caps) { if (c.e - c.s < 0.3) warn.push(`caption "${c.text}" is on screen only ${(c.e - c.s).toFixed(2)} s`); if (c.miss) warn.push(`caption "${c.text}" did not match a spoken word, placed by word count: start it with the word that is said`); }
      try {
        const words = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/words.json'), 'utf8')), lost = words.filter((w) => w.matched === false);
        if (lost.length) warn.push(`${lost.length} word(s) were not heard by Whisper and are timed by estimate: ${lost.slice(0, 8).map((w) => `"${w.w}" (line ${w.line})`).join(', ')}${lost.length > 8 ? ' …' : ''}`);
        if (JSON.parse(fs.readFileSync(path.join(ROOT, 'data/lines.json'), 'utf8')).estimated) warn.push('timing is ESTIMATED (estimate.py): run voice.py + words.py before the final render');
      } catch {}
      if (shots.length && shots[0].at > 0.05) warn.push(`the first shot starts at ${shots[0].at.toFixed(2)} s: frame 0 should already be the hook`);
      for (const w of warn) console.log('WARN ' + w);
      console.log(bad || P.logs.length ? 'CHECK FAILED' : `CHECK OK${warn.length ? ` (${warn.length} warning${warn.length > 1 ? 's' : ''})` : ''}`);
    } else if (mode === 'cues') {
      const cues = await P.ev('OP.cues()');
      fs.mkdirSync(path.join(ROOT, 'data'), { recursive: true });
      fs.writeFileSync(path.join(ROOT, 'data/cues.json'), JSON.stringify({ duration: dur, cues }, null, 1));
      console.log(`data/cues.json: ${cues.length} cues, ${dur.toFixed(2)} s`);
    } else if (mode === 'frames') {
      const dir = path.resolve(ROOT, rest[0] || 'review/frames'); fs.mkdirSync(dir, { recursive: true });
      for (const t of (rest[1] || '0').split(',').map(Number)) { fs.writeFileSync(path.join(dir, `t${t.toFixed(2)}.jpg`), jpg(await P.ev(FRAME(t, 0.92)))); }
      console.log(dir);
    } else if (mode === 'sheet') {
      const out = path.resolve(ROOT, rest[0] || 'review/all.jpg'), step = +(rest[1] || 0.5), cols = +(rest[2] || 9);
      const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'fs-sheet-')); let n = 0;
      for (let t = step / 2; t < dur; t += step) fs.writeFileSync(path.join(tmp, `f${String(n++).padStart(4, '0')}.jpg`), jpg(await P.ev(FRAME(t, 0.8, true))));
      const rows = Math.ceil(n / cols); fs.mkdirSync(path.dirname(out), { recursive: true });
      const r = spawnSync('ffmpeg', ['-v', 'error', '-y', '-framerate', '1', '-i', path.join(tmp, 'f%04d.jpg'), '-vf', `scale=216:384,tile=${cols}x${rows}:padding=4:color=black`, '-frames:v', '1', '-q:v', '3', out]);
      fs.rmSync(tmp, { recursive: true, force: true });
      if (r.status) throw new Error('ffmpeg: ' + r.stderr); console.log(`${out} (${n} frames, every ${step} s)`);
    } else if (mode === 'video') {
      const out = path.resolve(ROOT, rest[0] || 'renders/video.mp4'); fs.mkdirSync(path.dirname(out), { recursive: true });
      const draft = flags.has('--draft'), best = flags.has('--best'), fmt = draft ? 'image/jpeg' : 'image/png';
      const mix = path.join(ROOT, 'data/mix.wav'), hasMix = fs.existsSync(mix), a0 = rest[1] ? +rest[1] : 0, a1 = rest[2] ? Math.min(+rest[2], dur) : dur, n = Math.round((a1 - a0) * FPS);
      const ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-c:v', draft ? 'mjpeg' : 'png', '-framerate', String(FPS), '-i', '-',
        ...(hasMix ? ['-ss', String(a0), '-t', String(a1 - a0), '-i', mix] : ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']), '-map', '0:v', '-map', '1:a',
        '-c:v', 'libx264', '-preset', draft ? 'ultrafast' : best ? 'slow' : 'medium', '-crf', draft ? '28' : best ? '14' : '17', ...(best ? ['-tune', 'animation', '-x264-params', 'aq-mode=3'] : []), '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-r', String(FPS),
        '-c:a', 'aac', '-b:a', best ? '320k' : '192k', '-ar', '48000', '-shortest', '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });
      const t0 = Date.now(), jobs = Math.min(JOBS, Math.max(1, n));
      // extra browsers render frames in parallel (every frame is a pure function of time); frames are written in order
      const pages = [P, ...(await Promise.all(Array.from({ length: jobs - 1 }, () => openPage(port).catch(() => null)))).filter(Boolean)];
      extra.push(...pages.slice(1));
      const grab = (pg, i) => pg.ev(FRAME(a0 + i / FPS, draft ? 0.8 : 1, false, fmt));
      for (let i = 0; i < n; i += pages.length) {
        const batch = await Promise.all(pages.map((pg, k) => (i + k < n ? grab(pg, i + k) : null)));
        for (const d of batch) { if (!d) continue; if (!ff.stdin.write(jpg(d))) await new Promise((r) => ff.stdin.once('drain', r)); }
        if (i % 60 < pages.length) { const el = (Date.now() - t0) / 1000, done = Math.min(n, i + pages.length); process.stdout.write(`\r${done}/${n} frames · ${pages.length} browser${pages.length > 1 ? 's' : ''} · ~${Math.round(el / done * (n - done))} s left   `); }
      }
      ff.stdin.end(); const code = await new Promise((r) => ff.on('close', r));
      if (code) throw new Error('ffmpeg failed while encoding the video');
      console.log(`\r${out} (${n} frames, ${pages.length} browser${pages.length > 1 ? 's' : ''}, ${draft ? 'draft' : 'PNG frames'}, ${hasMix ? 'with data/mix.wav' : 'SILENT: no data/mix.wav'}, ${((Date.now() - t0) / 1000).toFixed(0)} s)          `);
    } else console.log('modes: check · cues · sheet · frames · video · preview');
  } finally { P.close(); extra.forEach((x) => x.close()); srv.close(); }
}
