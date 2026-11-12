"""ASR engine: WhisperX large-v3 transcription + forced alignment (internal contract).

  POST /transcribe  multipart file, language?, prompt? -> {text, language, segments:[{start,end,text,words:[...]}]}
  POST /align       multipart file, words (JSON list[str]), language -> {words:[{word,start,end,score}], method}
  GET  /health

Every upload is decoded by ffmpeg to 16 kHz mono float32; anything ffmpeg can't decode -> 400.
/align uses the WhisperX wav2vec2 aligner for the language; if there is none, or its mean score is
below 0.3, it falls back to torchaudio MMS_FA on uroman-romanised words (MMS weights: CC-BY-NC 4.0).
"""
import asyncio
import json
import logging
import os
import re
import subprocess
import threading
import time
from contextlib import asynccontextmanager

import numpy as np
import torch
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

from eduvid_common.tts_server import _is_fatal_cuda, _is_oom

log = logging.getLogger("asr")
SR = 16000
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MODEL_NAME = os.environ.get("ASR_MODEL", "large-v3")
MIN_ALIGN_SCORE = 0.3

state: dict = {"model": None, "aligners": {}, "mms": None, "uroman": None}
lock = threading.Lock()


class DecodeError(Exception):
    pass


def decode(data: bytes) -> np.ndarray:
    if not data:
        raise DecodeError("empty")
    p = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", "pipe:0", "-ac", "1", "-ar", str(SR),
                        "-f", "f32le", "pipe:1"], input=data, capture_output=True, timeout=600)
    if p.returncode != 0 or len(p.stdout) < 4 * SR // 100:  # < 10 ms of audio
        raise DecodeError(p.stderr.decode(errors="replace")[-200:])
    return np.frombuffer(p.stdout, dtype=np.float32).copy()


def load():
    import whisperx

    t0 = time.monotonic()
    state["model"] = whisperx.load_model(MODEL_NAME, DEVICE, compute_type="float16" if DEVICE == "cuda" else "int8",
                                         download_root="/models/whisper")
    log.warning("whisper %s loaded in %.1fs", MODEL_NAME, time.monotonic() - t0)
    for lang in ("hi", "en"):
        try:
            aligner(lang)
        except Exception as e:  # noqa: BLE001
            log.warning("no aligner for %s: %s", lang, e)


def aligner(lang: str):
    import whisperx

    if lang not in state["aligners"]:
        model, meta = whisperx.load_align_model(language_code=lang, device=DEVICE)
        state["aligners"][lang] = (model, meta)
    return state["aligners"][lang]


def _set_prompt(model, prompt: str | None):
    opts = model.options
    try:
        model.options = opts._replace(initial_prompt=prompt)  # NamedTuple (older faster-whisper)
    except AttributeError:
        import dataclasses

        model.options = dataclasses.replace(opts, initial_prompt=prompt)


def transcribe(audio: np.ndarray, language: str | None, prompt: str | None) -> dict:
    import whisperx

    model = state["model"]
    _set_prompt(model, prompt or None)
    res = model.transcribe(audio, batch_size=16, language=language or None)
    lang = res.get("language") or language
    segments = res["segments"]
    try:
        am, meta = aligner(lang)
        segments = whisperx.align(segments, am, meta, audio, DEVICE, return_char_alignments=False)["segments"]
    except Exception as e:  # noqa: BLE001 — no aligner: keep segment-level times only
        log.warning("alignment skipped for %s: %s", lang, e)
    out = []
    for s in segments:
        words = [{"word": w["word"], "start": w.get("start"), "end": w.get("end"), "score": w.get("score")}
                 for w in s.get("words", [])]
        out.append({"start": round(float(s["start"]), 3), "end": round(float(s["end"]), 3),
                    "text": s["text"].strip(), "words": words})
    return {"text": " ".join(s["text"] for s in out).strip(), "language": lang, "segments": out}


def fill_gaps(words: list[str], got: list[dict], dur: float) -> list[dict]:
    """One entry per input word, in order; words without times are spread evenly between known neighbours."""
    out = [{"word": w, "start": (got[i] if i < len(got) else {}).get("start"),
            "end": (got[i] if i < len(got) else {}).get("end"),
            "score": float((got[i] if i < len(got) else {}).get("score") or 0.0)} for i, w in enumerate(words)]
    known = [i for i, o in enumerate(out) if o["start"] is not None and o["end"] is not None]
    i = 0
    while i < len(out):
        if i in known:
            i += 1
            continue
        j = i
        while j < len(out) and j not in known:
            j += 1
        lo = out[i - 1]["end"] if i > 0 else 0.0
        hi = out[j]["start"] if j < len(out) else dur
        step = max(hi - lo, 0.0) / (j - i)
        for k in range(i, j):
            out[k].update(start=lo + (k - i) * step, end=lo + (k - i + 1) * step, score=0.0)
        i = j
    prev_end = 0.0
    for o in out:  # clamp into the clip and keep times non-decreasing
        s = min(max(float(o["start"]), prev_end), dur)
        e = min(max(float(o["end"]), s), dur)
        o.update(start=round(s, 3), end=round(e, 3), score=round(o["score"], 3))
        prev_end = s
    return out


