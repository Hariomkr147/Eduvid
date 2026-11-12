import io
import wave

import pytest

from tests.conftest import FakeSpeech, script
from voice_worker.voice import SpeakableError, build_narration, group_lines

S = script([
    {"say": "सिलेंडर का एरिया,", "caps": "@0 Cylinder ka *area"},
    {"say": "टू पाई आर एच होता है।", "caps": "@0 *2πrh"},
    {"say": "अब कोन देखो।", "caps": "@0 Ab *cone", "gap": 0.5},
])


def wav_seconds(b: bytes) -> float:
    with wave.open(io.BytesIO(b)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (24000, 1, 2)
        return w.getnframes() / w.getframerate()


def test_groups_follow_sentence_ends():
    assert group_lines(S["lines"]) == [[0, 1], [2]]
    assert group_lines([{"say": "एक"}, {"say": "दो", "break": True}, {"say": "तीन"}]) == [[0, 1], [2]]


def test_clean_takes_shape():
    sp = FakeSpeech()
    wav, lines, report = build_narration(S, "hinglish", "omnivoice:hinglish-female", sp.synth, sp.transcribe)
    assert [c[2] for c in sp.synth_calls] == [1, 1]                       # one take per sentence, seed 1
    assert sp.synth_calls[0][0] == "सिलेंडर का एरिया, टू पाई आर एच होता है।"
    L = lines["lines"]
    assert [x["i"] for x in L] == [0, 1, 2] and [x["group"] for x in L] == [0, 0, 1]
    assert L[0]["start"] == pytest.approx(0.15, abs=0.02)
    assert L[0]["end"] <= L[1]["start"] < L[1]["end"] <= L[2]["start"] < L[2]["end"]
    assert L[0]["group_end"] == L[1]["group_end"] == L[1]["end"]
    assert abs(lines["duration"] - wav_seconds(wav)) < 0.01
    assert lines["duration"] == pytest.approx(L[2]["end"] + 0.5 + 0.5, abs=0.02)   # last line's gap, then outro
    assert [r["takes"] for r in report] == [1, 1] and not any(r["flagged"] for r in report)


def test_cut_snaps_to_a_pause():
    sp = FakeSpeech()
    _, lines, _ = build_narration(S, "hinglish", "v", sp.synth, sp.transcribe)
    L = lines["lines"]
    # tone words are 0.3 s with 0.12 s pauses; trim leaves 0.01 s before the first word. The cut is placed by
    # character length (engine rule) and must land inside one of the pauses, not mid-word.
    t0 = L[0]["group_start"] + 0.01
    pauses = [(t0 + k * 0.3 + (k - 1) * 0.12, t0 + k * 0.42) for k in range(1, 9)]
    assert any(lo - 0.03 <= L[0]["end"] <= L[1]["start"] <= hi + 0.03 for lo, hi in pauses), (L[0]["end"], pauses)
    assert L[1]["start"] - L[0]["end"] > 0.05


def test_retake_on_high_cer():
    sp = FakeSpeech(bad_takes=1)
    _, _, report = build_narration(S, "hinglish", "v", sp.synth, sp.transcribe)
    first = [c for c in sp.synth_calls if c[0].startswith("सिलेंडर")]
    assert len(first) == 2 and [c[2] for c in first] == [1, 2]
    assert report[0]["takes"] == 2 and report[0]["seed"] == 2 and not report[0]["flagged"]
    assert report[0]["cer"][0] > 0.12 >= report[0]["cer"][1]


def test_flag_after_three_bad_takes():
    sp = FakeSpeech(bad_takes=99)
    wav, lines, report = build_narration(S, "hinglish", "v", sp.synth, sp.transcribe)
    assert report[0]["takes"] == 3 and report[0]["flagged"] is True
    assert len(sp.synth_calls) == 6 and lines["lines"] and wav_seconds(wav) > 1


def test_speakable_violation_raises_before_synthesis():
    sp = FakeSpeech()
    bad = script([{"say": "अब cone देखो।"}, {"say": "वॉल्यूम 2 गुना।"}])
    with pytest.raises(SpeakableError) as e:
        build_narration(bad, "hinglish", "v", sp.synth, sp.transcribe)
    assert "line 0" in str(e.value) and "line 1" in str(e.value)
    assert sp.synth_calls == []


def test_say_is_required():
    sp = FakeSpeech()
    with pytest.raises(SpeakableError, match="line 0.*say"):
        build_narration(script([{"text": "x"}]), "hinglish", "v", sp.synth, sp.transcribe)
