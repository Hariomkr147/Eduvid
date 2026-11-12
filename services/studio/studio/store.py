"""studio_videos / studio_events access."""
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from eduvid_common.db import pool

JSON_COLS = {"target", "settings", "script", "stage", "variants"}
COLS = JSON_COLS | {"title", "model", "status", "compare_id", "duration_s", "error"}


def _row(r: dict | None) -> dict | None:
    if r is None:
        return None
    r = dict(r)
    r["id"] = str(r["id"])
    if r.get("compare_id"):
        r["compare_id"] = str(r["compare_id"])
    r["cost_usd"] = float(r.get("cost_usd") or 0)
    for k in ("created_at", "updated_at"):
        if r.get(k):
            r[k] = r[k].isoformat()
    return r


def create(**cols) -> dict:
    assert set(cols) <= COLS, cols
    names = ", ".join(cols)
    vals = ", ".join(f"%({k})s" for k in cols)
    params = {k: Jsonb(v) if k in JSON_COLS else v for k, v in cols.items()}
    with pool().connection() as conn:
        r = conn.cursor(row_factory=dict_row).execute(
            f"INSERT INTO studio_videos ({names}) VALUES ({vals}) RETURNING *", params).fetchone()
    return _row(r)


def get(vid: str) -> dict | None:
    with pool().connection() as conn:
        r = conn.cursor(row_factory=dict_row).execute("SELECT * FROM studio_videos WHERE id = %s", (vid,)).fetchone()
    return _row(r)


def update(vid: str, **cols) -> None:
    assert set(cols) <= COLS, cols
    sets = ", ".join(f"{k} = %({k})s" for k in cols)
    params = {k: Jsonb(v) if k in JSON_COLS else v for k, v in cols.items()}
    with pool().connection() as conn:
        conn.execute(f"UPDATE studio_videos SET {sets}, updated_at = now() WHERE id = %(vid)s", {**params, "vid": vid})


def add_cost(vid: str, usd: float) -> float:
    with pool().connection() as conn:
        r = conn.execute("UPDATE studio_videos SET cost_usd = cost_usd + %s, updated_at = now() WHERE id = %s "
                         "RETURNING cost_usd", (round(usd, 4), vid)).fetchone()
    return float(r[0]) if r else 0.0


def merge_stage(vid: str, **kv) -> None:
    with pool().connection() as conn:
        conn.execute("UPDATE studio_videos SET stage = stage || %s, updated_at = now() WHERE id = %s", (Jsonb(kv), vid))


def listing(limit: int = 200) -> list[dict]:
    with pool().connection() as conn:
        rows = conn.cursor(row_factory=dict_row).execute(
            "SELECT id, created_at, updated_at, title, target, settings, model, status, variants, compare_id, "
            "cost_usd, duration_s, error FROM studio_videos ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall()
    return [_row(r) for r in rows]


def active(statuses: tuple[str, ...]) -> list[dict]:
    with pool().connection() as conn:
        rows = conn.cursor(row_factory=dict_row).execute(
            "SELECT * FROM studio_videos WHERE status = ANY(%s)", (list(statuses),)).fetchall()
    return [_row(r) for r in rows]


def delete(vid: str) -> None:
    with pool().connection() as conn:
        conn.execute("DELETE FROM studio_videos WHERE id = %s", (vid,))


def event(vid: str, step: str, status: str, message: str = "") -> None:
    with pool().connection() as conn:
        conn.execute("INSERT INTO studio_events (video_id, step, status, message) VALUES (%s, %s, %s, %s)",
                     (vid, step, status, message[:4000]))


def events(vid: str, after: int = 0) -> list[dict]:
    with pool().connection() as conn:
        rows = conn.cursor(row_factory=dict_row).execute(
            "SELECT id, ts, step, status, message FROM studio_events WHERE video_id = %s AND id > %s ORDER BY id",
            (vid, after)).fetchall()
    return [{**r, "ts": r["ts"].isoformat()} for r in rows]


def job(job_id: int) -> dict | None:
    with pool().connection() as conn:
        return conn.cursor(row_factory=dict_row).execute(
            "SELECT id, type, status, result, error, attempts, log_key FROM jobs WHERE id = %s", (job_id,)).fetchone()


def glossary(subject: str) -> list[dict]:
    s = subject.lower()
    subj = "maths" if s.startswith("math") else "science" if s in ("science", "physics", "chemistry", "biology") else s
    with pool().connection() as conn:   # columns as renamed by migration 0003; aliased to the names prompts.py uses
        return conn.cursor(row_factory=dict_row).execute(
            "SELECT term AS term_en, hindi_term, spoken_hinglish AS hinglish_say, spoken_hindi AS hindi_say, "
            "caption_roman AS caption FROM glossary WHERE subject = %s ORDER BY term", (subj,)).fetchall()
