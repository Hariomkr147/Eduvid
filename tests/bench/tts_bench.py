"""TTS benchmark: every candidate engine × voice × sentence × seed.

Measures synthesis latency, real-time factor, audio length, loudness, and intelligibility
(CER of the WhisperX large-v3 transcript against the input), plus the engine's GPU memory.
Writes results.json, results.csv, summary.md and per-clip WAVs to OUT (default data/scratch/tts-bench).

Run:  docker compose run --rm tools python tests/bench/tts_bench.py [--engines a,b] [--seeds 1,2,3]
"""
import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

from eduvid_common.audio import duration_s, rms_dbfs
from eduvid_common.textmetrics import cer, cer_spoken

# Our own sentences (facts from the pilot topics, written for speech). Not textbook text.
SENTENCES = [
    ("h1", "hinglish", "सिलेंडर का कर्व्ड सरफेस एरिया टू पाई आर एच होता है।"),
    ("h2", "hinglish", "अब इस कोन की स्लांट हाइट निकालते हैं, जो यहाँ पाँच सेंटीमीटर है।"),
    ("h3", "hinglish", "अगर रेडियस डबल कर दें, तो वॉल्यूम आठ गुना हो जाता है।"),
    ("h4", "hinglish", "वेलोसिटी में डायरेक्शन भी होती है, स्पीड में सिर्फ़ मैग्निट्यूड।"),
    ("h5", "hinglish", "हर सेल के अंदर एक न्यूक्लियस होता है, जो पूरी सेल को कंट्रोल करता है।"),
    ("h6", "hinglish", "एक मोल में छह पॉइंट शून्य दो गुणा दस की पावर तेईस पार्टिकल्स होते हैं।"),
    ("d1", "hindi", "बेलन का वक्र पृष्ठीय क्षेत्रफल दो पाई आर एच के बराबर होता है।"),
    ("d2", "hindi", "परमाणु बहुत छोटे होते हैं, इन्हें हम आँखों से नहीं देख सकते।"),
    ("d3", "hindi", "त्वरण का अर्थ है समय के साथ वेग में होने वाला परिवर्तन।"),
    ("d4", "hindi", "कोशिका जीवन की सबसे छोटी इकाई है।"),
    ("l1", "hinglish", "चलो एक छोटा सा एक्सपेरिमेंट करते हैं। एक पेपर शीट लो और उसे रोल करके एक सिलेंडर बनाओ। "
                       "अब ध्यान से देखो, जब हम इसे खोलते हैं तो यह एक रेक्टैंगल बन जाता है, "
                       "जिसकी लंबाई सर्कल की सरकमफ़रेंस के बराबर है।"),
    ("e1", "english", "The curved surface area of a cylinder is two pi r h."),
    ("e2", "english", "Velocity tells us both how fast something moves and in which direction."),
]

# engine -> (base url, {voice: languages it is benchmarked on})
HI = {"hinglish", "hindi"}
ALL = {"hinglish", "hindi", "english"}
ENGINES = {
    "omnivoice": ("http://tts-omnivoice:8000", {"hinglish-female": HI, "hinglish-male": HI}),
    "kokoro": ("http://tts-kokoro:8000", {"hf_alpha": HI, "hm_omega": HI, "am_michael": {"english"}}),
    "chatterbox": ("http://tts-chatterbox:8000", {"hindi-default": HI, "english-default": {"english"}}),
    "parler": ("http://tts-parler:8000", {"divya": ALL, "rohit": ALL}),
    "indicf5": ("http://tts-indicf5:8000", {"ref-female": HI, "ref-male": HI}),
    "veena": ("http://tts-veena:8000", {"kavya": HI, "agastya": {"english"}, "maitri": HI}),
}
ASR_URL = "http://asr-whisperx:8000"
# Without these prompts Whisper writes Hinglish loanwords in Latin script and numbers as digits.
ASR_PROMPT = {"hi": "यह हिंदी है। सारे शब्द देवनागरी में लिखे हैं, जैसे सिलेंडर, एरिया, वेलोसिटी, टू, थ्री, पाई।",
              "en": "Numbers and symbols are spoken as words: two pi r h, nine point eight metres per second squared."}
CER_OK = 0.12


