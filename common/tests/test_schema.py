import psycopg
import pytest
from psycopg import errors

TABLES = {
    "users", "chapters", "lessons", "segments", "segment_versions", "renders", "lesson_renders",
    "comments", "approvals", "jobs", "glossary", "api_keys", "api_usage", "schema_migrations",
}


def _seg_version(cur) -> int:
    cur.execute(
        "INSERT INTO chapters (class, subject, slug, title) VALUES (9,'maths','ch-test','Test') RETURNING id"
    )
    ch = cur.fetchone()[0]
    cur.execute("INSERT INTO lessons (chapter_id, position, title) VALUES (%s,1,'L') RETURNING id", (ch,))
    le = cur.fetchone()[0]
    cur.execute("INSERT INTO segments (lesson_id, position, kind) VALUES (%s,1,'scene') RETURNING id", (le,))
    seg = cur.fetchone()[0]
    cur.execute("INSERT INTO segment_versions (segment_id, n) VALUES (%s,1) RETURNING id", (seg,))
    return cur.fetchone()[0]


def test_all_tables_exist(conn):
    cur = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    assert TABLES <= {r[0] for r in cur.fetchall()}


def test_every_table_has_id_and_created_at(conn):
    cur = conn.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND column_name IN ('id','created_at')"
    )
    have: dict[str, set] = {}
    for t, c in cur.fetchall():
        have.setdefault(t, set()).add(c)
    for t in TABLES:
        assert have.get(t) == {"id", "created_at"}, t


def test_segment_kind_check(conn):
    cur = conn.cursor()
    _seg_version(cur)
    cur.execute("SELECT id FROM lessons ORDER BY id DESC LIMIT 1")
    le = cur.fetchone()[0]
    with pytest.raises(errors.CheckViolation):
        cur.execute("INSERT INTO segments (lesson_id, position, kind) VALUES (%s,2,'video')", (le,))


def test_render_unique_per_version_language_quality(conn):
    cur = conn.cursor()
    v = _seg_version(cur)
    cur.execute("INSERT INTO renders (version_id, language, quality) VALUES (%s,'hinglish','draft')", (v,))
    with pytest.raises(errors.UniqueViolation):
        cur.execute("INSERT INTO renders (version_id, language, quality) VALUES (%s,'hinglish','draft')", (v,))


def test_job_enums_checked(conn):
    with pytest.raises(errors.CheckViolation):
        conn.execute("INSERT INTO jobs (type, payload) VALUES ('dance', '{}')")


def test_connect_helper(pg_url):
    from eduvid_common.db import connect

    with connect() as c:
        assert isinstance(c, psycopg.Connection)
        assert c.autocommit is False
        assert c.execute("SELECT 1").fetchone()[0] == 1
