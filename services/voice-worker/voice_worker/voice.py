"""voice job: script.json `say` lines -> narration.wav + lines.json + takes report.

Same rules as engine/scripts/voice.py: lines are grouped into whole sentences (a line ending in . ? ! । ॥ closes one,
"break": true forces a close) and each sentence is synthesised in one pass; cuts inside a sentence are placed by
spoken-text length and snapped to the nearest pause (words.py then moves them onto aligned word boundaries).

Voice-to-script check (spec §5.4): each sentence is transcribed back and compared with its `say` text. Spoken CER above
CER_MAX -> a new take with the next seed; after len(SEEDS) bad takes the best one is kept and the sentence is flagged.
"""
import io
import re
import wave
from collections.abc import Callable

import numpy as np

from eduvid_common.speakable import violations
from eduvid_common.textmetrics import cer_mixed

SR = 24000
CER_MAX = 0.12
SEEDS = (1, 2, 3)
SENTENCE_END = re.compile(r'[.?!।॥]["\')]*$')

Synth = Callable[[str, str, int], bytes]          # (text, voice, seed) -> 24 kHz mono 16-bit WAV
Transcribe = Callable[[bytes, str], str]          # (wav, language) -> text


class SpeakableError(ValueError):
    """The script can't be spoken as written. Retrying won't help."""


def read_wav(data: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(data)) as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (SR, 1, 2):
            raise ValueError(f"expected 24 kHz mono 16-bit WAV, got {w.getframerate()} Hz "
                             f"{w.getnchannels()} ch {8 * w.getsampwidth()} bit")
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768.0


def write_wav(x: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def trim(x: np.ndarray, thr: float = 0.008) -> np.ndarray:
    """cut leading/trailing silence so line start/end times are exact (engine voice.py)"""
    idx = np.where(np.abs(x) > thr)[0]
    if not len(idx):
        return x
    a = max(0, idx[0] - int(0.01 * SR))
    b = min(len(x), idx[-1] + int(0.03 * SR))
    return x[a:b]


def silences(x: np.ndarray, thr: float = 0.012, min_len: float = 0.06) -> list[tuple[float, float]]:
    """pauses inside speech: [(start_s, end_s)] where the 10 ms RMS stays under thr x peak for >= min_len"""
    hop = int(0.01 * SR)
    n = len(x) // hop
    if n == 0:
        return []
    rms = np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1))
    quiet = rms < thr * (np.abs(x).max() or 1.0)
    out, st = [], None
    for f, q in enumerate(quiet):
        if q and st is None:
            st = f
        if (not q or f == n - 1) and st is not None:
            if (f - st) * 0.01 >= min_len:
                out.append((st * 0.01, f * 0.01))
            st = None
    return out


def group_lines(lines: list[dict]) -> list[list[int]]:
    groups, cur = [], []
    for i, ln in enumerate(lines):
        cur.append(i)
        if SENTENCE_END.search(ln["say"].strip()) or ln.get("break") or i == len(lines) - 1:
            groups.append(cur)
            cur = []
    return groups


def check_speakable(script: dict, language: str) -> None:
    problems = []
    for i, ln in enumerate(script.get("lines") or []):
        say = ln.get("say")
        if not isinstance(say, str) or not say.strip():
            problems.append(f"line {i}: no 'say' text")
            continue
        bad = violations(say, language)
        if bad:
            problems.append(f"line {i}: not speakable ({' '.join(sorted(set(bad)))}): {say}")
    if not script.get("lines"):
        problems.append("script has no lines")
    if problems:
        raise SpeakableError("; ".join(problems))


def _take(text: str, voice: str, language: str, synth: Synth, transcribe: Transcribe) -> tuple[np.ndarray, dict]:
    tried, best = [], None
    for seed in SEEDS:
        wav = synth(text, voice, seed)
        hyp = transcribe(wav, language)
        c = round(cer_mixed(text, hyp), 4)
        tried.append({"seed": seed, "cer": c, "transcript": hyp})
        if best is None or c < best[0]:
            best = (c, seed, wav)
        if c <= CER_MAX:
            break
    c, seed, wav = best
    return trim(read_wav(wav)), {"takes": len(tried), "cer": [t["cer"] for t in tried], "seed": seed,
                                 "best_cer": c, "flagged": c > CER_MAX,
                                 "transcripts": [t["transcript"] for t in tried]}


def build_narration(script: dict, language: str, voice: str, synth: Synth,
                    transcribe: Transcribe) -> tuple[bytes, dict, list[dict]]:
    """-> (narration_wav, lines_json, take_report). Raises SpeakableError before any synthesis."""
    check_speakable(script, language)
    lines = script["lines"]
    out = [np.zeros(int(float(script.get("lead", 0.12)) * SR))]
    t = len(out[0]) / SR
    placed: list[dict | None] = [None] * len(lines)
    report = []
    for gi, g in enumerate(group_lines(lines)):
        text = " ".join(lines[i]["say"].strip() for i in g)
        x, rep = _take(text, voice, language, synth, transcribe)
        report.append({"group": gi, "lines": g, "text": text, **rep})
        cuts: list[tuple[float, float]] = [(0.0, 0.0)]
        if len(g) > 1:
            lens = np.array([len(re.sub(r"[^\w]", "", lines[i]["say"])) + 1 for i in g], dtype=float)
            pauses = silences(x)
            for c in np.cumsum(lens)[:-1] / lens.sum() * len(x) / SR:
                near = [p for p in pauses if abs((p[0] + p[1]) / 2 - c) < 0.4]
                cuts.append(min(near, key=lambda p: abs((p[0] + p[1]) / 2 - c)) if near else (c, c))
        n = len(x) / SR
        for j, i in enumerate(g):
            a = 0.0 if j == 0 else cuts[j][1]
            b = n if j == len(g) - 1 else cuts[j + 1][0]
            placed[i] = {"i": i, "text": lines[i].get("text", lines[i]["say"]), "say": lines[i]["say"],
                         "start": round(t + a, 3), "end": round(t + b, 3), "group": gi,
                         "group_start": round(t, 3), "group_end": round(t + n, 3)}
        gap = np.zeros(int(float(lines[g[-1]].get("gap", script.get("gap", 0.3))) * SR))
        out += [x, gap]
        t += (len(x) + len(gap)) / SR
    out.append(np.zeros(int(float(script.get("outro", 0.45)) * SR)))
    y = np.concatenate(out)
    y = y / (np.abs(y).max() + 1e-9) * 0.9
    lines_json = {"duration": round(len(y) / SR, 3), "voice": voice, "lines": placed}
    return write_wav(y), lines_json, report
