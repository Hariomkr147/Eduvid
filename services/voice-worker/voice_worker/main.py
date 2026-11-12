"""voice-worker: claims `voice` and `words` jobs and runs them through the speech gateway.

Payloads:
  voice: {render_id, script_key, language, voice: "<model>:<voice id>", out_prefix}
  words: {render_id, out_prefix, language}
Writes narration.wav, lines.json, takes.json, script.json (the snapshot used), then words.json, under out_prefix.
"""
import json
import logging
import os
import socket
import threading
import time
import traceback

import httpx
from psycopg.types.json import Jsonb

from eduvid_common import jobs
from eduvid_common import storage as _storage
from eduvid_common.db import pool
from eduvid_common.settings import get_settings

from .voice import SpeakableError, build_narration
from .words import build_words

log = logging.getLogger("voice-worker")
storage = _storage                     # swapped for an in-memory fake in tests
HEARTBEAT_S = 60
LOCK_S = 900

# Whisper writes Hinglish loanwords in Latin script and numbers as digits without a prompt (docs/tts-benchmark.md).
ASR_PROMPT = {"hi": "यह हिंदी है। सारे शब्द देवनागरी में लिखे हैं, जैसे सिलेंडर, एरिया, वेलोसिटी, टू, थ्री, पाई।",
              "en": "Numbers and symbols are spoken as words: two pi r h, nine point eight metres per second squared."}


def asr_lang(language: str) -> str:
    return "en" if language == "english" else "hi"


class Gateway:
    """The speech gateway, called with the pipeline key (pipeline calls go first in its scheduler)."""

    def __init__(self, base_url: str, key: str, client: httpx.Client | None = None):
        self.base = base_url.rstrip("/")
        self.c = client or httpx.Client(timeout=httpx.Timeout(600, connect=5),
                                        headers={"Authorization": f"Bearer {key}"})

    def _ok(self, r: httpx.Response) -> httpx.Response:
        if r.status_code >= 400:
            raise RuntimeError(f"gateway {r.request.url.path} -> {r.status_code}: {r.text[:300]}")
        return r

    def synth(self, text: str, voice: str, seed: int) -> bytes:
        model, _, vid = voice.partition(":")
        if not vid:
            raise ValueError(f"voice must be '<model>:<voice id>', got {voice!r}")
        return self._ok(self.c.post(f"{self.base}/v1/audio/speech", json={
            "model": model, "input": text, "voice": vid, "seed": seed, "response_format": "wav"})).content

    def transcribe(self, wav: bytes, language: str) -> str:
        lang = asr_lang(language)
        r = self._ok(self.c.post(f"{self.base}/v1/audio/transcriptions", files={"file": ("take.wav", wav, "audio/wav")},
                                 data={"model": "whisper-large-v3", "language": lang, "prompt": ASR_PROMPT[lang]}))
        return r.json()["text"]

    def align(self, wav: bytes, words: list[str], language: str) -> list[dict]:
        r = self._ok(self.c.post(f"{self.base}/v1/audio/align", files={"file": ("sentence.wav", wav, "audio/wav")},
                                 data={"language": asr_lang(language), "words": json.dumps(words, ensure_ascii=False)}))
        return r.json()["words"]


RENDER_COLS = {"status", "voice", "prefix", "takes", "duration_s", "narration_key", "words_key"}


def update_render(render_id: int | None, **cols) -> None:
    if render_id is None or not cols:
        return
    assert set(cols) <= RENDER_COLS, cols
    sets = ", ".join(f"{k} = %({k})s" for k in cols)
    vals = {k: Jsonb(v) if k == "takes" else v for k, v in cols.items()}
    with pool().connection() as conn:
        conn.execute(f"UPDATE renders SET {sets}, updated_at = now() WHERE id = %(rid)s", {**vals, "rid": render_id})


def _prefix(p: str) -> str:
    return p if p.endswith("/") else p + "/"


