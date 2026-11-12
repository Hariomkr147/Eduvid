"""Fake engines (ASGI apps) + a gateway wired to them through httpx.ASGITransport."""
import io
import math
import os
import struct
import wave

import httpx
import psycopg
import pytest
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response


def make_wav(seconds: float = 1.0, sr: int = 24000, freq: float = 440.0) -> bytes:
    n = int(seconds * sr)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i / sr))) for i in range(n)))
    return buf.getvalue()


def fake_tts(name: str, voices: list[str]) -> FastAPI:
    app = FastAPI()
    app.state.calls = []

    @app.post("/synthesize")
    async def synthesize(req: Request):
        body = await req.json()
        app.state.calls.append(body)
        if body["voice"] not in voices:
            return JSONResponse({"error": f"unknown voice {body['voice']}"}, status_code=400)
        return Response(make_wav(0.5), media_type="audio/wav")

    @app.get("/voices")
    async def list_voices():
        return [{"id": v, "language": "hi", "description": v} for v in voices]

    @app.get("/health")
    async def health():
        return {"ok": True, "model": name, "gpu_mem_mb": 1000}

    return app


def fake_asr() -> FastAPI:
    app = FastAPI()

    @app.post("/transcribe")
    async def transcribe(file: UploadFile = File(...), language: str | None = Form(None), prompt: str | None = Form(None)):
        await file.read()
        words = [{"word": "सिलेंडर", "start": 0.1, "end": 0.6, "score": 0.9},
                 {"word": "का", "start": 0.7, "end": 0.8, "score": 0.9},
                 {"word": "एरिया", "start": 0.9, "end": 1.4, "score": 0.9}]
        return {"text": "सिलेंडर का एरिया", "language": language or "hi",
                "segments": [{"start": 0.1, "end": 1.4, "text": "सिलेंडर का एरिया", "words": words}]}

    @app.post("/align")
    async def align(file: UploadFile = File(...), words: str = Form(...), language: str = Form(...)):
        import json

        ws = json.loads(words)
        return {"words": [{"word": w, "start": 0.1 + i * 0.5, "end": 0.5 + i * 0.5, "score": 0.8}
                          for i, w in enumerate(ws)], "method": "wav2vec2"}

    @app.get("/health")
    async def health():
        return {"ok": True, "model": "whisper-large-v3", "gpu_mem_mb": 5000}

    return app


@pytest.fixture(scope="session")
def pg_url():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    from eduvid_common.testing import fresh_test_db

    return fresh_test_db()


@pytest.fixture
def engines():
    return {
        "omnivoice": fake_tts("omnivoice", ["hinglish-female", "hinglish-male", "hindi-female", "hindi-male"]),
        "kokoro": fake_tts("kokoro", ["am_michael", "af_heart"]),
        "asr": fake_asr(),
    }


@pytest.fixture
async def gateway(pg_url, engines):
    from speech_api.app import create_app

    transports = {k: httpx.ASGITransport(app=v) for k, v in engines.items()}
    urls = {k: f"http://{k}" for k in engines}
    app = create_app(engine_urls=urls, transports=transports, database_url=pg_url)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw") as c:
            c.app = app
            yield c


@pytest.fixture
def make_key(pg_url):
    from speech_api.auth import create_key

    def _make(scopes=("tts", "stt"), pipeline=False, rate_limit=1000, name="test"):
        return create_key(pg_url, name=name, scopes=list(scopes), pipeline=pipeline, rate_limit=rate_limit)

    return _make


@pytest.fixture
def db(pg_url):
    with psycopg.connect(pg_url, autocommit=True) as c:
        yield c


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
