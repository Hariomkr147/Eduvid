"""Text comparison for the voice-to-script check."""
import re
import unicodedata

_WS = re.compile(r"\s+")


def normalize(s: str) -> str:
    """NFC, lowercase, drop punctuation/symbols (keep letters, marks, digits of any script), collapse spaces."""
    s = unicodedata.normalize("NFC", s).lower()
    out = []
    for ch in s:
        cat = unicodedata.category(ch)
        if cat[0] in ("L", "M", "N"):
            out.append(ch)
        else:
            out.append(" ")  # punctuation, symbols, whitespace, format chars (ZWJ/ZWNJ) -> space
    return _WS.sub(" ", "".join(out)).strip()


def levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(ref: str, hyp: str) -> float:
    """Character error rate of hyp against ref, on normalised text."""
    r, h = normalize(ref), normalize(hyp)
    if not r:
        return 0.0 if not h else 1.0
    return levenshtein(r, h) / len(r)


# ---------------------------------------------------------------------------
# Spoken-form CER. ASR often writes what was *said* as digits/symbols ("6.02 x 10", "2πrh").
# cer_spoken() tries, for each number/symbol in the transcript, its spoken readings (Hindi words,
# English-in-Devanagari, English) and keeps whichever matches the reference best. It is never higher
# than cer(); a wrong number still counts as an error.
# ---------------------------------------------------------------------------
_HI = ("शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस "
       "बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस "
       "पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस सैंतालीस "
       "अड़तालीस उनचास पचास इक्यावन बावन तिरेपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ इकसठ बासठ तिरेसठ "
       "चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर "
       "अठहत्तर उन्यासी अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे इक्यानवे "
       "बानवे तिरानवे चौरानवे पचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे सौ").split()
_EN_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
            "sixteen seventeen eighteen nineteen").split()
_EN_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
_DE_ONES = ("ज़ीरो वन टू थ्री फ़ोर फ़ाइव सिक्स सेवन एट नाइन टेन इलेवन ट्वेल्व थर्टीन फ़ोर्टीन फ़िफ़्टीन "
            "सिक्सटीन सेवनटीन एटीन नाइनटीन").split()
_DE_TENS = "ट्वेंटी थर्टी फ़ोर्टी फ़िफ़्टी सिक्सटी सेवनटी एटी नाइनटी".split()
_SYMBOLS = {
    "π": ["पाई", "pi"], "x": ["गुणा", "गुना", "इनटू", "times"], "×": ["गुणा", "गुना", "इनटू", "times"],
    "%": ["प्रतिशत", "परसेंट", "percent"], "+": ["प्लस", "धन", "plus"], "=": ["बराबर", "इक्वल्स", "equals"],
    "²": ["स्क्वेयर्ड", "का वर्ग", "squared"], "³": ["क्यूब्ड", "का घन", "cubed"], "°": ["डिग्री", "degrees"],
}
_TOKEN = re.compile(r"\d+(?:\.\d+)?|[π×%+=²³°]|(?<=\d)\s*x\s*(?=\d)|(?<![A-Za-z])x(?![A-Za-z])")


def _composed(n: int) -> list[str]:
    th, rest = divmod(n, 1000)
    h, r = divmod(rest, 100)
    hi, de, en = [], [], []
    if th:
        hi += [_HI[th] if th <= 100 else str(th), "हज़ार"]
        de += [(_DE_ONES[th] if th < 20 else _int_words(th)[1]), "थाउज़ेंड"]
        en += [(_EN_ONES[th] if th < 20 else _int_words(th)[2]), "thousand"]
    if h:
        hi += [_HI[h], "सौ"]
        de += [_DE_ONES[h], "हंड्रेड"]
        en += [_EN_ONES[h], "hundred"]
    if r:
        sub = _int_words(r)
        hi.append(sub[0])
        de.append(sub[1] if len(sub) > 2 else sub[0])
        en.append(sub[2] if len(sub) > 2 else sub[-1])
    return [" ".join(hi), " ".join(de), " ".join(en)]


def _int_words(n: int) -> list[str]:
    out = []
    if n <= 100:
        out.append(_HI[n])
    if n < 20:
        out += [_DE_ONES[n], _EN_ONES[n]]
    elif n < 100:
        t, o = divmod(n, 10)
        out.append(_DE_TENS[t - 2] + ("" if o == 0 else " " + _DE_ONES[o]))
        out.append(_EN_TENS[t - 2] + ("" if o == 0 else " " + _EN_ONES[o]))
    if 100 < n < 100000:  # as said: "दो सौ छप्पन", "two hundred fifty six", "टू हंड्रेड फ़िफ़्टी सिक्स"
        out += _composed(n)
    if n > 100 or not out:  # digit by digit
        d = str(n)
        out += [" ".join(_HI[int(c)] for c in d), " ".join(_DE_ONES[int(c)] for c in d),
                " ".join(_EN_ONES[int(c)] for c in d)]
    return out


