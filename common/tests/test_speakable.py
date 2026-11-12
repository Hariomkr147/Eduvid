import pytest

from eduvid_common.speakable import violations


def test_hinglish_flags_latin_and_math():
    v = violations("A = πr²", "hinglish")
    for ch in ("A", "=", "π", "²"):
        assert ch in v


def test_hinglish_clean():
    assert violations("पाई आर स्क्वेयर्ड", "hinglish") == []


def test_hindi_flags_digits_ascii_and_devanagari():
    v = violations("कुल 2 और ३ भाग", "hindi")
    assert "2" in v and "३" in v


def test_english_flags_math_symbols():
    v = violations("v = u + at", "english")
    assert "=" in v and "+" in v


def test_english_clean():
    assert violations("v equals u plus a t", "english") == []


def test_english_flags_super_and_subscripts():
    v = violations("x² plus v₀", "english")
    assert "²" in v and "₀" in v


def test_english_allows_digits_and_letters():
    assert violations("Area is 25 square metres", "english") == []


def test_unknown_language():
    with pytest.raises(ValueError):
        violations("x", "french")


def test_each_violation_reported_once():
    assert violations("a + b + c", "english") == ["+"]


def test_glossary_lookup(pg_url):
    from eduvid_common.speakable import lookup

    g = lookup("Cylinder", "maths")
    assert g["hindi_term"] == "बेलन"
    assert g["spoken_hinglish"] == "सिलेंडर"
    assert lookup("बेलन", "maths")["term"] == "cylinder"
    assert lookup("no such term", "maths") is None


def test_glossary_seed_is_speakable(conn):
    rows = conn.execute("SELECT term, spoken_hinglish, spoken_hindi, spoken_english FROM glossary").fetchall()
    assert len(rows) >= 30
    for term, hs, hi, en in rows:
        assert violations(hs, "hinglish") == [], term
        assert violations(hi, "hindi") == [], term
        assert violations(en, "english") == [], term
