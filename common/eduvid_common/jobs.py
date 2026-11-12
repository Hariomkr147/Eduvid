"""Postgres job queue.

claim() uses FOR UPDATE SKIP LOCKED so concurrent workers never get the same job.
A running job whose lock expired (worker crashed) is claimable again; each claim counts
as an attempt. Max 3 attempts; retry backoff is 30 s * 2^(attempts-1).
"""
from dataclasses import dataclass
from datetime import datetime

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .db import pool

MAX_ATTEMPTS = 3
BACKOFF_BASE_S = 30


@dataclass
class Job:
    id: int
    type: str
    payload: dict
    attempts: int
    priority: int
    render_id: int | None = None


def enqueue(
    type: str,
    payload: dict,
    priority: int = 100,
    run_after: datetime | None = None,
    render_id: int | None = None,
) -> int:
    with pool().connection() as conn:
        row = conn.execute(
            "INSERT INTO jobs (type, payload, priority, run_after, render_id) "
            "VALUES (%s, %s, %s, COALESCE(%s, now()), %s) RETURNING id",
            (type, Jsonb(payload), priority, run_after, render_id),
        ).fetchone()
        return row[0]


_EXPIRE_EXHAUSTED = """
UPDATE jobs
   SET status = 'failed', locked_until = NULL, updated_at = now(), finished_at = now(),
       error = COALESCE(error || E'\\n', '') || 'lock expired after max attempts (worker died?)'
 WHERE status = 'running' AND locked_until < now() AND attempts >= %(max)s AND type = ANY(%(types)s)
"""

_CLAIM = """
UPDATE jobs
   SET status = 'running', attempts = attempts + 1,
       locked_until = now() + make_interval(secs => %(lock_s)s),
       worker = %(worker)s, gpu = %(gpu)s, started_at = now(), updated_at = now()
 WHERE id = (
       SELECT id FROM jobs
        WHERE type = ANY(%(types)s)
          AND (   (status = 'queued' AND run_after <= now())
               OR (status = 'running' AND locked_until < now() AND attempts < %(max)s))
        ORDER BY priority, id
        FOR UPDATE SKIP LOCKED
        LIMIT 1)
RETURNING id, type, payload, attempts, priority, render_id
"""


def claim(types: list[str], worker: str, gpu: int | None, lock_s: int = 900) -> Job | None:
    params = {"types": list(types), "worker": worker, "gpu": gpu, "lock_s": lock_s, "max": MAX_ATTEMPTS}
    with pool().connection() as conn:
        conn.execute(_EXPIRE_EXHAUSTED, params)
        row = conn.cursor(row_factory=dict_row).execute(_CLAIM, params).fetchone()
    return Job(**row) if row else None


def heartbeat(job_id: int, lock_s: int = 900) -> None:
    with pool().connection() as conn:
        conn.execute(
            "UPDATE jobs SET locked_until = now() + make_interval(secs => %s), updated_at = now() "
            "WHERE id = %s AND status = 'running'",
            (lock_s, job_id),
        )


def complete(job_id: int, result: dict | None = None) -> None:
    with pool().connection() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'done', result = %s, locked_until = NULL, error = NULL, "
            "updated_at = now(), finished_at = now() WHERE id = %s",
            (Jsonb(result) if result is not None else None, job_id),
        )


def fail(job_id: int, error: str, log_key: str | None = None, retry: bool = True) -> str:
    """Requeue with backoff if retry and attempts < 3, else mark failed. Returns 'requeued' or 'failed'."""
    with pool().connection() as conn:
        row = conn.execute(
            """
            UPDATE jobs SET
                status = CASE WHEN %(retry)s AND attempts < %(max)s THEN 'queued' ELSE 'failed' END,
                run_after = CASE WHEN %(retry)s AND attempts < %(max)s
                                 THEN now() + make_interval(secs => %(base)s * power(2, attempts - 1))
                                 ELSE run_after END,
                finished_at = CASE WHEN %(retry)s AND attempts < %(max)s THEN NULL ELSE now() END,
                error = %(error)s, log_key = COALESCE(%(log_key)s, log_key),
                locked_until = NULL, updated_at = now()
            WHERE id = %(id)s
            RETURNING status
            """,
            {"retry": retry, "max": MAX_ATTEMPTS, "base": BACKOFF_BASE_S, "error": error,
             "log_key": log_key, "id": job_id},
        ).fetchone()
    if row is None:
        raise LookupError(f"job {job_id} not found")
    return "requeued" if row[0] == "queued" else "failed"
