import unicodedata

from eduvid_common.textmetrics import cer, normalize


def test_cer_identical_is_zero():
    assert cer("सिलेंडर का एरिया", "सिलेंडर का एरिया") == 0


def test_cer_missing_word_is_positive():
    assert cer("टू पाई आर एच", "टू पाई एच") > 0


def test_cer_value():
    # "abcd" -> "abed": 1 substitution / 4 chars
    assert cer("abcd", "abed") == 0.25


def test_nfc_decomposed_equals_precomposed():
    pre = "क़"  # क़ precomposed
    dec = "क़"  # क + nukta
    assert pre != dec
    assert normalize(pre) == normalize(dec)
    assert cer("क़लम", unicodedata.normalize("NFD", "क़लम")) == 0


def test_normalize_strips_punctuation_case_and_space():
    assert normalize("  Hello,   World!  ") == "hello world"
    assert normalize("सिलेंडर का एरिया।") == normalize("सिलेंडर का एरिया")


def test_normalize_keeps_marks_and_digits():
    s = normalize("कि 42")
    assert "ि" in s and "42" in s


def test_cer_empty_reference():
    assert cer("", "") == 0
    assert cer("", "x") == 1.0


# --- spoken-form CER: digits/symbols in the ASR transcript may stand for spoken words ---
from eduvid_common.textmetrics import cer_spoken  # noqa: E402


def test_spoken_digit_hinglish_and_hindi():
    assert cer_spoken("टू पाई आर एच", "2 पाई आर एच") == 0
    assert cer_spoken("दो पाई आर एच", "2 पाई आर एच") == 0


def test_spoken_decimal_and_times():
    ref = "छह पॉइंट शून्य दो गुणा दस की पावर तेईस"
    assert cer_spoken(ref, "6.02 गुणा 10 की पावर 23") == 0
    assert cer_spoken(ref, "6.02 x 10 की पावर 23") == 0


def test_spoken_two_digit_hindi():
    assert cer_spoken("आठ गुना", "8 गुना") == 0
    assert cer_spoken("पैंतालीस डिग्री", "45 डिग्री") == 0


def test_spoken_english_glued_symbols():
    assert cer_spoken("two pi r h", "2πrh") < 0.12
    assert cer_spoken("nine point eight", "9.8") == 0


def test_spoken_never_worse_than_plain():
    for ref, hyp in [("सिलेंडर का एरिया", "सिलेंडर एरिया"), ("एक दो", "1 3"), ("abc", "xyz 5")]:
        assert cer_spoken(ref, hyp) <= cer(ref, hyp)


def test_spoken_wrong_number_still_counts():
    assert cer_spoken("दो पाई आर एच", "3 पाई आर एच") > 0
