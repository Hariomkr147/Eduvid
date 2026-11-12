"""Unit tests for the studio's pure logic (no database, no network)."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from studio import prompts
from studio.pipeline import _chunks, variants_for
from studio.schema import Script, voice_script

FIX = json.loads((Path(__file__).parent / "fixtures" / "cylinder_script.json").read_text())


def test_fixture_is_valid_and_speakable():
    s = Script(**FIX)
    assert [x.id for x in s.scenes] == ["s1", "s2", "s3", "s4", "s5", "s6"]
    assert s.speakable_problems() == []


def test_latin_letters_in_hinglish_say_are_flagged():
    d = json.loads(json.dumps(FIX))
    d["scenes"][1]["lines"][0]["say"] = "इस cylinder की height 5 है।"
    probs = Script(**d).speakable_problems()
    assert len(probs) == 1 and probs[0].startswith("s2 line 0")


def test_check_scene_rules():
    d = json.loads(json.dumps(FIX))
    chk = d["scenes"][4]
    assert Script(**d).scenes[4].lines[0].gap == chk["pause_s"]       # the pause is the gap after the question line
    chk["correct"] = 7
    with pytest.raises(ValidationError):
        Script(**d)
    chk["correct"] = 1
    chk["lines"] = chk["lines"][:1]
    with pytest.raises(ValidationError):
        Script(**d)


def test_anchor_lines_are_clamped():
    d = json.loads(json.dumps(FIX))
    d["scenes"][2]["steps"][0]["line"] = 99
    assert Script(**d).scenes[2].steps[0].line == len(d["scenes"][2]["lines"]) - 1


def test_bi_accepts_plain_strings():
    d = json.loads(json.dumps(FIX))
    d["scenes"][0]["title"] = "Just English"
    t = Script(**d).scenes[0].title
    assert t.en == "Just English" and t.hi == "Just English"


def test_voice_script_flattens_with_scene_breaks():
    s = Script(**FIX)
    vs = voice_script(s)
    assert len(vs["lines"]) == sum(len(x.lines) for x in s.scenes)
    breaks = [i for i, ln in enumerate(vs["lines"]) if ln.get("break")]
    ends, n = [], 0
    for sc in s.scenes:
        n += len(sc.lines)
        ends.append(n - 1)
    assert set(ends) <= set(breaks)
    q = next(ln for ln in vs["lines"] if ln["scene"] == "s5")
    assert q["gap"] == 6 and q["break"]


def test_caption_chunks_pin_to_words():
    words = [{"w": w, "s": float(i), "e": i + 0.8} for i, w in enumerate("a b c d e f".split())]
    out = _chunks("first part | @4 second part", words, 0.0, 6.0)
    assert [c["text"] for c in out] == ["first part", "second part"]
    assert out[1]["s"] == 4.0 and out[0]["e"] == 4.0 and out[1]["e"] == 6.0


def test_caption_chunks_without_words_spread_evenly():
    out = _chunks("one | two", [], 10.0, 14.0)
    assert out[0]["s"] == 10.0 and out[1]["s"] == 12.0


@pytest.mark.parametrize("code,bad", [
    ("A.text('important', 1, 2)", False),
    ("for (let i = 0; i < 10; i++) A.circle(i, i, 3)", False),
    ("while (true) {}", True),
    ("fetch('http://x')", True),
    ("window.location = 'x'", True),
    ("const f = Function('return 1')", True),
    ("x.constructor.constructor('alert(1)')()", True),
])
def test_code_filter(code, bad):
    assert bool(prompts.code_problems(code)) is bad


def test_script_prompt_grounds_in_units():
    units = [{"id": "u1", "name": "Cones", "grade": 9, "subject": "Mathematics", "chapter": "Surface Areas",
              "chapter_number": 11, "section_code": "11.1", "section_name": "Cone", "bloom": "Apply",
              "difficulty": "Medium", "description": "", "context": "UNIQUE-NCERT-TEXT"}]
    msgs = prompts.script_prompt(units, "", {"language": "hinglish", "minutes": 2, "checks": 1}, [])
    user = msgs[1]["content"]
    assert "UNIQUE-NCERT-TEXT" in user and "exactly 1" in user and "Devanagari" in user


def test_variants():
    assert variants_for("both") == ["template", "llm"]
    assert variants_for("llm") == ["llm"]
    assert variants_for("weird") == ["template"]


def test_structure_problems_catch_short_scripts():
    from studio.pipeline import structure_problems
    s = Script(**FIX)
    ok = {"minutes": 1, "kinds": ["title", "concept", "board", "figure", "example", "check", "summary"], "checks": 1}
    assert structure_problems(s, ok) == []
    d = json.loads(json.dumps(FIX)); d["scenes"] = d["scenes"][:1]
    probs = structure_problems(Script(**d), {**ok, "minutes": 3})
    assert any("far too short" in p for p in probs) and any("check scene" in p for p in probs)
    assert any("switched off" in p for p in structure_problems(s, {**ok, "kinds": ["title", "summary"]}))


def test_fix_tex_literals_doubles_single_backslashes_only():
    src = "A.tex('\\frac{1}{2} \\times 2\\pi r', 1, 2); A.tex(\"\\\\pi r^2\", 3, 4); A.text('a\\nb', 0, 0)"
    out = prompts.fix_tex_literals(src)
    assert "A.tex('\\\\frac{1}{2} \\\\times 2\\\\pi r', 1, 2)" in out
    assert "A.tex(\"\\\\pi r^2\", 3, 4)" in out          # already doubled: unchanged
    assert "A.text('a\\nb', 0, 0)" in out                # not a tex call: unchanged
