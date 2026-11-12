"""ASR engine tests (GPU). Fixtures are our own TTS output, mounted at /fixtures (repo tests/fixtures)."""
import io
import json
import os
import subprocess
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from eduvid_common.textmetrics import cer

pytestmark = pytest.mark.gpu
FX = Path(os.environ.get("FIXTURES", "/fixtures"))
# Whisper writes Hinglish loanwords in Latin script and numbers as digits unless prompted (see README).
PROMPT = {"hi": "यह हिंदी है। सारे शब्द देवनागरी में लिखे हैं, जैसे सिलेंडर, एरिया, वेलोसिटी, टू, थ्री, पाई।",
          "en": "Numbers and symbols are spoken as words: two pi r h, nine point eight metres per second squared."}


@pytest.fixture(scope="module")
def client():
    from server import app

    with TestClient(app) as c:
        yield c


def fx(name):
    return (FX / f"{name}.wav").read_bytes(), (FX / f"{name}.txt").read_text().strip()


def dur(wav: bytes) -> float:
    with wave.open(io.BytesIO(wav)) as w:
        return w.getnframes() / w.getframerate()


def convert(wav: bytes, suffix: str, *args: str) -> bytes:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d) / "in.wav", Path(d) / f"out{suffix}"
        src.write_bytes(wav)
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), *args, str(dst)], check=True)
        return dst.read_bytes()


def transcribe(client, data, name, language):
    r = client.post("/transcribe", files={"file": (name, data)}, data={"language": language, "prompt": PROMPT[language]})
    assert r.status_code == 200, r.text
    return r.json()


def test_align_known_hinglish_text(client):
    wav, text = fx("hinglish_female")
    words = text.split()
    r = client.post("/align", files={"file": ("a.wav", wav)},
                    data={"words": json.dumps(words, ensure_ascii=False), "language": "hi"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["method"] in {"wav2vec2", "mms"}
    out = body["words"]
    assert [w["word"] for w in out] == words
    d = dur(wav)
    prev = 0.0
    for w in out:
        assert w["start"] < w["end"], w
        assert w["start"] >= prev - 1e-6
        assert 0 <= w["start"] and w["end"] <= d + 1e-3
        prev = w["start"]


def test_transcribe_hinglish_cer(client):
    wav, text = fx("hinglish_female")
    res = transcribe(client, wav, "a.wav", "hi")
    assert cer(text, res["text"]) < 0.12, res["text"]


def test_transcribe_english_words_have_times(client):
    wav, text = fx("english_michael")
    res = transcribe(client, wav, "a.wav", "en")
    assert cer(text, res["text"]) < 0.12, res["text"]
    words = [w for s in res["segments"] for w in s["words"]]
    assert len(words) >= 8
    assert all(w["start"] is not None and w["end"] is not None and w["start"] <= w["end"] for w in words)


def test_odd_formats_normalised(client):
    wav, text = fx("hinglish_female")
    base = cer(text, transcribe(client, wav, "a.wav", "hi")["text"])
    mp3 = convert(wav, ".mp3", "-ar", "48000", "-ac", "2")
    m4a = convert(wav, ".m4a", "-c:a", "aac")
    for name, data in (("a.mp3", mp3), ("a.m4a", m4a)):
        c = cer(text, transcribe(client, data, name, "hi")["text"])
        assert c <= base + 0.03, (name, c, base)


def test_empty_or_corrupt_400(client):
    for data in (b"", os.urandom(4096)):
        r = client.post("/transcribe", files={"file": ("x.wav", data)}, data={"language": "hi"})
        assert r.status_code == 400 and r.json() == {"error": "could not decode audio"}
        r = client.post("/align", files={"file": ("x.wav", data)}, data={"words": '["a"]', "language": "hi"})
        assert r.status_code == 400 and r.json() == {"error": "could not decode audio"}


def test_mms_fallback_for_language_without_aligner(client):
    wav, text = fx("hinglish_female")
    r = client.post("/align", files={"file": ("a.wav", wav)},
                    data={"words": json.dumps(text.split(), ensure_ascii=False), "language": "xx"})
    assert r.status_code == 200, r.text
    assert r.json()["method"] == "mms"
    assert len(r.json()["words"]) == len(text.split())


def test_health(client):
    h = client.get("/health").json()
    assert h["ok"] is True and "hi" in h["aligners"] and "en" in h["aligners"]


def test_fatal_cuda_error_exits_for_restart_and_health_goes_red(client, monkeypatch):
    # Review Focus 4: a sticky CUDA error must not leave a "healthy" engine that fails every call.
    import server

    exits = []
    monkeypatch.setattr(server, "_exit_for_restart", lambda: exits.append(1))
    monkeypatch.setitem(server.state, "broken", None)

    def boom(*a, **k):
        raise RuntimeError("CUDA error: an illegal memory access was encountered")

    monkeypatch.setattr(server, "transcribe", boom)
    r = client.post("/transcribe", files={"file": ("a.wav", fx("english_michael")[0], "audio/wav")},
                    data={"language": "en"})
    assert r.status_code == 500 and r.json()["error"] == "engine crashed"
    import time
    time.sleep(0.5)
    assert exits == [1]
    assert client.get("/health").json()["ok"] is False


def test_oom_frees_cache_and_stays_up(client, monkeypatch):
    import server

    exits = []
    monkeypatch.setattr(server, "_exit_for_restart", lambda: exits.append(1))
    monkeypatch.setitem(server.state, "broken", None)

    def oom(*a, **k):
        raise torch.cuda.OutOfMemoryError("CUDA out of memory. Tried to allocate 2.00 GiB")

    import torch
    monkeypatch.setattr(server, "do_align", oom)
    r = client.post("/align", files={"file": ("a.wav", fx("english_michael")[0], "audio/wav")},
                    data={"words": json.dumps(["the"]), "language": "en"})
    assert r.status_code == 500 and r.json()["error"] == "out of memory"
    assert exits == [] and client.get("/health").json()["ok"] is True
