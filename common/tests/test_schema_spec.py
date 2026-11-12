"""The schema follows spec §4 (docs/superpowers/specs/2026-11-11-eduvid-design.md)."""
import pytest
from psycopg import errors

# spec §4 "Tables (main columns)"; extra columns are allowed, these must exist
SPEC_COLUMNS = {
    "users": {"name", "email", "password_hash", "role", "subjects"},
    "chapters": {"class", "subject", "ncert_ref", "title", "status"},
    "lessons": {"chapter_id", "position", "title", "objectives", "status"},
    "segments": {"lesson_id", "position", "kind", "title", "current_version_id", "status"},
    "segment_versions": {"segment_id", "n", "script", "visual", "created_by", "parent_version_id", "status",
                         "cost_usd"},
    "renders": {"version_id", "language", "voice", "quality", "status", "duration_s", "narration_key", "words_key",
                "video_key", "sheet_key", "qa_key", "qa_status", "gpu_seconds"},
    "lesson_renders": {"lesson_id", "language", "render_ids", "video_key", "chapter_markers", "status"},
    "comments": {"version_id", "render_id", "user_id", "timecode_s", "text", "status", "resolved_by_version_id"},
    "approvals": {"target_type", "target_id", "user_id", "decision", "note", "created_at"},
    "jobs": {"type", "payload", "status", "priority", "attempts", "worker", "gpu", "started_at", "finished_at",
             "log_key", "error"},
    "glossary": {"subject", "term", "spoken_hinglish", "caption_roman", "spoken_english", "spoken_hindi", "notes"},
    "api_keys": {"name", "hash", "scopes", "rate_limit"},
    "api_usage": {"key_id", "endpoint", "model", "characters", "seconds", "ms", "created_at"},
}


def test_spec_columns_exist(conn):
    rows = conn.execute("SELECT table_name, column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public'").fetchall()
    have: dict[str, set] = {}
    for t, c in rows:
        have.setdefault(t, set()).add(c)
    missing = {t: sorted(cols - have.get(t, set())) for t, cols in SPEC_COLUMNS.items() if cols - have.get(t, set())}
    assert missing == {}


def _chain(cur):
    cur.execute("INSERT INTO chapters (class, subject, slug, title) VALUES (9,'maths','ch-spec','T') RETURNING id")
    ch = cur.fetchone()[0]
    cur.execute("INSERT INTO lessons (chapter_id, position, title) VALUES (%s,1,'L') RETURNING id", (ch,))
    le = cur.fetchone()[0]
    cur.execute("INSERT INTO segments (lesson_id, position, kind) VALUES (%s,1,'scene') RETURNING id", (le,))
    seg = cur.fetchone()[0]
    cur.execute("INSERT INTO segment_versions (segment_id, n) VALUES (%s,1) RETURNING id", (seg,))
    return ch, le, seg, cur.fetchone()[0]


@pytest.mark.parametrize("table,col,good,bad", [
    ("users", "role", ["admin", "teacher"], "reviewer"),
    ("lessons", "status", ["planned", "scripting", "in_review", "approved", "assembled"], "published"),
    ("segment_versions", "status", ["draft", "script_approved", "approved", "rejected"], "in_review"),
    ("renders", "qa_status", ["pass", "warn", "fail"], "ok"),
    ("comments", "status", ["open", "resolved"], "closed"),
])
def test_spec_enums(conn, table, col, good, bad):
    cur = conn.cursor()
    ch, le, seg, v = _chain(cur)
    insert = {
        "users": ("INSERT INTO users (email, role) VALUES (%s, %s)", lambda val, k: (f"u{k}@x.test", val)),
        "lessons": ("INSERT INTO lessons (chapter_id, position, title, status) VALUES (%s, %s, 'x', %s)",
                    lambda val, k: (ch, 10 + k, val)),
        "segment_versions": ("INSERT INTO segment_versions (segment_id, n, status) VALUES (%s, %s, %s)",
                             lambda val, k: (seg, 10 + k, val)),
        "renders": ("INSERT INTO renders (version_id, language, quality, qa_status) VALUES (%s, %s, %s, %s)",
                    lambda val, k: (v, ["hinglish", "english", "hindi"][k % 3], ["draft", "final"][k // 3], val)),
        "comments": ("INSERT INTO comments (version_id, text, status) VALUES (%s, 'x', %s)", lambda val, k: (v, val)),
    }[table]
    for k, val in enumerate(good):
        cur.execute(insert[0], insert[1](val, k))
    with pytest.raises(errors.CheckViolation):
        cur.execute(insert[0], insert[1](bad, 5))


def test_segment_current_version_and_parent(conn):
    cur = conn.cursor()
    _, _, seg, v1 = _chain(cur)
    cur.execute("INSERT INTO segment_versions (segment_id, n, parent_version_id) VALUES (%s,2,%s) RETURNING id",
                (seg, v1))
    v2 = cur.fetchone()[0]
    cur.execute("UPDATE segments SET current_version_id = %s WHERE id = %s", (v2, seg))
    assert cur.execute("SELECT current_version_id FROM segments WHERE id = %s", (seg,)).fetchone()[0] == v2


def test_approval_targets_checked(conn):
    conn.execute("INSERT INTO approvals (target_type, target_id, decision) VALUES ('segment_version', 1, 'approved')")
    with pytest.raises(errors.CheckViolation):
        conn.execute("INSERT INTO approvals (target_type, target_id, decision) VALUES ('banana', 1, 'approved')")
