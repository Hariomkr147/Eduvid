"""Live: voice -> words for area-volume through the real gateway and engines (needs voice-worker running)."""
import json

import pytest

from eduvid_common import jobs, storage
from eduvid_common.db import pool
from tests.integration.helpers import wait_job
from tests.integration.seed import seed

pytestmark = pytest.mark.gpu
VOICE = "omnivoice:hinglish-female"        # the area-volume video's own voice (female Hinglish)


def longest_unmatched_run(words):
    best = cur = 0
    for w in words:
        cur = 0 if w["matched"] else cur + 1
        best = max(best, cur)
    return best


def test_voice_then_words():
    s = seed()
    v = jobs.enqueue("voice", {"render_id": s["render_id"], "script_key": s["script_key"], "language": "hinglish",
                               "voice": VOICE, "out_prefix": s["out_prefix"]}, render_id=s["render_id"])
    rv = wait_job(v, 900)
    assert rv["status"] == "done", rv
    w = jobs.enqueue("words", {"render_id": s["render_id"], "out_prefix": s["out_prefix"], "language": "hinglish"},
                     render_id=s["render_id"])
    rw = wait_job(w, 600)
    assert rw["status"] == "done", rw

    words = json.loads(storage.get_bytes(s["out_prefix"] + "words.json"))
    lines = json.loads(storage.get_bytes(s["out_prefix"] + "lines.json"))
    takes = json.loads(storage.get_bytes(s["out_prefix"] + "takes.json"))
    print(f"\nvoice {rv['seconds']}s {rv['result']} | words {rw['seconds']}s {rw['result']}")
    print("takes:", [(t["group"], t["takes"], t["best_cer"], t["flagged"]) for t in takes])
    assert 130 <= len(words) <= 150
    assert longest_unmatched_run(words) <= 3
    assert all(a["s"] <= b["s"] for a, b in zip(words, words[1:]))
    assert lines["voice"] == VOICE and abs(lines["duration"] - lines["lines"][-1]["end"]) < 2
    with pool().connection() as conn:
        status, voice, nk, wk = conn.execute("SELECT status, voice, narration_key, words_key FROM renders WHERE id=%s",
                                             (s["render_id"],)).fetchone()
    assert (status, voice) == ("timed", VOICE) and nk.endswith("narration.wav") and wk.endswith("words.json")
