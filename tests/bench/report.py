"""Build a self-contained HTML listening report from a tts_bench run (seed-1 clips embedded as MP3).

Run: docker compose run --rm tools python tests/bench/report.py [--bench /data/scratch/tts-bench] [--out FILE]
"""
import argparse
import base64
import html
import json
import statistics
import subprocess
from pathlib import Path

from tts_bench import SENTENCES  # same folder

ENGINE_NOTES = {
    "omnivoice": ("OmniVoice", "k2-fsa · 0.6B", "Weights CC-BY-NC: internal use only", "bad"),
    "kokoro": ("Kokoro-82M", "kokoro-onnx · 82M", "Apache-2.0", "good"),
    "chatterbox": ("Chatterbox v3", "Resemble AI · 0.5B", "MIT · retired upstream · watermarked", "warn"),
    "veena": ("Veena", "Maya Research · 3B", "Licence unclear (apache-2.0 vs proprietary tag)", "warn"),
    "parler": ("Indic Parler-TTS", "AI4Bharat · 0.9B", "Apache-2.0 · gated (accept terms)", "good"),
    "indicf5": ("IndicF5", "AI4Bharat · 0.4B", "MIT · gated · clone only consented voices", "good"),
}


def mp3_b64(wav: Path) -> str:
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(wav), "-ac", "1", "-b:a", "40k", "-f", "mp3", "pipe:1"],
                       capture_output=True, check=True)
    return base64.b64encode(p.stdout).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", default="/data/scratch/tts-bench")
    ap.add_argument("--out", default="/data/scratch/tts-bench/report.html")
    a = ap.parse_args()
    bench = Path(a.bench)
    data = json.loads((bench / "results.json").read_text())
    rows = [r for r in data["rows"] if r.get("status") == 200]
    voices = []  # (engine, voice) in first-seen order
    for r in rows:
        if (r["engine"], r["voice"]) not in voices:
            voices.append((r["engine"], r["voice"]))

    # ---- summary per engine/voice (Hindi + Hinglish only) ----
    summ = []
    for eng, voice in voices:
        rs = [r for r in rows if r["engine"] == eng and r["voice"] == voice and r["language"] != "english"]
        if not rs:
            continue
        summ.append({
            "eng": eng, "voice": voice, "n": len(rs),
            "cer": statistics.mean(r["cer_spoken"] for r in rs),
            "fail": sum(r["cer_spoken"] > 0.12 for r in rs),
            "lat": statistics.median(r["wall_s"] for r in rs),
            "rtf": statistics.median(r["rtf"] for r in rs),
            "cps": statistics.median(r["chars_per_s"] for r in rs),
        })
    info = data["engines"]

    # ---- clips (seed 1) ----
    clips = {}
    for r in rows:
        if r["seed"] != 1:
            continue
        wav = bench / "wav" / f"{r['engine']}__{r['voice']}__{r['sentence']}__s1.wav"
        if wav.exists():
            clips[f"{r['engine']}|{r['voice']}|{r['sentence']}"] = {
                "b64": mp3_b64(wav), "cer": r["cer_spoken"], "dur": r["audio_s"], "t": r["transcript"]}

    e = html.escape
    lang_label = {"hinglish": "Hinglish", "hindi": "Hindi", "english": "English"}

    def sev(c):
        return "good" if c <= 0.05 else "warn" if c <= 0.12 else "bad"

    summary_rows = []
    for s in summ:
        name, model, lic, tone = ENGINE_NOTES[s["eng"]]
        mem = info.get(s["eng"], {}).get("peak_gpu_mem_mb")
        summary_rows.append(
            f"<tr><td><b>{e(name)}</b><span class=sub>{e(s['voice'])}</span></td>"
            f"<td class=num><span class='pill {sev(s['cer'])}'>{s['cer']:.3f}</span></td>"
            f"<td class=num>{s['fail']}/{s['n']}</td>"
            f"<td class=num>{s['lat']:.2f} s</td><td class=num>{s['rtf']:.2f}</td>"
            f"<td class=num>{s['cps']:.1f}</td>"
            f"<td class=num>{(str(mem) + ' MB') if mem else 'CPU/ORT'}</td>"
            f"<td><span class='lic {tone}'>{e(lic)}</span></td></tr>")

    sent_blocks = []
    for sid, lang, text in SENTENCES:
        cells = []
        for eng, voice in voices:
            c = clips.get(f"{eng}|{voice}|{sid}")
            if not c:
                continue
            cells.append(
                f"<button class=clip type=button data-k='{e(eng)}|{e(voice)}|{sid}' aria-label='Play {e(voice)}'>"
                f"<span class=play aria-hidden=true></span>"
                f"<span class=who><b>{e(ENGINE_NOTES[eng][0])}</b> {e(voice)}</span>"
                f"<span class='cer {sev(c['cer'])}'>CER {c['cer']:.2f} · {c['dur']:.1f}s</span>"
                f"<span class=heard lang={'en' if lang == 'english' else 'hi'}>{e(c['t'])}</span></button>")
        sent_blocks.append(
            f"<section class=sent id='s-{sid}'><header><span class=tag>{lang_label[lang]}</span>"
            f"<p class=text lang={'en' if lang == 'english' else 'hi'}>{e(text)}</p></header>"
            f"<div class=grid>{''.join(cells)}</div></section>")

    audio_map = json.dumps({k: v["b64"] for k, v in clips.items()})
    page = TEMPLATE.replace("%%SUMMARY%%", "".join(summary_rows)).replace("%%SENTENCES%%", "".join(sent_blocks))
    page = page.replace("%%AUDIO%%", audio_map).replace("%%NCLIPS%%", str(len(clips)))
    page = page.replace("%%NROWS%%", str(len(rows)))
    Path(a.out).write_text(page)
    print(f"wrote {a.out} ({len(page) / 1e6:.1f} MB, {len(clips)} clips)")


