"""Shared FastAPI server for TTS engines (internal contract).

  POST /synthesize {text, voice, language?, instruct?, speed=1.0, seed?} -> audio/wav (24 kHz mono s16)
  GET  /voices -> [{id, language, description}]
  GET  /health -> {ok, model, gpu_mem_mb, peak_gpu_mem_mb}

An engine supplies a Backend. The model loads once at startup; calls run one at a time (one GPU).
A CUDA error that is not a plain out-of-memory exits the process so Docker restarts the container.
"""
import asyncio
import io
import logging
import os
import random
import threading
import time
import wave
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from .audio import SR, to_wav_24k_mono

log = logging.getLogger("tts")
MAX_CHARS = int(os.environ.get("TTS_MAX_CHARS", "4000"))


class Backend:
    """Subclass and implement load / voices / synthesize."""

    name = "base"

    def load(self) -> None:
        raise NotImplementedError

    def voices(self) -> list[dict]:
        raise NotImplementedError

    def synthesize(self, text: str, voice: str, language: str | None, instruct: str | None,
                   speed: float, seed: int):
        """Return (mono float samples in [-1, 1] as a numpy array, sample_rate)."""
        raise NotImplementedError


class SynthRequest(BaseModel):
    text: str
    voice: str
    language: str | None = None
    instruct: str | None = None
    speed: float = 1.0
    seed: int | None = None


def seed_everything(seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed % (2**32))
    except ImportError:
        pass
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def samples_to_wav(samples, sr: int) -> bytes:
    import numpy as np

    a = np.asarray(samples, dtype=np.float32).reshape(-1)
    a = np.nan_to_num(a)
    peak = float(np.max(np.abs(a))) if a.size else 0.0
    if peak > 1.0:  # some models return int-range floats or slightly clipped audio
        a = a / (32768.0 if peak > 2.0 else peak)
    pcm = (np.clip(a, -1.0, 1.0) * 32767.0).round().astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    wav = buf.getvalue()
    return wav if sr == SR else to_wav_24k_mono(wav)


def _gpu_mem() -> tuple[int, int]:
    try:
        import torch

        if torch.cuda.is_available():
            return (int(torch.cuda.memory_reserved() / 2**20), int(torch.cuda.max_memory_reserved() / 2**20))
    except ImportError:
        pass
    return 0, 0


def _is_oom(e: BaseException) -> bool:
    return "out of memory" in str(e).lower() or type(e).__name__ == "OutOfMemoryError"


def _is_fatal_cuda(e: BaseException) -> bool:
    s = str(e)
    return ("CUDA error" in s or "cuDNN error" in s or "CUBLAS_STATUS" in s) and not _is_oom(e)


def make_app(backend: Backend) -> FastAPI:
    lock = threading.Lock()
    state = {"loaded": False, "voices": {}}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        t0 = time.monotonic()
        await asyncio.to_thread(backend.load)
        state["voices"] = {v["id"]: v for v in backend.voices()}
        state["loaded"] = True
        log.warning("%s loaded in %.1fs, voices=%s", backend.name, time.monotonic() - t0, list(state["voices"]))
        yield

    app = FastAPI(title=f"tts-{backend.name}", lifespan=lifespan)

    def err(status: int, msg: str, **extra) -> JSONResponse:
        return JSONResponse({"error": msg, **extra}, status_code=status)

    def run(req: SynthRequest, seed: int):
        with lock:
            seed_everything(seed)
            t0 = time.monotonic()
            samples, sr = backend.synthesize(req.text, req.voice, req.language, req.instruct, req.speed, seed)
            return samples, sr, time.monotonic() - t0

    @app.post("/synthesize")
    async def synthesize(req: SynthRequest):
        if req.voice not in state["voices"]:
            return err(400, f"unknown voice '{req.voice}'", voices=sorted(state["voices"]))
        if not req.text.strip():
            return err(400, "text is empty")
        if len(req.text) > MAX_CHARS:
            return err(413, "input too long", max_chars=MAX_CHARS)
        if not 0.25 <= req.speed <= 4.0:
            return err(400, "speed must be between 0.25 and 4.0")
        seed = req.seed if req.seed is not None else random.randrange(2**31)
        try:
            samples, sr, secs = await asyncio.to_thread(run, req, seed)
        except Exception as e:  # noqa: BLE001
            if _is_oom(e):
                try:
                    import torch

                    torch.cuda.empty_cache()
                except ImportError:
                    pass
                log.error("OOM: %s", e)
                return err(500, "out of memory")
            if _is_fatal_cuda(e):
                log.critical("fatal CUDA error, exiting for restart: %s", e)
                asyncio.get_running_loop().call_later(0.2, os._exit, 1)
                return err(500, "engine crashed")
            log.exception("synthesis failed")
            return err(500, f"synthesis failed: {type(e).__name__}: {e}"[:500])
        wav = samples_to_wav(samples, sr)
        return Response(wav, media_type="audio/wav",
                        headers={"X-Seed": str(seed), "X-Synth-Seconds": f"{secs:.3f}"})

    @app.get("/voices")
    async def voices():
        return list(state["voices"].values())

    @app.get("/health")
    async def health():
        cur, peak = _gpu_mem()
        return {"ok": state["loaded"], "model": backend.name, "gpu_mem_mb": cur, "peak_gpu_mem_mb": peak}

    return app
