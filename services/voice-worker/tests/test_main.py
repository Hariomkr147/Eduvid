"""Job loop with jobs/storage/db replaced by in-memory fakes (no Postgres or MinIO needed)."""
import json

import pytest

from eduvid_common.jobs import Job
from tests.conftest import FakeSpeech
from voice_worker import main


class Store(dict):
    def put_bytes(self, key, data, content_type):
        self[key] = data

    def get_bytes(self, key):
        return self[key]


@pytest.fixture
def env(monkeypatch):
    store, calls, updates = Store(), {"complete": [], "fail": []}, []
    monkeypatch.setattr(main, "storage", store)
    monkeypatch.setattr(main.jobs, "complete", lambda jid, result=None: calls["complete"].append((jid, result)))
    monkeypatch.setattr(main.jobs, "fail",
                        lambda jid, error, log_key=None, retry=True: calls["fail"].append((jid, error, log_key, retry)))
    monkeypatch.setattr(main.jobs, "heartbeat", lambda jid, lock_s=900: None)
    monkeypatch.setattr(main, "update_render", lambda rid, **cols: updates.append((rid, cols)))
    return store, calls, updates


def put_script(store, lines):
    store["in/script.json"] = json.dumps({"lines": lines}, ensure_ascii=False).encode()


def voice_job(**kw):
    return Job(id=7, type="voice", attempts=1, priority=100, render_id=3, payload={
        "render_id": 3, "script_key": "in/script.json", "language": "hinglish",
        "voice": "omnivoice:hinglish-female", "out_prefix": "out/", **kw})


def test_speakable_violation_fails_job_without_retry(env, monkeypatch):
    store, calls, updates = env
    put_script(store, [{"say": "अब cone देखो।"}])
    sp = FakeSpeech()
    monkeypatch.setattr(main.jobs, "claim", lambda *a, **k: voice_job())
    assert main.run_once("w1", sp) is True
    assert sp.synth_calls == []
    assert calls["complete"] == []
    (jid, error, _, retry), = calls["fail"]
    assert jid == 7 and retry is False and "line 0" in error
    assert updates[-1] == (3, {"status": "failed"})


def test_voice_then_words_uploads_and_updates_render(env, monkeypatch):
    store, calls, updates = env
    put_script(store, [{"say": "सिलेंडर का एरिया,"}, {"say": "टू पाई आर एच होता है।"}])
    sp = FakeSpeech()
    monkeypatch.setattr(main.jobs, "claim", lambda *a, **k: voice_job())
    main.run_once("w1", sp)
    assert {"out/narration.wav", "out/lines.json", "out/takes.json", "out/script.json"} <= set(store)
    rid, cols = updates[-1]
    assert rid == 3 and cols["status"] == "voiced" and cols["voice"] == "omnivoice:hinglish-female"
    assert cols["prefix"] == "out/" and cols["duration_s"] > 1 and cols["takes"][0]["takes"] == 1
    assert cols["narration_key"] == "out/narration.wav"

    monkeypatch.setattr(main.jobs, "claim", lambda *a, **k: Job(
        id=8, type="words", attempts=1, priority=100, render_id=3,
        payload={"render_id": 3, "out_prefix": "out/", "language": "hinglish"}))
    main.run_once("w1", sp)
    words = json.loads(store["out/words.json"])
    assert len(words) == 9 and updates[-1] == (3, {"status": "timed", "words_key": "out/words.json"})
    assert [c[0] for c in calls["complete"]] == [7, 8] and calls["fail"] == []


def test_engine_error_fails_with_retry_and_log(env, monkeypatch):
    store, calls, _ = env
    put_script(store, [{"say": "नमस्ते।"}])

    class Down(FakeSpeech):
        def synth(self, *a):
            raise RuntimeError("engine unavailable")

    monkeypatch.setattr(main.jobs, "claim", lambda *a, **k: voice_job())
    main.run_once("w1", Down())
    (jid, error, log_key, retry), = calls["fail"]
    assert retry is True and "engine unavailable" in error
    assert log_key == "out/logs/job-7.txt" and b"Traceback" in store[log_key]


def test_idle_returns_false(env, monkeypatch):
    monkeypatch.setattr(main.jobs, "claim", lambda *a, **k: None)
    assert main.run_once("w1", FakeSpeech()) is False
