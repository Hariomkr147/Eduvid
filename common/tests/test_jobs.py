import threading
import time

import psycopg
import pytest

from eduvid_common import jobs


@pytest.fixture(autouse=True)
def clean_jobs(pg_url):
    with psycopg.connect(pg_url, autocommit=True) as c:
        c.execute("TRUNCATE jobs RESTART IDENTITY CASCADE")
    yield


def _row(pg_url, job_id):
    with psycopg.connect(pg_url) as c:
        return c.execute(
            "SELECT status, attempts, run_after - now(), error, log_key, locked_until FROM jobs WHERE id=%s",
            (job_id,),
        ).fetchone()


def _make_runnable(pg_url, job_id):
    with psycopg.connect(pg_url, autocommit=True) as c:
        c.execute("UPDATE jobs SET run_after = now() WHERE id=%s", (job_id,))


def test_claim_returns_oldest_highest_priority(pg_url):
    a = jobs.enqueue("render", {"n": 1}, priority=100)
    b = jobs.enqueue("render", {"n": 2}, priority=10)
    c = jobs.enqueue("render", {"n": 3}, priority=10)
    jobs.enqueue("voice", {"n": 4}, priority=1)  # other type, ignored
    got = [jobs.claim(["render"], "w1", gpu=1).id for _ in range(3)]
    assert got == [b, c, a]
    assert jobs.claim(["render"], "w1", gpu=1) is None
    j = _row(pg_url, b)
    assert j[0] == "running" and j[1] == 1


def test_claim_respects_run_after(pg_url):
    from datetime import datetime, timedelta, timezone

    jobs.enqueue("render", {}, run_after=datetime.now(timezone.utc) + timedelta(minutes=5))
    assert jobs.claim(["render"], "w1", gpu=None) is None


def test_claim_payload_roundtrip(pg_url):
    jid = jobs.enqueue("voice", {"render_id": 7, "language": "hinglish"})
    job = jobs.claim(["voice", "words"], "w", gpu=None)
    assert (job.id, job.type, job.payload, job.attempts) == (jid, "voice", {"render_id": 7, "language": "hinglish"}, 1)


def test_two_workers_never_claim_same_job(pg_url):
    ids = {jobs.enqueue("render", {"i": i}) for i in range(20)}
    claimed: list[int] = []
    lock = threading.Lock()

    def worker(name):
        while (j := jobs.claim(["render"], name, gpu=None)) is not None:
            with lock:
                claimed.append(j.id)

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(claimed) == 20
    assert set(claimed) == ids


def test_fail_backoff_then_failed(pg_url):
    jid = jobs.enqueue("render", {})
    jobs.claim(["render"], "w", gpu=None)
    assert jobs.fail(jid, "boom") == "requeued"
    st, att, delay, *_ = _row(pg_url, jid)
    assert st == "queued" and att == 1 and 28 <= delay.total_seconds() <= 31

    _make_runnable(pg_url, jid)
    jobs.claim(["render"], "w", gpu=None)
    assert jobs.fail(jid, "boom") == "requeued"
    st, att, delay, *_ = _row(pg_url, jid)
    assert st == "queued" and att == 2 and 58 <= delay.total_seconds() <= 61

    _make_runnable(pg_url, jid)
    jobs.claim(["render"], "w", gpu=None)
    assert jobs.fail(jid, "boom", log_key="logs/1.txt") == "failed"
    st, att, _, err, log_key, locked = _row(pg_url, jid)
    assert (st, att, err, log_key, locked) == ("failed", 3, "boom", "logs/1.txt", None)


def test_fail_without_retry_is_final(pg_url):
    jid = jobs.enqueue("voice", {})
    jobs.claim(["voice"], "w", gpu=None)
    assert jobs.fail(jid, "bad input", retry=False) == "failed"
    assert _row(pg_url, jid)[0] == "failed"


def test_complete(pg_url):
    jid = jobs.enqueue("render", {})
    jobs.claim(["render"], "w", gpu=None)
    jobs.complete(jid, {"video_key": "x.mp4"})
    with psycopg.connect(pg_url) as c:
        st, res, fin = c.execute("SELECT status, result, finished_at FROM jobs WHERE id=%s", (jid,)).fetchone()
    assert st == "done" and res == {"video_key": "x.mp4"} and fin is not None


def test_expired_lock_is_reclaimed(pg_url):
    jid = jobs.enqueue("render", {})
    assert jobs.claim(["render"], "w1", gpu=1, lock_s=1).id == jid
    assert jobs.claim(["render"], "w2", gpu=2) is None  # still locked
    time.sleep(1.5)
    again = jobs.claim(["render"], "w2", gpu=2)
    assert again.id == jid and again.attempts == 2


def test_heartbeat_extends_lock(pg_url):
    jid = jobs.enqueue("render", {})
    jobs.claim(["render"], "w1", gpu=1, lock_s=1)
    jobs.heartbeat(jid, lock_s=60)
    time.sleep(1.5)
    assert jobs.claim(["render"], "w2", gpu=2) is None


def test_expired_lock_after_max_attempts_fails_instead_of_reclaim(pg_url):
    jid = jobs.enqueue("render", {})
    with psycopg.connect(pg_url, autocommit=True) as c:
        c.execute(
            "UPDATE jobs SET status='running', attempts=3, locked_until=now()-interval '1 s' WHERE id=%s", (jid,)
        )
    assert jobs.claim(["render"], "w", gpu=None) is None
    st, att, _, err, *_ = _row(pg_url, jid)
    assert st == "failed" and att == 3 and "lock expired" in err
