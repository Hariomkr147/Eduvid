"""Public OpenAI-compatible routes."""
import asyncio
import json
import os
import re
import tempfile
import time
from typing import Literal

import httpx
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel

from .auth import Caller, authenticate
from .errors import ApiError, engine_unavailable

router = APIRouter()

MAX_TTS_CHARS = 4000
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_AUDIO_SECONDS = 3600

# model id -> (engine, kind, commercial)  — commercial flags from docs/licences.md
MODELS = {
    "omnivoice": ("omnivoice", "tts", False),
    "kokoro": ("kokoro", "tts", True),
    "indicf5": ("indicf5", "tts", True),  # optional: only served when ENGINE_INDICF5_URL is set
    "whisper-large-v3": ("asr", "stt", True),
    "whisper-align": ("asr", "align", False),
}
STT_ALIASES = {"whisper-1": "whisper-large-v3", "whisper-large-v3": "whisper-large-v3"}
CONTENT_TYPES = {"wav": "audio/wav", "mp3": "audio/mpeg", "opus": "audio/ogg"}


# ---------- engine calls ----------

async def call_engine(request: Request, engine: str, method: str, path: str, *, pipeline: bool,
                      **kwargs) -> httpx.Response:
    st = request.app.state
    client: httpx.AsyncClient = st.engines[engine]

    async def _do() -> httpx.Response:
        try:
            r = await client.request(method, path, **kwargs)
        except (httpx.TransportError, OSError):
            raise engine_unavailable(engine)
        if r.status_code >= 500:
            raise engine_unavailable(engine)
        if r.status_code >= 400:
            try:
                msg = r.json().get("error") or r.text
            except ValueError:
                msg = r.text or "engine rejected the request"
            raise ApiError(r.status_code, str(msg), engine=engine)
        return r

    return await st.schedulers[engine].submit(_do, pipeline=pipeline)


async def log_usage(request: Request, caller: Caller, endpoint: str, model: str, t0: float,
                    characters: int | None = None, seconds: float | None = None) -> None:
    ms = int((time.monotonic() - t0) * 1000)
    async with request.app.state.db.connection() as conn:
        await conn.execute(
            "INSERT INTO api_usage (key_id, endpoint, model, status, characters, seconds, ms) "
            "VALUES (%s,%s,%s,200,%s,%s,%s)",
            (caller.key_id, endpoint, model, characters, seconds, ms),
        )


# ---------- ffmpeg helpers ----------

