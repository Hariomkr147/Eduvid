"""Plan 1 (M0–M3) acceptance. Run with infra/acceptance.sh (it also runs the restore test on the host).

ACCEPTANCE_BASE_URL defaults to the public address https://$DOMAIN/speech. Set it to http://speech-api:8000
to run everything except the internet path (e.g. while 443 is closed).
"""
import hashlib
import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path

import httpx
import pytest

from eduvid_common import jobs, storage
from eduvid_common.db import pool
from eduvid_common.textmetrics import cer_spoken
from tests.integration.helpers import wait_job
from tests.integration.seed import seed, upload_project

pytestmark = pytest.mark.gpu
BASE = os.environ.get("ACCEPTANCE_BASE_URL") or f"https://{os.environ['DOMAIN']}/speech"
TEXT = "सिलेंडर का कर्व्ड सरफेस एरिया टू पाई आर एच होता है।"
PROMPT = "यह हिंदी है। सारे शब्द देवनागरी में लिखे हैं, जैसे सिलेंडर, एरिया, वेलोसिटी, टू, थ्री, पाई।"


@pytest.fixture(scope="module")
def outside_key():
    """A normal (non-pipeline) key, like another app would get from manage_keys.py create."""
    key = "ev_" + secrets.token_urlsafe(24)
    with pool().connection() as conn:
        kid = conn.execute("INSERT INTO api_keys (name, prefix, hash, scopes, rate_limit, pipeline) "
                           "VALUES ('acceptance-outside-app', %s, %s, '{tts,stt}', 60, false) RETURNING id",
                           (key[:8], hashlib.sha256(key.encode()).hexdigest())).fetchone()[0]
    yield key, kid
    with pool().connection() as conn:
        conn.execute("UPDATE api_keys SET revoked_at = now() WHERE id = %s", (kid,))


@pytest.fixture(scope="module")
def api(outside_key):
    with httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {outside_key[0]}"},
                      timeout=httpx.Timeout(300, connect=10)) as c:
        yield c


def test_1_health_shows_three_engines(api):
    h = api.get("/health").json()
    assert h["ok"] is True, h
    assert {k for k, v in h["engines"].items() if v["ok"]} >= {"omnivoice", "kokoro", "asr"}


def test_2_outside_key_speech_transcript_align(api):
    r = api.post("/v1/audio/speech", json={"model": "omnivoice", "input": TEXT, "voice": "hinglish-female",
                                           "seed": 1, "response_format": "wav"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav", r.text[:300]
    wav = r.content
    t = api.post("/v1/audio/transcriptions", files={"file": ("a.wav", wav, "audio/wav")},
                 data={"model": "whisper-1", "language": "hi", "prompt": PROMPT})
    assert t.status_code == 200, t.text[:300]
    c = cer_spoken(TEXT, t.json()["text"])
    assert c < 0.12, (c, t.json()["text"])
    a = api.post("/v1/audio/align", files={"file": ("a.wav", wav, "audio/wav")},
                 data={"language": "hi", "text": TEXT})
    assert a.status_code == 200, a.text[:300]
    words = a.json()["words"]
    assert [w["word"] for w in words] == TEXT.split()
    assert all(0 <= w["start"] <= w["end"] for w in words)
    assert all(x["start"] <= y["start"] for x, y in zip(words, words[1:]))


def test_3_voice_words_render_chain():
    s = seed(version=2)
    d = seed(version=2, quality="draft")
    v = jobs.enqueue("voice", {"render_id": d["render_id"], "script_key": s["script_key"], "language": "hinglish",
                               "voice": "omnivoice:hinglish-female", "out_prefix": s["out_prefix"]},
                     render_id=d["render_id"])
    assert wait_job(v, 900)["status"] == "done"
    w = jobs.enqueue("words", {"render_id": d["render_id"], "out_prefix": s["out_prefix"], "language": "hinglish"},
                     render_id=d["render_id"])
    assert wait_job(w, 600)["status"] == "done"
    r = jobs.enqueue("render", {"render_id": d["render_id"], "project_key": upload_project(version=2),
                                "data_prefix": s["out_prefix"], "quality": "draft", "out_prefix": s["out_prefix"]},
                     render_id=d["render_id"])
    rr = wait_job(r, 900)
    assert rr["status"] == "done", rr
    with pool().connection() as conn:
        status, video_key, renderer = conn.execute(
            "SELECT status, video_key, webgl_renderer FROM renders WHERE id = %s", (d["render_id"],)).fetchone()
    assert status == "done" and "NVIDIA" in renderer
    with tempfile.TemporaryDirectory() as tmp:
        mp4 = storage.get_file(video_key, Path(tmp) / "draft.mp4")
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                    str(mp4)], capture_output=True, text=True, check=True).stdout)
    lines = json.loads(storage.get_bytes(s["out_prefix"] + "lines.json"))
    assert abs(dur - lines["duration"]) < 0.5


def test_4_usage_logged(outside_key):
    _, kid = outside_key
    with pool().connection() as conn:
        rows = dict(conn.execute("SELECT endpoint, count(*) FROM api_usage WHERE key_id = %s GROUP BY 1",
                                 (kid,)).fetchall())
        pipeline = conn.execute("SELECT count(*) FROM api_usage u JOIN api_keys k ON k.id = u.key_id "
                                "WHERE k.pipeline AND u.created_at > now() - interval '1 hour'").fetchone()[0]
    assert rows.get("/v1/audio/speech", 0) >= 1
    assert rows.get("/v1/audio/transcriptions", 0) >= 1
    assert rows.get("/v1/audio/align", 0) >= 1
    assert pipeline >= 3                                   # the voice-worker's calls in the chain
