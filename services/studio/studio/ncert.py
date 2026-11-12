"""NCERT content from the GyanSetu database (read-only): books → chapters → sections → teaching units.

Every connection is opened read-only (default_transaction_read_only), so nothing here can write to it.
"""
import os
import re
import threading
import time

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None
_lock = threading.Lock()
_cache: dict[str, tuple[float, object]] = {}
CACHE_S = 600
MAX_CONTEXT = 14000     # characters of teaching-unit context per unit sent to the LLM


def _configure(conn: psycopg.Connection) -> None:
    conn.execute("SET default_transaction_read_only = on")
    conn.commit()


def pool() -> ConnectionPool:
    global _pool
    with _lock:
        if _pool is None:
            url = os.environ.get("NCERT_DATABASE_URL", "")
            if not url:
                raise RuntimeError("NCERT_DATABASE_URL is not set")
            _pool = ConnectionPool(url, min_size=0, max_size=4, open=True, configure=_configure,
                                   kwargs={"connect_timeout": 10, "row_factory": dict_row})
        return _pool


def _q(sql: str, params: tuple = (), cache_key: str | None = None):
    if cache_key and cache_key in _cache and time.monotonic() - _cache[cache_key][0] < CACHE_S:
        return _cache[cache_key][1]
    with pool().connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    rows = [{k: (str(v) if k.endswith("id") and v is not None else v) for k, v in r.items()} for r in rows]
    if cache_key:
        _cache[cache_key] = (time.monotonic(), rows)
    return rows


def _title(s: str | None) -> str:
    """'Heron S Formula' → "Heron's Formula" (the source titles lost their apostrophes)."""
    s = (s or "").strip()
    return re.sub(r"\b(\w+) S\b", r"\1's", s)


def books() -> list[dict]:
    rows = _q("""SELECT b.id, b.title, b.subject, b.grade, b.board,
                        (SELECT count(*) FROM agents_schema.chapters c WHERE c.book_id = b.id) AS chapters
                   FROM agents_schema.books b ORDER BY b.grade, b.subject, b.title""", cache_key="books")
    return [r for r in rows if r["chapters"]]


def chapters(book_id: str) -> list[dict]:
    rows = _q("""SELECT c.id, c.chapter_number AS number, c.title,
                        (SELECT count(*) FROM agents_schema.sections s WHERE s.chapter_id = c.id) AS sections,
                        (SELECT count(*) FROM agents_schema.teaching_units t WHERE t.chapter_id = c.id) AS units
                   FROM agents_schema.chapters c WHERE c.book_id = %s ORDER BY c.chapter_number""",
              (book_id,), cache_key=f"ch:{book_id}")
    return [{**r, "title": _title(r["title"])} for r in rows]


def sections(chapter_id: str) -> list[dict]:
    secs = _q("""SELECT s.id, s.section_id AS code, s.section_name AS name, s.sequence
                   FROM agents_schema.sections s WHERE s.chapter_id = %s ORDER BY s.sequence, s.section_id""",
              (chapter_id,), cache_key=f"sec:{chapter_id}")
    units = _q("""SELECT t.id, t.section_db_id AS section_id, t.tu_name AS name, t.sequence, t.bloom_level AS bloom,
                         t.difficulty, left(coalesce(t.description, ''), 300) AS description,
                         length(coalesce(t.assembled_context, '')) AS context_chars
                    FROM agents_schema.teaching_units t WHERE t.chapter_id = %s ORDER BY t.sequence""",
               (chapter_id,), cache_key=f"tu:{chapter_id}")
    by = {}
    for u in units:
        by.setdefault(u["section_id"], []).append(u)
    return [{**s, "units": by.get(s["id"], [])} for s in secs]


def units(unit_ids: list[str]) -> list[dict]:
    """Full teaching units for grounding, in the order given."""
    if not unit_ids:
        return []
    rows = _q("""SELECT t.id, t.tu_name AS name, t.bloom_level AS bloom, t.difficulty, t.description,
                        t.assembled_context AS context, s.section_id AS section_code, s.section_name,
                        c.title AS chapter, c.chapter_number, b.subject, b.grade, b.title AS book
                   FROM agents_schema.teaching_units t
                   LEFT JOIN agents_schema.sections s ON s.id = t.section_db_id
                   LEFT JOIN agents_schema.chapters c ON c.id = t.chapter_id
                   LEFT JOIN agents_schema.books b ON b.id = c.book_id
                  WHERE t.id = ANY(%s::uuid[])""", (unit_ids,))
    order = {u: i for i, u in enumerate(unit_ids)}
    rows.sort(key=lambda r: order.get(r["id"], 0))
    for r in rows:
        r["chapter"] = _title(r["chapter"])
        r["context"] = clean_context(r.get("context") or "")
    return rows


def clean_context(text: str) -> str:
    """Drop page/bbox image markers and runs of blank lines; cap the length."""
    text = re.sub(r"!\[\]\([^)]*\)", "", text)
    text = re.sub(r"\n\s*\n(\s*\n)+", "\n\n", text)
    return text.strip()[:MAX_CONTEXT]


def preview(unit_id: str) -> dict:
    rows = units([unit_id])
    return rows[0] if rows else {}
