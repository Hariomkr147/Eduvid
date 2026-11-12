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