def transcribe(client: httpx.Client, wav: bytes, lang: str) -> str:
    r = client.post(f"{ASR_URL}/transcribe", files={"file": ("a.wav", wav, "audio/wav")},
                    data={"language": (lg := "en" if lang == "english" else "hi"), "prompt": ASR_PROMPT[lg]}, timeout=300)
    r.raise_for_status()
    return r.json()["text"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", default=",".join(ENGINES))
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--out", default="/data/scratch/tts-bench")
    ap.add_argument("--rescore", action="store_true", help="recompute metrics/summary from results.json only")
    ap.add_argument("--merge", action="store_true", help="keep rows of engines not in --engines from results.json")
    a = ap.parse_args()
    out = Path(a.out)
    (out / "wav").mkdir(parents=True, exist_ok=True)
    seeds = [int(s) for s in a.seeds.split(",")]
    rows, engine_info = [], {}
    run_engines = [] if a.rescore else a.engines.split(",")
    if a.rescore or a.merge:
        old = json.loads((out / "results.json").read_text())
        rows = [r for r in old["rows"] if r["engine"] not in run_engines]
        engine_info = {k: v for k, v in old["engines"].items() if k not in run_engines}
        texts = {sid: t for sid, _, t in SENTENCES}
        for r in rows:
            if r.get("status") == 200:
                r["cer_spoken"] = round(cer_spoken(texts[r["sentence"]], r["transcript"]), 4)

    with httpx.Client(timeout=httpx.Timeout(600, connect=5)) as c:
        for eng in run_engines:
            url, voices = ENGINES[eng]
            try:
                h = c.get(f"{url}/health", timeout=5).json()
                avail = {v["id"] for v in c.get(f"{url}/voices", timeout=5).json()}
            except (httpx.HTTPError, ValueError) as e:
                print(f"SKIP {eng}: not reachable ({e})", file=sys.stderr)
                engine_info[eng] = {"error": f"not reachable: {e}"}
                continue
            # warm-up (first call compiles kernels / allocates caches)
            first_voice = next(v for v in voices if v in avail)
            t0 = time.monotonic()
            c.post(f"{url}/synthesize", json={"text": "नमस्ते।", "voice": first_voice, "seed": 0})
            warm = time.monotonic() - t0
            for voice, langs in voices.items():
                if voice not in avail:
                    print(f"SKIP {eng}/{voice}: voice not offered", file=sys.stderr)
                    continue
                for sid, lang, text in SENTENCES:
                    if lang not in langs:
                        continue
                    for seed in seeds:
                        t0 = time.monotonic()
                        r = c.post(f"{url}/synthesize", json={"text": text, "voice": voice, "seed": seed})
                        wall = time.monotonic() - t0
                        row = {"engine": eng, "voice": voice, "sentence": sid, "language": lang, "seed": seed,
                               "chars": len(text), "status": r.status_code}
                        if r.status_code != 200:
                            row["error"] = r.text[:300]
                            rows.append(row)
                            print(f"ERR {eng}/{voice}/{sid}/{seed}: {r.text[:120]}", file=sys.stderr)
                            continue
                        wav = r.content
                        (out / "wav" / f"{eng}__{voice}__{sid}__s{seed}.wav").write_bytes(wav)
                        dur = duration_s(wav)
                        hyp = transcribe(c, wav, lang)
                        synth = float(r.headers.get("x-synth-seconds", wall))
                        row.update(wall_s=round(wall, 3), synth_s=round(synth, 3), audio_s=round(dur, 3),
                                   rtf=round(synth / dur, 3) if dur else None,
                                   chars_per_s=round(len(text) / dur, 2) if dur else None,
                                   rms_dbfs=round(rms_dbfs(wav), 1), cer=round(cer(text, hyp), 4),
                                   cer_spoken=round(cer_spoken(text, hyp), 4),
                                   transcript=hyp)
                        rows.append(row)
                        print(f"{eng:10s} {voice:15s} {sid} s{seed} cer={row['cer']:.3f} rtf={row['rtf']:.2f} "
                              f"dur={dur:.1f}s", flush=True)
            h = c.get(f"{url}/health", timeout=5).json()
            engine_info[eng] = {"warmup_s": round(warm, 2), "gpu_mem_mb": h.get("gpu_mem_mb"),
                                "peak_gpu_mem_mb": h.get("peak_gpu_mem_mb")}

    (out / "results.json").write_text(json.dumps({"engines": engine_info, "rows": rows}, ensure_ascii=False,
                                                 indent=1))
    keys = ["engine", "voice", "sentence", "language", "seed", "chars", "status", "wall_s", "synth_s", "audio_s",
            "rtf", "chars_per_s", "rms_dbfs", "cer", "cer_spoken", "transcript", "error"]
    with open(out / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)

    lines = ["| engine | voice | lang | n | errors | mean spoken CER | spoken CER>0.12 | mean raw CER | median RTF | "
             "median latency s | chars/s |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    groups: dict = {}
    for r in rows:
        groups.setdefault((r["engine"], r["voice"], "en" if r["language"] == "english" else "hi"), []).append(r)
    for (eng, voice, lang), rs in groups.items():
        ok = [r for r in rs if r["status"] == 200]
        if not ok:
            lines.append(f"| {eng} | {voice} | {lang} | {len(rs)} | {len(rs)} | – | – | – | – | – | – |")
            continue
        cers = [r["cer_spoken"] for r in ok]
        lines.append(
            f"| {eng} | {voice} | {lang} | {len(rs)} | {len(rs) - len(ok)} | {statistics.mean(cers):.3f} | "
            f"{sum(c > CER_OK for c in cers)}/{len(ok)} | {statistics.mean(r['cer'] for r in ok):.3f} | "
            f"{statistics.median(r['rtf'] for r in ok):.2f} | "
            f"{statistics.median(r['wall_s'] for r in ok):.2f} | "
            f"{statistics.median(r['chars_per_s'] for r in ok):.1f} |")
    lines += ["", "| engine | warm-up s | GPU MB (reserved) | peak GPU MB |", "|---|---|---|---|"]
    for eng, info in engine_info.items():
        lines.append(f"| {eng} | {info.get('warmup_s', '–')} | {info.get('gpu_mem_mb', '–')} | "
                     f"{info.get('peak_gpu_mem_mb', info.get('error', '–'))} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