async def _run(*cmd: str, stdin: bytes | None = None, timeout: float = 120) -> tuple[int, bytes, bytes]:
    p = await asyncio.create_subprocess_exec(*cmd, stdin=asyncio.subprocess.PIPE if stdin is not None else None,
                                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(p.communicate(stdin), timeout)
    except asyncio.TimeoutError:
        p.kill()
        raise
    return p.returncode, out, err


async def convert_audio(wav: bytes, fmt: str) -> bytes:
    if fmt == "wav":
        return wav
    args = {"mp3": ["-c:a", "libmp3lame", "-b:a", "128k", "-f", "mp3"],
            "opus": ["-c:a", "libopus", "-b:a", "48k", "-f", "ogg"]}[fmt]
    rc, out, err = await _run("ffmpeg", "-v", "error", "-f", "wav", "-i", "pipe:0", *args, "pipe:1", stdin=wav)
    if rc != 0 or not out:
        raise ApiError(500, "audio conversion failed")
    return out


_TIME = re.compile(rb"time=(\d+):(\d+):(\d+(?:\.\d+)?)")


async def probe_duration(path: str) -> float | None:
    """Seconds of audio, or None if ffmpeg can't decode it. Streamed files (browser MediaRecorder WebM) have no
    duration in their header (ffprobe: N/A), so those are measured by decoding the audio."""
    rc, out, _ = await _run("ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", path, timeout=60)
    try:
        d = float(out.decode().strip())
        return d if rc == 0 and d > 0 else None
    except ValueError:
        pass
    rc, _, err = await _run("ffmpeg", "-nostdin", "-i", path, "-map", "0:a:0", "-f", "null", "-", timeout=300)
    times = _TIME.findall(err)
    if rc != 0 or not times:
        return None
    h, m, sec = times[-1]
    d = int(h) * 3600 + int(m) * 60 + float(sec)
    return d if d > 0 else None


async def read_upload(file: UploadFile) -> tuple[bytes, str, float]:
    """Read an upload (<= 100 MB), check it decodes and is <= 60 min. Returns (bytes, filename, seconds)."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "file too large", max_bytes=MAX_UPLOAD_BYTES)
    if not data:
        raise ApiError(400, "could not decode audio")
    suffix = os.path.splitext(file.filename or "")[1][:10]
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(data)
        tmp.flush()
        dur = await probe_duration(tmp.name)
    if dur is None:
        raise ApiError(400, "could not decode audio")
    if dur > MAX_AUDIO_SECONDS:
        raise ApiError(413, "audio too long", max_seconds=MAX_AUDIO_SECONDS)
    return data, file.filename or "audio", dur


# ---------- routes ----------

class SpeechRequest(BaseModel):
    model: str
    input: str
    voice: str
    language: str | None = None
    instruct: str | None = None
    speed: float = 1.0
    seed: int | None = None
    response_format: Literal["wav", "mp3", "opus"] = "wav"


@router.post("/v1/audio/speech")
async def speech(request: Request, body: SpeechRequest):
    caller = await authenticate(request, "tts")
    t0 = time.monotonic()
    if len(body.input) > MAX_TTS_CHARS:
        raise ApiError(413, "input too long", max_chars=MAX_TTS_CHARS)
    if not body.input.strip():
        raise ApiError(400, "input is empty")
    m = MODELS.get(body.model)
    engines = request.app.state.engines
    if m is None or m[1] != "tts" or m[0] not in engines:
        raise ApiError(400, f"unknown model '{body.model}'",
                       models=[k for k, v in MODELS.items() if v[1] == "tts" and v[0] in engines])
    if not 0.25 <= body.speed <= 4.0:
        raise ApiError(400, "speed must be between 0.25 and 4.0")
    r = await call_engine(request, m[0], "POST", "/synthesize", pipeline=caller.pipeline, json={
        "text": body.input, "voice": body.voice, "language": body.language, "instruct": body.instruct,
        "speed": body.speed, "seed": body.seed})
    audio = await convert_audio(r.content, body.response_format)
    await log_usage(request, caller, "/v1/audio/speech", body.model, t0, characters=len(body.input))
    return Response(audio, media_type=CONTENT_TYPES[body.response_format])


def _ts(t: float, sep: str) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _subtitles(segments: list[dict], vtt: bool) -> str:
    lines = ["WEBVTT", ""] if vtt else []
    for i, seg in enumerate(segments, 1):
        if not vtt:
            lines.append(str(i))
        sep = "." if vtt else ","
        lines.append(f"{_ts(seg['start'], sep)} --> {_ts(seg['end'], sep)}")
        lines.append(seg["text"].strip())
        lines.append("")
    return "\n".join(lines)


@router.post("/v1/audio/transcriptions")
async def transcriptions(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form("whisper-large-v3"),
    language: str | None = Form(None),
    prompt: str | None = Form(None),
    response_format: Literal["json", "verbose_json", "srt", "vtt", "text"] = Form("json"),
    timestamp_granularities: list[str] = Form(default=[], alias="timestamp_granularities[]"),
):
    caller = await authenticate(request, "stt")
    t0 = time.monotonic()
    model_id = STT_ALIASES.get(model)
    if model_id is None:
        raise ApiError(400, f"unknown model '{model}'", models=["whisper-large-v3"])
    data, name, dur = await read_upload(file)
    form = {k: v for k, v in {"language": language, "prompt": prompt}.items() if v}
    r = await call_engine(request, "asr", "POST", "/transcribe", pipeline=caller.pipeline,
                          files={"file": (name, data)}, data=form)
    res = r.json()
    await log_usage(request, caller, "/v1/audio/transcriptions", model_id, t0, seconds=round(dur, 3))
    segments = res.get("segments", [])
    if response_format == "text":
        return PlainTextResponse(res["text"].strip() + "\n")
    if response_format in ("srt", "vtt"):
        return PlainTextResponse(_subtitles(segments, response_format == "vtt"),
                                 media_type="text/vtt" if response_format == "vtt" else "application/x-subrip")
    if response_format == "json":
        return JSONResponse({"text": res["text"]})
    out = {
        "task": "transcribe",
        "language": res.get("language", language),
        "duration": round(dur, 3),
        "text": res["text"],
        "segments": [{"id": i, "start": s["start"], "end": s["end"], "text": s["text"]}
                     for i, s in enumerate(segments)],
    }
    if "word" in timestamp_granularities:
        out["words"] = [{"word": w["word"], "start": w.get("start"), "end": w.get("end"), "score": w.get("score")}
                        for s in segments for w in s.get("words", [])]
    return JSONResponse(out)


@router.post("/v1/audio/align")
async def align(
    request: Request,
    file: UploadFile = File(...),
    language: str = Form(...),
    text: str | None = Form(None),
    words: str | None = Form(None),
):
    caller = await authenticate(request, "stt")
    t0 = time.monotonic()
    if words:
        try:
            word_list = json.loads(words)
            assert isinstance(word_list, list) and all(isinstance(w, str) for w in word_list)
        except (ValueError, AssertionError):
            raise ApiError(400, "words must be a JSON list of strings")
    elif text:
        word_list = text.split()
    else:
        raise ApiError(400, "send 'text' or 'words'")
    if not word_list:
        raise ApiError(400, "no words to align")
    if sum(len(w) for w in word_list) > MAX_TTS_CHARS * 4:
        raise ApiError(413, "text too long", max_chars=MAX_TTS_CHARS * 4)
    data, name, dur = await read_upload(file)
    r = await call_engine(request, "asr", "POST", "/align", pipeline=caller.pipeline,
                          files={"file": (name, data)},
                          data={"words": json.dumps(word_list, ensure_ascii=False), "language": language})
    await log_usage(request, caller, "/v1/audio/align", "whisper-align", t0, seconds=round(dur, 3))
    return JSONResponse(r.json())


@router.get("/v1/models")
async def models(request: Request):
    await authenticate(request, None)
    return {"object": "list", "data": [
        {"id": k, "object": "model", "owned_by": "eduvid", "kind": v[1], "commercial": v[2]}
        for k, v in MODELS.items() if v[0] in request.app.state.engines]}


@router.get("/v1/voices")
async def voices(request: Request):
    await authenticate(request, None)
    st = request.app.state
    out, unavailable = [], []
    for model, (engine, kind, _) in MODELS.items():
        if kind != "tts" or engine not in st.engines:
            continue
        try:
            r = await st.engines[engine].get("/voices", timeout=5)
            r.raise_for_status()
            out += [{"model": model, **v} for v in r.json()]
        except (httpx.HTTPError, ValueError):
            unavailable.append(model)
    return {"object": "list", "data": out, "unavailable": unavailable}


@router.get("/health")
async def health(request: Request):
    st = request.app.state

    async def one(name: str, client: httpx.AsyncClient):
        try:
            r = await client.get("/health", timeout=httpx.Timeout(3.0, connect=2.0))
            body = r.json() if r.status_code == 200 else {}
            return name, {"ok": bool(body.get("ok")), **{k: v for k, v in body.items() if k != "ok"},
                          **st.schedulers[name].stats()}
        except (httpx.HTTPError, ValueError, OSError):
            return name, {"ok": False, **st.schedulers[name].stats()}

    results = dict(await asyncio.gather(*(one(n, c) for n, c in st.engines.items())))
    return {"ok": all(e["ok"] for e in results.values()), "engines": results}


@router.get("/livez")
async def livez():
    return {"ok": True}
