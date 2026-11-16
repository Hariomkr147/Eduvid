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
    ("// swept surface while rotating\nA.circle(1, 2, 3)", False),
    ("/* fetch nothing */ A.text('turn it while it spins', 1, 2)", False),
    ("A.text(`${window.name}`, 1, 2)", True),                      # template literal: ${…} is code
    ("x['constructor']['constructor']('1')()", True),               # strings still checked for these
    ("A.text('it\\'s fine', 1, 2); while (1) {}", True),
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


def test_shape_colour_words_and_fill_strings_are_accepted():
    from studio.schema import Shape
    s = Shape(type="circle", color="Blue", fill="primary")
    assert s.color == "primary" and s.fill is True
    assert Shape(type="circle", color="red").color == "ink"          # no red in teaching frames
    assert Shape(type="circle", fill="none").fill is False
    assert Shape(type="circle", color="#123456").color == "ink"


CHECK_TXT = """duration 144.52 s
s1      0.00 →  12.87  (12.87 s)  title · llm animation
s2     12.87 →  32.85  (19.98 s)  concept · llm animation
s3     32.85 →  48.27  (15.42 s)  figure · TEMPLATE FALLBACK: Failed to execute 'arc': The radius provided (-2.2e-15) is negative. (t=4.92)
s4     48.27 →  81.79  (33.51 s)  board
s5     81.79 →  99.00  (17.21 s)  check
captions:
    0.07–1.35   Cone kya hai?"""

REPORT_SCRIPT = {"scenes": [{"id": f"s{i}", "kind": k, "title": {"en": t}} for i, (k, t) in enumerate(
    [("title", "Meet the Cone"), ("concept", "How a Cone Is Made"), ("figure", "Parts of a Cone"),
     ("board", "Deriving the Surface Area"), ("check", "Try it")], start=1)]}


def test_llm_report_names_every_fallback_and_why():
    from studio.pipeline import llm_report, report_message
    rep = llm_report(CHECK_TXT, REPORT_SCRIPT, [{"id": "s4", "reason": "no usable code: uses forbidden 'window'"}])
    assert rep["animatable"] == 4 and rep["animated"] == 2          # the check scene is never animated
    assert [f["id"] for f in rep["fallbacks"]] == ["s3", "s4"]
    assert "radius" in rep["fallbacks"][0]["reason"] and "Parts of a Cone" in rep["fallbacks"][0]["name"]
    assert "forbidden" in rep["fallbacks"][1]["reason"]
    msg = report_message(rep)
    assert msg.startswith("LLM animation: 2 of 4 scenes animated") and "s3 “Parts of a Cone”" in msg


def test_llm_report_all_animated():
    from studio.pipeline import llm_report, report_message
    txt = "s1   0.00 →   5.00  (5.00 s)  title · llm animation\ns2   5.00 →   9.00  (4.00 s)  concept · llm animation"
    rep = llm_report(txt, REPORT_SCRIPT)
    assert rep == {"animatable": 2, "animated": 2, "fallbacks": []}
    assert report_message(rep) == "LLM animation: 2 of 2 scenes animated"


def test_llm_report_without_code_reason():
    from studio.pipeline import llm_report
    rep = llm_report("s4   0.00 →  33.51  (33.51 s)  board", REPORT_SCRIPT)
    assert rep["fallbacks"][0]["reason"] == "no animation code was written for this scene"


def test_custom_prompt_asks_for_a_different_look():
    sc = {"id": "s2", "kind": "figure", "title": {"en": "Parts of a Cone"}, "lines": [{"say": "यह कोन है", "en": "This is a cone"}]}
    user = prompts.custom_prompt({"title": {"en": "Cone"}}, sc, "16:9")[1]["content"]
    for must in ("A.camera(", "A.stage", "A.bg(", "A.grad(", "Do NOT rebuild that", "no bullet lists"):
        assert must in user
    assert "One moving thing at a time" not in user                  # the template's rule, not this mode's
    assert not prompts.code_problems("A.bg(A.grad(0,0,0,1080,['#bfe3ff','#fff'])); A.camera(t, [{at: 0, zoom: 1}]);")


