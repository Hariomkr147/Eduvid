"""Seed the area-volume pilot segment: catalog rows + the script (new say/caps format) in MinIO.

The engine's script.json lines are already the spoken Devanagari form except for the Latin word "cone";
`say` spells it कोन (as the glossary does), `caps` stays the Roman caption.
"""
import json
from pathlib import Path

from eduvid_common import storage
from eduvid_common.db import pool
from eduvid_common.keys import segment_prefix

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "engine/videos/area-volume"
CLS, SUBJECT, CHAPTER, LESSON, SEG = 9, "maths", "ch11-surface-areas", 1, 1
SAY_FIXES = {"cone": "कोन"}


def to_say(text: str) -> str:
    return " ".join(SAY_FIXES.get(w.lower(), w) for w in text.split())


def convert_script() -> dict:
    src = json.loads((PROJECT / "script.json").read_text(encoding="utf-8"))
    out = {k: v for k, v in src.items() if k != "lines"}       # title, music, lead/gap/outro, sources, …
    out["lines"] = [{"text": ln["text"], "say": to_say(ln["text"]), "caps": ln.get("caps", ""),
                     **{k: ln[k] for k in ("break", "gap") if k in ln}} for ln in src["lines"]]
    return out


def seed(language: str = "hinglish", quality: str = "draft", version: int = 1) -> dict:
    """Idempotent. Returns {render_id, version_id, script_key, out_prefix}."""
    script = convert_script()
    out_prefix = segment_prefix(CLS, SUBJECT, CHAPTER, LESSON, SEG, version, language)
    script_key = out_prefix + "script.json"
    storage.put_bytes(script_key, json.dumps(script, ensure_ascii=False, indent=1).encode(), "application/json")
    with pool().connection() as conn:
        ch = conn.execute(
            "INSERT INTO chapters (class, subject, slug, title, ncert_ref) VALUES (%s,%s,%s,%s,%s) "
            "ON CONFLICT DO NOTHING RETURNING id",
            (CLS, SUBJECT, CHAPTER, "Surface Areas and Volumes", "NCERT Mathematics Class 9, Chapter 11")).fetchone()
        ch = ch[0] if ch else conn.execute("SELECT id FROM chapters WHERE class=%s AND subject=%s AND slug=%s",
                                           (CLS, SUBJECT, CHAPTER)).fetchone()[0]
        le = conn.execute("SELECT id FROM lessons WHERE chapter_id=%s AND position=%s", (ch, LESSON)).fetchone()
        le = le[0] if le else conn.execute(
            "INSERT INTO lessons (chapter_id, position, title) VALUES (%s,%s,%s) RETURNING id",
            (ch, LESSON, "Cylinder and cone")).fetchone()[0]
        sg = conn.execute("SELECT id FROM segments WHERE lesson_id=%s AND position=%s", (le, SEG)).fetchone()
        sg = sg[0] if sg else conn.execute(
            "INSERT INTO segments (lesson_id, position, kind, title) VALUES (%s,%s,'scene',%s) RETURNING id",
            (le, SEG, "Why 2πrh")).fetchone()[0]
        v = conn.execute("SELECT id FROM segment_versions WHERE segment_id=%s AND n=%s", (sg, version)).fetchone()
        from psycopg.types.json import Jsonb
        v = v[0] if v else conn.execute(
            "INSERT INTO segment_versions (segment_id, n, script) VALUES (%s,%s,%s) RETURNING id",
            (sg, version, Jsonb(script))).fetchone()[0]
        conn.execute("UPDATE segments SET current_version_id=%s WHERE id=%s", (v, sg))
        r = conn.execute(
            "INSERT INTO renders (version_id, language, quality) VALUES (%s,%s,%s) "
            "ON CONFLICT (version_id, language, quality) DO UPDATE SET status='pending', updated_at=now() "
            "RETURNING id", (v, language, quality)).fetchone()[0]
    return {"render_id": r, "version_id": v, "script_key": script_key, "out_prefix": out_prefix}


SHARED_TOOLS = ROOT / "engine/shared/tools"
PROJECT_SKIP = {"data", "renders", "review", "kaggle_out"}


def upload_project(version: int = 1) -> str:
    """tar.gz of the area-volume project (code, fonts, vendor, the converted script.json; shared tools; no data/).
    Returns its key: …/seg-01/v{n}/project.tar.gz (shared by every language of the version)."""
    import io
    import tarfile

    buf = io.BytesIO()
    script = json.dumps(convert_script(), ensure_ascii=False, indent=1).encode()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for p in sorted(PROJECT.iterdir()):
            if p.name in PROJECT_SKIP or p.name == "script.json" or p.name == "tools":
                continue
            t.add(p, arcname=p.name)
        for p in sorted(SHARED_TOOLS.iterdir()):
            t.add(p, arcname=f"tools/{p.name}")
        info = tarfile.TarInfo("script.json")
        info.size = len(script)
        t.addfile(info, io.BytesIO(script))
    key = segment_prefix(CLS, SUBJECT, CHAPTER, LESSON, SEG, version, "hinglish").rsplit("/hinglish/", 1)[0] \
        + "/project.tar.gz"
    storage.put_bytes(key, buf.getvalue(), "application/gzip")
    return key
