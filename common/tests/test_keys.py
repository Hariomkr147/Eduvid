import pytest

from eduvid_common.keys import lesson_key, segment_key


def test_segment_key_layout():
    assert (
        segment_key(9, "maths", "ch11-surface-areas", 2, 4, 3, "hinglish", "draft.mp4")
        == "class-9/maths/ch11-surface-areas/lesson-02/seg-04/v3/hinglish/draft.mp4"
    )


def test_lesson_key_layout():
    assert (
        lesson_key(9, "maths", "ch11-surface-areas", 2, "english")
        == "class-9/maths/ch11-surface-areas/lesson-02/english/lesson.mp4"
    )


def test_key_rejects_bad_language():
    with pytest.raises(ValueError):
        segment_key(9, "maths", "ch11", 1, 1, 1, "french", "draft.mp4")


@pytest.mark.parametrize(
    "args",
    [
        (0, "maths", "ch11", 1, 1, 1, "hindi", "a.mp4"),  # class out of range
        (9, "Maths", "ch11", 1, 1, 1, "hindi", "a.mp4"),  # subject not slug
        (9, "maths", "../x", 1, 1, 1, "hindi", "a.mp4"),  # path traversal
        (9, "maths", "ch11", 0, 1, 1, "hindi", "a.mp4"),  # lesson < 1
        (9, "maths", "ch11", 1, 1, 0, "hindi", "a.mp4"),  # version < 1
        (9, "maths", "ch11", 1, 1, 1, "hindi", "x/a.mp4"),  # filename with slash
        (9, "maths", "ch11", 1, 1, 1, "hindi", ""),  # empty filename
    ],
)
def test_key_rejects_bad_parts(args):
    with pytest.raises(ValueError):
        segment_key(*args)
