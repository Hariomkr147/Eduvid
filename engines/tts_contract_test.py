"""Internal TTS contract test, copied into every TTS engine image as tests/test_contract.py.

Configured by env: TEST_VOICE, TEST_TEXT, TEST_DETERMINISTIC (1 = byte-identical with the same seed,
0 = duration within 2%). Runs the real model on the GPU.
"""
import io
import os
import wave

import pytest
from fastapi.testclient import TestClient

from eduvid_common.audio import rms_dbfs

pytestmark = pytest.mark.gpu

VOICE = os.environ["TEST_VOICE"]
TEXT = os.environ.get("TEST_TEXT", "सिलेंडर का सरफेस एरिया टू पाई आर एच होता है।")
DETERMINISTIC = os.environ.get("TEST_DETERMINISTIC", "1") == "1"


@pytest.fixture(scope="module")
def client():
    from server import app

    with TestClient(app) as c:
        yield c


def _info(wav: bytes):
    with wave.open(io.BytesIO(wav)) as w:
        return w.getframerate(), w.getnchannels(), w.getnframes() / w.getframerate()


def test_synthesize_returns_24k_mono_wav(client):
    r = client.post("/synthesize", json={"text": TEXT, "voice": VOICE, "seed": 1})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "audio/wav"
    sr, ch, dur = _info(r.content)
    assert (sr, ch) == (24000, 1)
    assert 1.5 <= dur <= 8.0, dur
    assert rms_dbfs(r.content) > -40


def test_same_seed_same_audio(client):
    a = client.post("/synthesize", json={"text": TEXT, "voice": VOICE, "seed": 7}).content
    b = client.post("/synthesize", json={"text": TEXT, "voice": VOICE, "seed": 7}).content
    if DETERMINISTIC:
        assert a == b
    else:
        da, db = _info(a)[2], _info(b)[2]
        assert abs(da - db) / da <= 0.02, (da, db)


def test_unknown_voice_400(client):
    r = client.post("/synthesize", json={"text": TEXT, "voice": "no-such-voice"})
    assert r.status_code == 400 and "unknown voice" in r.json()["error"]


def test_voices_and_health(client):
    vs = client.get("/voices").json()
    assert any(v["id"] == VOICE for v in vs)
    h = client.get("/health").json()
    assert h["ok"] is True and h["gpu_mem_mb"] >= 0