def handle_voice(job: jobs.Job, speech) -> dict:
    p = job.payload
    out = _prefix(p["out_prefix"])
    script = json.loads(storage.get_bytes(p["script_key"]))
    wav, lines, report = build_narration(script, p["language"], p["voice"], speech.synth, speech.transcribe)
    storage.put_bytes(out + "script.json", json.dumps(script, ensure_ascii=False, indent=1).encode(), "application/json")
    storage.put_bytes(out + "narration.wav", wav, "audio/wav")
    storage.put_bytes(out + "lines.json", json.dumps(lines, ensure_ascii=False, indent=1).encode(), "application/json")
    storage.put_bytes(out + "takes.json", json.dumps(report, ensure_ascii=False, indent=1).encode(), "application/json")
    update_render(p.get("render_id", job.render_id), status="voiced", voice=p["voice"], prefix=out, takes=report,
                  duration_s=lines["duration"], narration_key=out + "narration.wav")
    flagged = [r["group"] for r in report if r["flagged"]]
    return {"duration_s": lines["duration"], "sentences": len(report),
            "retakes": sum(r["takes"] - 1 for r in report), "flagged": flagged}


def handle_words(job: jobs.Job, speech) -> dict:
    p = job.payload
    out = _prefix(p["out_prefix"])
    script = json.loads(storage.get_bytes(out + "script.json"))
    lines = json.loads(storage.get_bytes(out + "lines.json"))
    words, lines2 = build_words(storage.get_bytes(out + "narration.wav"), script, lines, p["language"], speech.align)
    storage.put_bytes(out + "words.json", json.dumps(words, ensure_ascii=False, indent=1).encode(), "application/json")
    storage.put_bytes(out + "lines.json", json.dumps(lines2, ensure_ascii=False, indent=1).encode(), "application/json")
    update_render(p.get("render_id", job.render_id), status="timed", words_key=out + "words.json")
    unmatched = [w["w"] for w in words if not w["matched"]]
    return {"words": len(words), "unmatched": len(unmatched)}


HANDLERS = {"voice": handle_voice, "words": handle_words}


def _beat(job_id: int, stop: threading.Event) -> None:
    while not stop.wait(HEARTBEAT_S):
        try:
            jobs.heartbeat(job_id, LOCK_S)
        except Exception:                                          # a missed beat is not fatal; the lock is 15 min
            log.exception("heartbeat failed for job %s", job_id)


def run_once(worker: str, speech) -> bool:
    """Claim and run one job. Returns False when the queue had nothing for us."""
    job = jobs.claim(list(HANDLERS), worker, None, LOCK_S)
    if job is None:
        return False
    rid = job.payload.get("render_id", job.render_id)
    stop = threading.Event()
    threading.Thread(target=_beat, args=(job.id, stop), daemon=True).start()
    try:
        result = HANDLERS[job.type](job, speech)
        jobs.complete(job.id, result)
        log.info("job %s %s done: %s", job.id, job.type, result)
    except SpeakableError as e:                                    # bad input: retrying won't help
        jobs.fail(job.id, f"{job.type}: {e}", retry=False)
        update_render(rid, status="failed")
        log.warning("job %s %s rejected: %s", job.id, job.type, e)
    except Exception as e:
        tb = traceback.format_exc()
        log_key = None
        try:
            log_key = _prefix(job.payload["out_prefix"]) + f"logs/job-{job.id}.txt"
            storage.put_bytes(log_key, tb.encode(), "text/plain")
        except Exception:
            log_key = None
        state = jobs.fail(job.id, f"{job.type}: {type(e).__name__}: {e}", log_key=log_key)
        if state == "failed":
            update_render(rid, status="failed")
        log.error("job %s %s %s: %s", job.id, job.type, state, e)
    finally:
        stop.set()
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    key = os.environ.get("PIPELINE_API_KEY", "")
    if not key:
        raise SystemExit("PIPELINE_API_KEY is not set (.env)")
    speech = Gateway(get_settings().speech_api_url, key)
    worker = f"voice-{socket.gethostname()}"
    log.info("%s polling for %s", worker, ", ".join(HANDLERS))
    while True:
        try:
            if not run_once(worker, speech):
                time.sleep(2)
        except Exception:                                          # database blip: back off, keep the worker alive
            log.exception("worker loop error")
            time.sleep(10)


if __name__ == "__main__":
    main()
