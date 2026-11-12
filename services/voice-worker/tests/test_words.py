import copy

from tests.conftest import FakeSpeech, script
from voice_worker.voice import build_narration
from voice_worker.words import build_words, refine_cuts

S = script([
    {"say": "सिलेंडर का एरिया,"},
    {"say": "टू पाई आर एच होता है।"},
    {"say": "अब कोन देखो।"},
])


def narrate(sp):
    return build_narration(S, "hinglish", "v", sp.synth, sp.transcribe)


def test_words_shape_and_order():
    sp = FakeSpeech()
    wav, lines, _ = narrate(sp)
    words, lines2 = build_words(wav, S, lines, "hinglish", sp.align)
    say_words = [w for ln in S["lines"] for w in ln["say"].split()]
    assert [w["w"] for w in words] == say_words
    assert [w["line"] for w in words] == [0, 0, 0, 1, 1, 1, 1, 1, 1, 2, 2, 2]
    assert all(set(w) == {"w", "line", "s", "e", "matched", "score"} for w in words)
    assert all(a["s"] <= b["s"] for a, b in zip(words, words[1:]))
    for w in words:
        ln = lines2["lines"][w["line"]]
        assert ln["start"] - 1e-6 <= w["s"] <= w["e"] <= ln["end"] + 1e-6
    assert all(w["matched"] for w in words)


def test_align_called_per_sentence_with_clipped_audio():
    sp = FakeSpeech()
    wav, lines, _ = narrate(sp)
    calls = []

    def align(clip, ws, lang):
        calls.append((len(clip), ws, lang))
        return sp.align(clip, ws, lang)

    build_words(wav, S, lines, "hinglish", align)
    assert [c[1] for c in calls] == [["सिलेंडर", "का", "एरिया,", "टू", "पाई", "आर", "एच", "होता", "है।"],
                                     ["अब", "कोन", "देखो।"]]
    assert calls[0][2] == "hinglish"
    g0 = lines["lines"][0]
    assert abs(calls[0][0] - (44 + 2 * round((g0["group_end"] - g0["group_start"]) * 24000))) < 200


def test_low_score_is_not_matched():
    sp = FakeSpeech()
    wav, lines, _ = narrate(sp)

    def align(clip, ws, lang):
        out = sp.align(clip, ws, lang)
        out[1]["score"] = 0.1
        out[2]["score"] = None
        return out

    words, _ = build_words(wav, S, lines, "hinglish", align)
    assert [w["matched"] for w in words[:4]] == [True, False, False, True]
    assert words[2]["score"] == 0


def test_cut_moves_to_aligned_boundary():
    L = [{"i": 0, "start": 0.15, "end": 1.0, "group": 0, "group_start": 0.15, "group_end": 3.0},
         {"i": 1, "start": 1.0, "end": 3.0, "group": 0, "group_start": 0.15, "group_end": 3.0}]
    words = [{"w": "a", "line": 0, "s": 0.2, "e": 0.8, "matched": True},
             {"w": "b", "line": 0, "s": 0.85, "e": 1.3, "matched": True},
             {"w": "c", "line": 1, "s": 1.4, "e": 2.9, "matched": True}]
    L2 = copy.deepcopy(L)
    assert refine_cuts(L2, words) == 1
    assert L2[0]["end"] == 1.3 and L2[1]["start"] == 1.4
    # unmatched neighbour: cut stays
    words[2]["matched"] = False
    L3 = copy.deepcopy(L)
    assert refine_cuts(L3, words) == 0 and L3 == L