# ---------- 3D solid scenes (roadmap phase 2) ----------

def _with_solid(**scene):
    d = json.loads(json.dumps(FIX))
    base = {"kind": "solid", "title": {"en": "Open the cylinder"}, "lines": d["scenes"][1]["lines"][:3],
            "solid": {"shape": "cylinder", "r": 7, "h": 10, "unit": "cm"},
            "moves": [{"do": "revolve", "line": 0}, {"do": "show", "line": 1, "dims": ["r", "h"]},
                      {"do": "unroll", "line": 2}]}
    base.update(scene)
    d["scenes"].insert(2, base)
    return d


def test_solid_scene_is_valid_and_clamps_its_moves():
    d = _with_solid(moves=[{"do": "fill", "line": 9, "len": 50, "level": 3}, {"do": "cut", "at": "0.99", "axis": "v"},
                           {"do": "paint", "part": "base", "color": "orange"}, {"do": "orbit", "turn": "lots", "level": None}])
    sc = Script(**d).scenes[2]
    assert sc.kind == "solid" and sc.solid.shape == "cylinder" and sc.solid.r == 7
    fill, cut, paint, orbit = sc.moves
    assert fill.line == len(sc.lines) - 1 and fill.len == 10 and fill.level == 1
    assert cut.at == 0.9 and cut.axis == "v" and paint.color == "flame" and orbit.turn == 360


def test_solid_scene_needs_its_solid_and_a_known_shape():
    with pytest.raises(ValidationError):
        Script(**_with_solid(solid=None))
    with pytest.raises(ValidationError):
        Script(**_with_solid(solid={"shape": "pyramid", "r": 3}))
    assert Script(**_with_solid(solid={"shape": "Box", "l": 4, "b": 3, "h": 2},
                                moves=[{"do": "show"}])).scenes[2].solid.shape == "cuboid"


def test_structure_problems_reject_moves_a_solid_cannot_do():
    from studio.pipeline import structure_problems
    ok = {"minutes": 1, "kinds": ["title", "concept", "board", "figure", "solid", "example", "check", "summary"], "checks": 1}
    assert structure_problems(Script(**_with_solid()), ok) == []
    probs = structure_problems(Script(**_with_solid(solid={"shape": "sphere", "r": 7})), ok)
    assert any("'unroll' works only for a cylinder or a cone" in p for p in probs)
    probs = structure_problems(Script(**_with_solid(solid={"shape": "cube", "l": 4}, moves=[{"do": "revolve"}])), ok)
    assert any("'revolve' does not make a cube" in p for p in probs)


def test_llm_report_skips_solid_scenes():
    from studio.pipeline import llm_report
    script = {"scenes": [{"id": "s1", "kind": "title", "title": {"en": "T"}}, {"id": "s2", "kind": "solid", "title": {"en": "S"}}]}
    txt = "s1   0.00 →   5.00  (5.00 s)  title · llm animation\ns2   5.00 →   9.00  (4.00 s)  solid · 3D"
    assert llm_report(txt, script) == {"animatable": 1, "animated": 1, "fallbacks": []}


def _unit(context):
    return [{"id": "u1", "name": "Unit", "grade": 9, "subject": "S", "chapter": "C", "chapter_number": 1,
             "section_code": "1.1", "section_name": "N", "bloom": "", "difficulty": "", "description": "", "context": context}]


def test_script_prompt_offers_solids_only_for_3d_lessons():
    st = {"language": "english", "minutes": 3, "checks": 1}
    cone = prompts.script_prompt(_unit("The curved surface area of a right circular cone is πrl."), "", st, [])[1]["content"]
    poem = prompts.script_prompt(_unit("The poem describes the river at dawn."), "", st, [])[1]["content"]
    assert "Scene kinds to use: title, concept, board, figure, solid," in cone and "solid" in cone.split("rough plan:")[1][:80]
    assert "Scene kinds to use: title, concept, board, figure, example," in poem
