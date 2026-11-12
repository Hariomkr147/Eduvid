"""Checks that 'say' text can be read aloud as written, plus glossary lookup.

Hinglish / Hindi speakable text: Devanagari words only, no Latin letters, digits or math symbols.
English speakable text: no math symbols and no super/subscript characters.
"""
import unicodedata

MATH_SYMBOLS = set("=+−×÷/^²³√π∑∫<>%°")
LANGUAGES = ("hinglish", "hindi", "english")


def _is_super_or_subscript(ch: str) -> bool:
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return False
    return "SUPERSCRIPT" in name or "SUBSCRIPT" in name


def _is_latin_letter(ch: str) -> bool:
    if not unicodedata.category(ch).startswith("L"):
        return False
    try:
        return unicodedata.name(ch).startswith("LATIN")
    except ValueError:
        return False


def violations(text: str, language: str) -> list[str]:
    """Characters in text that can't be spoken as written, each listed once, in order of appearance."""
    if language not in LANGUAGES:
        raise ValueError(f"unknown language {language!r}")
    text = unicodedata.normalize("NFC", text)
    found: list[str] = []
    for ch in text:
        if ch in found:
            continue
        bad = ch in MATH_SYMBOLS or _is_super_or_subscript(ch)
        if language in ("hinglish", "hindi"):
            bad = bad or _is_latin_letter(ch) or unicodedata.category(ch) == "Nd"
        if bad:
            found.append(ch)
    return found


def lookup(term: str, subject: str) -> dict | None:
    """Find a glossary row by English term, Hindi term or Hinglish spoken form (case-insensitive)."""
    from psycopg.rows import dict_row

    from .db import pool

    t = unicodedata.normalize("NFC", term.strip())
    with pool().connection() as conn:
        return conn.cursor(row_factory=dict_row).execute(
            "SELECT * FROM glossary WHERE subject = %s "
            "AND (lower(term) = lower(%s) OR hindi_term = %s OR spoken_hinglish = %s) "
            "ORDER BY id LIMIT 1",
            (subject, t, t, t),
        ).fetchone()
