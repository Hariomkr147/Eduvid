import io
import json
import subprocess
import time
import wave

import httpx
import pytest

from tests.conftest import make_wav

pytestmark = pytest.mark.anyio


def H(key):
    return {"Authorization": f"Bearer {key}"}


async def test_health_no_auth(gateway):
    r = await gateway.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert set(body["engines"]) == {"omnivoice", "kokoro", "asr"}
    assert all(e["ok"] for e in body["engines"].values())


async def test_speech_roundtrip_wav(gateway, make_key, engines):
    key = make_key()
    r = await gateway.post("/v1/audio/speech", headers=H(key), json={
        "model": "omnivoice", "voice": "hinglish-female", "input": "सिलेंडर का एरिया", "seed": 7})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(r.content)) as w:
        assert w.getframerate() == 24000 and w.getnchannels() == 1
    sent = engines["omnivoice"].state.calls[-1]
    assert sent["text"] == "सिलेंडर का एरिया" and sent["seed"] == 7 and sent["voice"] == "hinglish-female"


async def test_speech_mp3_content_type(gateway, make_key):
    r = await gateway.post("/v1/audio/speech", headers=H(make_key()), json={
        "model": "kokoro", "voice": "am_michael", "input": "two pi r h", "response_format": "mp3"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.content[:3] == b"ID3" or r.content[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")


async def test_speech_opus(gateway, make_key):
    r = await gateway.post("/v1/audio/speech", headers=H(make_key()), json={
        "model": "kokoro", "voice": "am_michael", "input": "hello", "response_format": "opus"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/ogg"
    assert r.content[:4] == b"OggS"


async def test_input_too_long_413(gateway, make_key, engines):
    n_before = len(engines["kokoro"].state.calls)
    t0 = time.monotonic()
    r = await gateway.post("/v1/audio/speech", headers=H(make_key()), json={
        "model": "kokoro", "voice": "am_michael", "input": "a" * 4001})
    assert r.status_code == 413
    assert r.json() == {"error": "input too long", "max_chars": 4000}
    assert time.monotonic() - t0 < 1
    assert len(engines["kokoro"].state.calls) == n_before  # engine never called


async def test_input_20000_chars_413(gateway, make_key):
    r = await gateway.post("/v1/audio/speech", headers=H(make_key()), json={
        "model": "omnivoice", "voice": "hinglish-female", "input": "क" * 20000})
    assert r.status_code == 413 and r.json()["max_chars"] == 4000


async def test_unknown_model_400(gateway, make_key):
    r = await gateway.post("/v1/audio/speech", headers=H(make_key()), json={
        "model": "tts-1", "voice": "x", "input": "hi"})
    assert r.status_code == 400 and "model" in r.json()["error"]


async def test_engine_400_passes_through(gateway, make_key):
    r = await gateway.post("/v1/audio/speech", headers=H(make_key()), json={
        "model": "kokoro", "voice": "nobody", "input": "hi"})
    assert r.status_code == 400 and "unknown voice" in r.json()["error"]


async def test_bad_json_is_json_error(gateway, make_key):
    r = await gateway.post("/v1/audio/speech", headers=H(make_key()), json={"model": "kokoro"})
    assert r.status_code == 422 and "error" in r.json()


async def test_transcription_openai_shape(gateway, make_key):
    files = {"file": ("a.wav", make_wav(1.5), "audio/wav")}
    data = {"model": "whisper-large-v3", "language": "hi", "response_format": "verbose_json",
            "timestamp_granularities[]": ["word", "segment"]}
    r = await gateway.post("/v1/audio/transcriptions", headers=H(make_key()), files=files, data=data)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"] == "सिलेंडर का एरिया"
    assert body["language"] == "hi"
    assert body["segments"][0]["start"] == 0.1
    assert [w["word"] for w in body["words"]] == ["सिलेंडर", "का", "एरिया"]
    assert abs(body["duration"] - 1.5) < 0.05


async def test_transcription_json_and_text_and_srt(gateway, make_key):
    key = make_key()
    for fmt, check in [
        ("json", lambda r: r.json() == {"text": "सिलेंडर का एरिया"}),
        ("text", lambda r: r.text.strip() == "सिलेंडर का एरिया"),
        ("srt", lambda r: "00:00:00,100 --> 00:00:01,400" in r.text),
        ("vtt", lambda r: r.text.startswith("WEBVTT") and "00:00:00.100 --> 00:00:01.400" in r.text),
    ]:
        r = await gateway.post("/v1/audio/transcriptions", headers=H(key),
                               files={"file": ("a.wav", make_wav(1.5), "audio/wav")},
                               data={"model": "whisper-large-v3", "response_format": fmt})
        assert r.status_code == 200 and check(r), (fmt, r.text)


async def test_transcription_words_omitted_without_granularity(gateway, make_key):
    r = await gateway.post("/v1/audio/transcriptions", headers=H(make_key()),
                           files={"file": ("a.wav", make_wav(1.0), "audio/wav")},
                           data={"model": "whisper-1", "response_format": "verbose_json"})
    assert r.status_code == 200 and "words" not in r.json()


async def test_transcription_corrupt_400(gateway, make_key):
    for blob in (b"", b"\x00garbage" * 100):
        r = await gateway.post("/v1/audio/transcriptions", headers=H(make_key()),
                               files={"file": ("a.mp3", blob, "audio/mpeg")},
                               data={"model": "whisper-large-v3"})
        assert r.status_code == 400 and r.json()["error"] == "could not decode audio"


async def test_transcription_too_long_413(gateway, make_key, tmp_path):
    p = tmp_path / "long.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=8000:cl=mono", "-t", "3601",
                    "-b:a", "8k", str(p)], check=True)
    r = await gateway.post("/v1/audio/transcriptions", headers=H(make_key()),
                           files={"file": ("long.mp3", p.read_bytes(), "audio/mpeg")},
                           data={"model": "whisper-large-v3"})
    assert r.status_code == 413 and r.json()["max_seconds"] == 3600


async def test_align_route(gateway, make_key):
    r = await gateway.post("/v1/audio/align", headers=H(make_key()),
                           files={"file": ("a.wav", make_wav(1.5), "audio/wav")},
                           data={"text": "सिलेंडर का एरिया", "language": "hi"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [w["word"] for w in body["words"]] == ["सिलेंडर", "का", "एरिया"]
    assert body["method"] == "wav2vec2"
    r2 = await gateway.post("/v1/audio/align", headers=H(make_key()),
                            files={"file": ("a.wav", make_wav(1.5), "audio/wav")},
                            data={"words": json.dumps(["a", "b"]), "language": "en"})
    assert [w["word"] for w in r2.json()["words"]] == ["a", "b"]


async def test_usage_row_written(gateway, make_key, db):
    from speech_api.auth import hash_key

    key = make_key()
    (kid,) = db.execute("SELECT id FROM api_keys WHERE hash=%s", (hash_key(key),)).fetchone()
    await gateway.post("/v1/audio/speech", headers=H(key), json={
        "model": "kokoro", "voice": "am_michael", "input": "hello there"})
    await gateway.post("/v1/audio/transcriptions", headers=H(key),
                       files={"file": ("a.wav", make_wav(2.0), "audio/wav")}, data={"model": "whisper-large-v3"})
    rows = db.execute("SELECT endpoint, model, characters, seconds, ms FROM api_usage WHERE key_id=%s ORDER BY id",
                      (kid,)).fetchall()
    assert [r[0] for r in rows] == ["/v1/audio/speech", "/v1/audio/transcriptions"]
    assert rows[0][1] == "kokoro" and rows[0][2] == len("hello there")
    assert rows[1][1] == "whisper-large-v3" and abs(float(rows[1][3]) - 2.0) < 0.05
    assert all(r[4] >= 0 for r in rows)


async def test_models_and_voices(gateway, make_key):
    key = make_key()
    models = (await gateway.get("/v1/models", headers=H(key))).json()["data"]
    by_id = {m["id"]: m for m in models}
    assert by_id["omnivoice"]["commercial"] is False and by_id["kokoro"]["commercial"] is True
    voices = (await gateway.get("/v1/voices", headers=H(key))).json()["data"]
    assert {"model": "omnivoice", "id": "hinglish-female", "language": "hi", "description": "hinglish-female"} in voices


async def test_engine_down_503_fast(pg_url, engines, make_key):
    from speech_api.app import create_app

    transports = {k: httpx.ASGITransport(app=v) for k, v in engines.items() if k != "kokoro"}
    urls = {"omnivoice": "http://omnivoice", "asr": "http://asr", "kokoro": "http://127.0.0.1:9"}  # nothing listens
    app = create_app(engine_urls=urls, transports=transports, database_url=pg_url)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw") as c:
            t0 = time.monotonic()
            r = await c.post("/v1/audio/speech", headers=H(make_key()), json={
                "model": "kokoro", "voice": "am_michael", "input": "hi"})
            assert time.monotonic() - t0 < 5
            assert r.status_code == 503
            assert r.json() == {"error": "engine unavailable", "engine": "kokoro"}
            h = (await c.get("/health")).json()
            assert h["ok"] is False and h["engines"]["kokoro"]["ok"] is False
            assert h["engines"]["omnivoice"]["ok"] is True


async def test_engine_5xx_is_503(pg_url, engines, make_key):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    from speech_api.app import create_app

    broken = FastAPI()

    @broken.post("/synthesize")
    async def oom():
        return JSONResponse({"error": "CUDA out of memory"}, status_code=500)

    transports = {k: httpx.ASGITransport(app=v) for k, v in engines.items()}
    transports["omnivoice"] = httpx.ASGITransport(app=broken)
    app = create_app(engine_urls={k: f"http://{k}" for k in engines}, transports=transports, database_url=pg_url)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw") as c:
            r = await c.post("/v1/audio/speech", headers=H(make_key()), json={
                "model": "omnivoice", "voice": "hinglish-female", "input": "x"})
            assert r.status_code == 503 and r.json()["engine"] == "omnivoice"


async def test_queue_full_429_route(pg_url, engines, make_key):
    import asyncio

    from speech_api.app import create_app

    gate = asyncio.Event()
    from fastapi import FastAPI
    from fastapi.responses import Response

    slow = FastAPI()

    @slow.post("/synthesize")
    async def synth():
        await gate.wait()
        return Response(make_wav(0.1), media_type="audio/wav")

    transports = {k: httpx.ASGITransport(app=v) for k, v in engines.items()}
    transports["kokoro"] = httpx.ASGITransport(app=slow)
    app = create_app(engine_urls={k: f"http://{k}" for k in engines}, transports=transports,
                     database_url=pg_url, max_waiting=2)
    key = make_key()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw") as c:
            body = {"model": "kokoro", "voice": "am_michael", "input": "x"}
            first = [asyncio.create_task(c.post("/v1/audio/speech", headers=H(key), json=body)) for _ in range(3)]
            await asyncio.sleep(0.2)
            r = await c.post("/v1/audio/speech", headers=H(key), json=body)
            assert r.status_code == 429 and r.headers["retry-after"] == "10"
            gate.set()
            assert [x.status_code for x in await asyncio.gather(*first)] == [200, 200, 200]


async def test_transcription_streamed_webm_without_duration_header(gateway, make_key):
    # browser MediaRecorder output: WebM/Opus written as a stream, so the header has no duration (ffprobe: N/A)
    webm = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=2", "-c:a", "libopus",
                           "-f", "webm", "pipe:1"], capture_output=True, check=True).stdout
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", "-"],
                           input=webm, capture_output=True).stdout.decode().strip()
    assert probe == "N/A"                                           # the input class this test is about
    r = await gateway.post("/v1/audio/transcriptions", headers=H(make_key()),
                           files={"file": ("mic.webm", webm, "audio/webm")}, data={"model": "whisper-1"})
    assert r.status_code == 200, r.text
