"""words job: forced alignment of the known `say` words, one sentence at a time (spec §5.5).

Output keeps engine/scripts/words.py's format {w, line, s, e, matched} plus the aligner's score. Cuts inside a
sentence move onto the aligned word boundaries with the engine's refine_cuts rule.
"""
import copy
import unicodedata
from collections.abc import Callable

import numpy as np

from .voice import SR, read_wav, write_wav

MATCH_SCORE = 0.3
Align = Callable[[bytes, list[str], str], list[dict]]   # (wav, words, language) -> [{word,start,end,score}] 1:1


def norm(w: str) -> str:
    """lower-case, keep letters, combining marks (Devanagari vowel signs) and digits of any script"""
    return "".join(ch for ch in unicodedata.normalize("NFC", str(w).lower()) if unicodedata.category(ch)[0] in "LMN")


def refine_cuts(L: list[dict], words: list[dict]) -> int:
    """engine/scripts/words.py::refine_cuts — move each cut inside a sentence onto the heard words. Returns # moved."""
    moved = 0
    for k in range(1, len(L)):
        a, b = L[k - 1], L[k]
        if a.get("group") is None or a.get("group") != b.get("group"):
            continue
        wa = [w for w in words if w["line"] == k - 1]
        wb = [w for w in words if w["line"] == k]
        if not wa or not wb or not wb[0].get("matched") or not wa[-1].get("matched"):
            continue
        end, start = wa[-1]["e"], wb[0]["s"]
        if start < end:
            start = end = (start + end) / 2
        lo, hi = a["start"] + 0.2, b["end"] - 0.2                       # keep both lines non-empty
        if not (lo < start < hi):
            continue
        if abs(b["start"] - start) > 0.03 or abs(a["end"] - end) > 0.03:
            moved += 1
        a["end"], b["start"] = round(end, 3), round(start, 3)
    return moved


def build_words(narration_wav: bytes, script: dict, lines_json: dict, language: str,
                align: Align) -> tuple[list[dict], dict]:
    """-> (words_json, lines_json with refined cuts). lines_json is not modified in place."""
    LJ = copy.deepcopy(lines_json)
    L = LJ["lines"]
    x = read_wav(narration_wav)
    toks = [(w, i) for i, ln in enumerate(script["lines"]) for w in ln["say"].split() if norm(w)]
    groups: dict[int, list[int]] = {}
    for i, ln in enumerate(L):
        groups.setdefault(ln["group"], []).append(i)

    words: list[dict] = []
    for g in sorted(groups):
        members = set(groups[g])
        gt = [(w, i) for w, i in toks if i in members]
        if not gt:
            continue
        g0, g1 = L[groups[g][0]]["group_start"], L[groups[g][0]]["group_end"]
        clip = write_wav(x[int(round(g0 * SR)):int(round(g1 * SR))]) if g1 > g0 else write_wav(np.zeros(1))
        got = align(clip, [w for w, _ in gt], language)
        if len(got) != len(gt):
            raise ValueError(f"aligner returned {len(got)} words for {len(gt)} in sentence {g}")
        for (w, i), a in zip(gt, got):
            score = float(a.get("score") or 0.0)
            s = min(max(g0 + float(a["start"]), g0), g1)
            e = min(max(g0 + float(a["end"]), s), g1)
            words.append({"w": w, "line": i, "s": round(s, 3), "e": round(e, 3),
                          "matched": score >= MATCH_SCORE, "score": round(score, 3)})

    refine_cuts(L, words)
    prev = 0.0
    for w in words:                                    # each word inside its (refined) line, starts never go back
        lo, hi = L[w["line"]]["start"], L[w["line"]]["end"]
        w["s"] = round(min(max(w["s"], lo, prev), hi), 3)
        w["e"] = round(min(max(w["e"], w["s"]), hi), 3)
        prev = w["s"]
    return words, LJ