def _readings(tok: str) -> list[str]:
    tok = tok.strip()
    if tok in _SYMBOLS:
        return _SYMBOLS[tok]
    if "." in tok:
        a, b = tok.split(".", 1)
        ints = _int_words(int(a))
        hi_d = " ".join(_HI[int(c)] for c in b)
        de_d = " ".join(_DE_ONES[int(c)] for c in b)
        en_d = " ".join(_EN_ONES[int(c)] for c in b)
        return [f"{i} {p} {d}" for i in ints for p, d in
                (("दशमलव", hi_d), ("पॉइंट", hi_d), ("पॉइंट", de_d), ("point", en_d))]
    return _int_words(int(tok))


def cer_spoken(ref: str, hyp: str) -> float:
    """CER where digits/symbols in hyp may be read as any of their spoken forms (best match to ref)."""
    parts: list[str | list[str]] = []
    pos = 0
    h = unicodedata.normalize("NFC", hyp)
    for m in _TOKEN.finditer(h):
        parts.append(h[pos:m.start()])
        parts.append([m.group(0)] + _readings(m.group(0)))
        pos = m.end()
    parts.append(h[pos:])
    if all(isinstance(p, str) for p in parts):
        return cer(ref, hyp)
    choice = [p[0] if isinstance(p, list) else p for p in parts]

    def render() -> str:
        return " ".join(choice)  # spaces around replaced tokens; normalize() collapses them

    for i, p in enumerate(parts):
        if not isinstance(p, list):
            continue
        best, best_c = choice[i], cer(ref, render())
        for cand in p[1:]:
            choice[i] = cand
            c = cer(ref, render())
            if c < best_c:
                best, best_c = cand, c
        choice[i] = best
    return min(cer(ref, hyp), cer(ref, render()))


# ---------------------------------------------------------------------------
# Mixed-script CER. For Hinglish, Whisper often writes the English words it hears in Latin script
# ("एक right angle triangle लो") even with a Devanagari prompt, so a correct take scores as 50-70 % "error"
# against the Devanagari script. When the transcript has Latin letters, both sides are also compared as a
# consonant skeleton (राइट एंगल → RTNGL, "right angle" → RTNGL; vowels, aspiration and h are dropped), and that
# score, scaled by SKELETON_WEIGHT, can stand in. Dropped, garbled or invented words still score high
# (measured on real IndicF5 takes: correct 0.04-0.10 after scaling, a dropped half-sentence 0.31).
# ---------------------------------------------------------------------------
SKELETON_WEIGHT = 0.6
_DEV_CLASS = {}
for _chars, _cls in [("कखक़ख़", "K"), ("गघग़", "G"), ("चछ", "C"), ("जझ", "J"), ("ज़", "S"), ("टठतथ", "T"),
                     ("डढड़ढ़दध", "D"), ("णनङञं", "N"), ("पफफ़", "P"), ("बभव", "B"), ("म", "M"), ("यय़", "Y"),
                     ("रऱ", "R"), ("लळ", "L"), ("शषस", "S")]:
    for _ch in _chars:
        _DEV_CLASS[_ch] = _cls
_LAT_DIGRAPHS = (("gh", ""), ("ph", "f"), ("th", "t"), ("sh", "s"), ("ch", "C"), ("ck", "k"), ("qu", "kw"), ("x", "ks"))
_LAT_CLASS = dict(zip("ckqgjtdnmpfbvwrlszy", "KKKGJTDNMPPBBBRLSSY"))
_LATIN = re.compile(r"[A-Za-z]")


def skeleton(s: str) -> str:
    """Consonant classes of s, script-neutral (Devanagari and Latin map onto the same classes)."""
    s = normalize(s)
    for a, b in _LAT_DIGRAPHS:
        s = s.replace(a, b)
    out: list[str] = []
    for ch in s:
        c = "C" if ch == "C" else _DEV_CLASS.get(ch) or _LAT_CLASS.get(ch)
        if c and (not out or out[-1] != c):
            out.append(c)
    return "".join(out)


def _skeleton_cer(ref: str, hyp: str) -> float:
    r = skeleton(ref)
    if not r:
        return 0.0 if not skeleton(hyp) else 1.0
    parts: list[str | list[str]] = []
    pos = 0
    for m in _TOKEN.finditer(hyp):
        parts.append(hyp[pos:m.start()])
        parts.append(_readings(m.group(0)) or [m.group(0)])
        pos = m.end()
    parts.append(hyp[pos:])
    choice = [p[0] if isinstance(p, list) else p for p in parts]

    def score() -> float:
        return levenshtein(r, skeleton(" ".join(choice))) / len(r)
    for i, p in enumerate(parts):
        if isinstance(p, list):
            best, best_s = choice[i], score()
            for cand in p:
                choice[i] = cand
                s_ = score()
                if s_ < best_s:
                    best, best_s = cand, s_
            choice[i] = best
    return score()


def cer_mixed(ref: str, hyp: str) -> float:
    """cer_spoken(), or the scaled consonant-skeleton CER when the transcript mixes in Latin script."""
    c = cer_spoken(ref, hyp)
    if not _LATIN.search(hyp):
        return c
    return min(c, round(SKELETON_WEIGHT * _skeleton_cer(ref, hyp), 4))