TEMPLATE = r"""<title>Hindi TTS Bake-off</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&family=Noto+Sans+Devanagari:wght@400;500;600&display=swap">
<style>
/* Layout: one reading column — verdict table first, then one listening card per test sentence. */
:root{
  --bg:#f6f7f9; --surface:#ffffff; --ink:#18212b; --muted:#5b6672; --line:#dde2e8; --accent:#2a5bd7;
  --good:#1f7a4d; --good-bg:#e3f4ea; --warn:#8a5a00; --warn-bg:#fbefd5; --bad:#b3261e; --bad-bg:#fbe4e2;
  --mutedpill:#eef1f4;
  --sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --deva:"Noto Sans Devanagari","Nirmala UI","Mangal",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#11161c; --surface:#19212a; --ink:#e6ebf0; --muted:#97a3af; --line:#2a3542; --accent:#7ea2ff;
  --good:#6fd39e; --good-bg:#16352a; --warn:#f0c46a; --warn-bg:#3a2f15; --bad:#ff8a80; --bad-bg:#3d1d1b;
  --mutedpill:#222c37; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#11161c; --surface:#19212a; --ink:#e6ebf0; --muted:#97a3af; --line:#2a3542; --accent:#7ea2ff;
  --good:#6fd39e; --good-bg:#16352a; --warn:#f0c46a; --warn-bg:#3a2f15; --bad:#ff8a80; --bad-bg:#3d1d1b;
  --mutedpill:#222c37; color-scheme:dark}
body{background:var(--bg);color:var(--ink);font:15px/1.55 var(--sans)}
.wrap{max-width:1080px;margin:0 auto;padding-block:32px 64px;padding-left:max(16px,env(safe-area-inset-left,0px));
  padding-right:max(16px,env(safe-area-inset-right,0px));display:grid;gap:28px}
h1{font-size:28px;line-height:1.2;margin:0;font-weight:600;text-wrap:balance}
h2{font-size:18px;margin:0;font-weight:600}
.lede{color:var(--muted);max-width:68ch;margin:6px 0 0}
.lede b{color:var(--ink);font-weight:500}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:18px 18px 8px;display:grid;gap:12px}
.tablewrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;min-width:760px;font-size:14px}
th{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:500;text-align:left;
  padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:10px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}
td.num,th.num{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.sub{display:block;color:var(--muted);font-family:var(--mono);font-size:12px}
.pill{display:inline-block;padding:1px 8px;border-radius:99px;font-weight:500}
.good{color:var(--good);background:var(--good-bg)} .warn{color:var(--warn);background:var(--warn-bg)}
.bad{color:var(--bad);background:var(--bad-bg)} .muted{color:var(--muted);background:var(--mutedpill)}
.lic{display:inline-block;padding:2px 8px;border-radius:6px;font-size:12.5px}
.notes{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.note{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px;min-width:0}
.note h3{margin:0 0 4px;font-size:14px}
.note p{margin:0;color:var(--muted);font-size:14px}
.sent{display:grid;gap:12px;padding-top:6px;border-top:1px solid var(--line)}
.sent header{display:grid;gap:4px}
.tag{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);font-weight:600}
.text{margin:0;font-size:19px;line-height:1.6}
[lang=hi]{font-family:var(--deva)}
.grid{display:grid;gap:8px;grid-template-columns:repeat(auto-fill,minmax(232px,1fr))}
.clip{all:unset;box-sizing:border-box;cursor:pointer;display:grid;grid-template-columns:28px 1fr;column-gap:10px;row-gap:2px;
  align-items:start;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 12px;min-width:0}
.clip:hover{border-color:var(--accent)}
.clip:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.clip.on{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent)}
.play{grid-row:span 3;width:28px;height:28px;border-radius:50%;background:var(--accent);position:relative}
.play::after{content:"";position:absolute;left:11px;top:8px;border-left:9px solid var(--surface);border-top:6px solid transparent;border-bottom:6px solid transparent}
.clip.on .play::after{left:9px;top:9px;border:0;width:10px;height:10px;background:var(--surface)}
.who{font-size:13px;color:var(--muted);overflow-wrap:anywhere} .who b{color:var(--ink);font-weight:500}
.cer{font-family:var(--mono);font-size:11.5px;justify-self:start;padding:0 6px;border-radius:5px}
.heard{font-size:13px;color:var(--muted);overflow-wrap:anywhere}
.heard::before{content:"heard: ";font-family:var(--sans);font-size:11px;text-transform:uppercase;letter-spacing:.05em}
.foot{color:var(--muted);font-size:13px}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
<div class=wrap>
  <header>
    <h1>Hindi TTS Bake-off</h1>
    <p class=lede>Every candidate voice read the same 11 Hindi/Hinglish lines and 2 English lines, 3 seeds each
      (%%NROWS%% clips). Whisper large-v3 transcribed each clip back, and <b>spoken CER</b> compares that transcript
      with the script, reading digits as words (so “2” matches टू or दो). Lower is better; above 0.12 triggers a
      retake in the pipeline. Tap any card to listen to its seed-1 take.</p>
  </header>

  <section class=panel aria-labelledby=t-sum>
    <h2 id=t-sum>Results, Hindi + Hinglish lines</h2>
    <div class=tablewrap><table>
      <thead><tr><th>Voice</th><th class=num>Spoken CER</th><th class=num>Over 0.12</th><th class=num>Latency</th>
        <th class=num>RTF</th><th class=num>Chars/s</th><th class=num>GPU</th><th>Licence</th></tr></thead>
      <tbody>%%SUMMARY%%</tbody></table></div>
  </section>

  <div class=notes>
    <div class=note><h3>IndicF5 is clearest; the rest are close</h3><p>IndicF5 leads at 0.05 spoken CER; everything else lands
      between 0.07 and 0.11. Most remaining errors are Whisper's spelling (आरेच for आर एच, प्रिष्ठिय for पृष्ठीय),
      so listen before choosing.</p></div>
    <div class=note><h3>Speed is not</h3><p>Median time per line: Kokoro 0.2 s, OmniVoice 1.4 s, Chatterbox 3.4 s,
      IndicF5 6 s, Parler 8 s, Veena 10 s on one L4. IndicF5, Parler and Veena run slower than real time.</p></div>
    <div class=note><h3>Licences decide a lot</h3><p>OmniVoice weights are non-commercial. Veena's licence is
      contradictory. Chatterbox is MIT but retired upstream and watermarks its output. Kokoro and Indic Parler-TTS are Apache-2.0; IndicF5 is MIT.</p></div>
    <div class=note><h3>IndicF5 voices are borrowed</h3><p>IndicF5 copies the voice of a short reference clip. Ours are
      synthetic clips from Kokoro's Hindi voices, so IndicF5 sounds like Kokoro, read more clearly. A licensed
      voice-artist clip would give it any voice we have consent for.</p></div>
  </div>

  %%SENTENCES%%

  <p class=foot>%%NCLIPS%% clips embedded as 40 kbps MP3. Run on 2026-11-11, GPU 0 and GPU 3 (NVIDIA L4).
    Sentences are our own text about the pilot topics.</p>
</div>
<script>
const AUDIO = %%AUDIO%%;
const player = new Audio();
let current = null;
function stop(){ if(current){ current.classList.remove('on'); current = null; } player.pause(); }
player.addEventListener('ended', stop);
document.addEventListener('click', ev => {
  const b = ev.target.closest('.clip'); if(!b) return;
  if (current === b) { stop(); return; }
  stop();
  player.src = 'data:audio/mpeg;base64,' + AUDIO[b.dataset.k];
  player.play().then(() => { current = b; b.classList.add('on'); }).catch(() => {});
});
</script>
"""

if __name__ == "__main__":
    main()
