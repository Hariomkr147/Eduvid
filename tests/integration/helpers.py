import time

from eduvid_common.db import pool


def wait_job(job_id: int, timeout_s: float) -> dict:
    """Poll a job until done/failed. Returns its row as a dict; raises TimeoutError."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        with pool().connection() as conn:
            row = conn.execute("SELECT status, error, result, log_key, attempts FROM jobs WHERE id=%s",
                               (job_id,)).fetchone()
        status, error, result, log_key, attempts = row
        if status in ("done", "failed"):
            return {"status": status, "error": error, "result": result, "log_key": log_key, "attempts": attempts,
                    "seconds": round(time.monotonic() - t0, 1)}
        time.sleep(2)
    raise TimeoutError(f"job {job_id} not finished after {timeout_s}s")