def align_wav2vec2(audio: np.ndarray, words: list[str], lang: str) -> list[dict]:
    import whisperx

    am, meta = aligner(lang)
    dur = len(audio) / SR
    seg = [{"start": 0.0, "end": dur, "text": " ".join(words)}]
    res = whisperx.align(seg, am, meta, audio, DEVICE, return_char_alignments=False)
    got = [w for s in res["segments"] for w in s.get("words", [])]
    return fill_gaps(words, got[: len(words)], dur)


def _romanize(words: list[str]) -> list[str]:
    import uroman as ur

    if state["uroman"] is None:
        state["uroman"] = ur.Uroman()
    return [re.sub(r"[^a-z']", "", state["uroman"].romanize_string(w).lower()) for w in words]


def align_mms(audio: np.ndarray, words: list[str]) -> list[dict]:
    import torchaudio

    bundle = torchaudio.pipelines.MMS_FA
    if state["mms"] is None:
        state["mms"] = (bundle.get_model(with_star=False).to(DEVICE), bundle.get_tokenizer(), bundle.get_aligner())
    model, tokenizer, mms_aligner = state["mms"]
    dur = len(audio) / SR
    roman = _romanize(words)
    idx = [i for i, r in enumerate(roman) if r]
    got: list[dict] = [{} for _ in words]
    if idx:
        wave = torch.from_numpy(audio).unsqueeze(0).to(DEVICE)
        with torch.inference_mode():
            emission, _ = model(wave)
            spans = mms_aligner(emission[0], tokenizer([roman[i] for i in idx]))
        ratio = wave.size(1) / emission.size(1) / SR
        for i, sp in zip(idx, spans):
            n = sum(len(t) for t in sp)
            got[i] = {"start": sp[0].start * ratio, "end": sp[-1].end * ratio,
                      "score": float(sum(t.score * len(t) for t in sp) / max(1, n))}
    return fill_gaps(words, got, dur)


def do_align(audio: np.ndarray, words: list[str], lang: str) -> dict:
    try:
        res = align_wav2vec2(audio, words, lang)
        mean = sum(w["score"] for w in res) / len(res)
        if mean >= MIN_ALIGN_SCORE:
            return {"words": res, "method": "wav2vec2"}
        log.warning("wav2vec2 mean score %.2f < %.2f, trying MMS", mean, MIN_ALIGN_SCORE)
    except Exception as e:  # noqa: BLE001
        log.warning("wav2vec2 aligner unavailable for %s (%s), using MMS", lang, e)
    return {"words": align_mms(audio, words), "method": "mms"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(load)
    yield


app = FastAPI(title="asr-whisperx", lifespan=lifespan)


def _run_locked(fn, *args):
    with lock:
        return fn(*args)


def _bad_audio() -> JSONResponse:
    return JSONResponse({"error": "could not decode audio"}, status_code=400)


def _exit_for_restart() -> None:
    os._exit(1)                                   # compose restart: unless-stopped brings a clean process back


def _engine_error(e: Exception, what: str) -> JSONResponse:
    """OOM: free the cache and stay up. Fatal CUDA error (the context is unusable): report down and exit so Docker
    restarts the container — otherwise every later call fails while /health stays green (Review Focus 4)."""
    if _is_oom(e):
        torch.cuda.empty_cache()
        log.error("%s: out of memory: %s", what, e)
        return JSONResponse({"error": "out of memory"}, status_code=500)
    if _is_fatal_cuda(e):
        state["broken"] = f"{type(e).__name__}: {e}"[:300]
        log.critical("%s: fatal CUDA error, exiting for restart: %s", what, e)
        asyncio.get_running_loop().call_later(0.2, _exit_for_restart)
        return JSONResponse({"error": "engine crashed"}, status_code=500)
    log.exception("%s failed", what)
    return JSONResponse({"error": f"{what} failed: {type(e).__name__}"}, status_code=500)


@app.post("/transcribe")
async def transcribe_route(file: UploadFile = File(...), language: str | None = Form(None),
                           prompt: str | None = Form(None)):
    try:
        audio = await asyncio.to_thread(decode, await file.read())
    except DecodeError:
        return _bad_audio()
    try:
        return await asyncio.to_thread(_run_locked, transcribe, audio, language, prompt)
    except Exception as e:  # noqa: BLE001
        return _engine_error(e, "transcription")


@app.post("/align")
async def align_route(file: UploadFile = File(...), words: str = Form(...), language: str = Form(...)):
    try:
        word_list = json.loads(words)
        assert isinstance(word_list, list) and word_list and all(isinstance(w, str) and w for w in word_list)
    except (ValueError, AssertionError):
        return JSONResponse({"error": "words must be a non-empty JSON list of strings"}, status_code=400)
    try:
        audio = await asyncio.to_thread(decode, await file.read())
    except DecodeError:
        return _bad_audio()
    try:
        return await asyncio.to_thread(_run_locked, do_align, audio, word_list, language)
    except Exception as e:  # noqa: BLE001
        return _engine_error(e, "alignment")


@app.get("/health")
async def health():
    mem = int(torch.cuda.memory_reserved() / 2**20) if torch.cuda.is_available() else 0
    return {"ok": state["model"] is not None and not state.get("broken"), "model": f"whisper-{MODEL_NAME}", "gpu_mem_mb": mem,
            "aligners": sorted(state["aligners"])}
