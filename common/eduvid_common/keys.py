"""Object key layout (fixed by the plan):

class-{n}/{subject}/{chapter_slug}/lesson-{nn}/seg-{nn}/v{n}/{language}/{file}
class-{n}/{subject}/{chapter_slug}/lesson-{nn}/{language}/lesson.mp4
"""
import re

LANGUAGES = ("hinglish", "english", "hindi")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _check(cls: int, subject: str, chapter_slug: str, lesson: int, language: str) -> None:
    if not isinstance(cls, int) or not 1 <= cls <= 12:
        raise ValueError(f"class must be 1..12, got {cls!r}")
    for name, v in (("subject", subject), ("chapter_slug", chapter_slug)):
        if not isinstance(v, str) or not _SLUG.match(v):
            raise ValueError(f"{name} must be a lowercase slug, got {v!r}")
    if not isinstance(lesson, int) or lesson < 1:
        raise ValueError(f"lesson must be >= 1, got {lesson!r}")
    if language not in LANGUAGES:
        raise ValueError(f"language must be one of {LANGUAGES}, got {language!r}")


def lesson_prefix(cls: int, subject: str, chapter_slug: str, lesson: int) -> str:
    return f"class-{cls}/{subject}/{chapter_slug}/lesson-{lesson:02d}"


def segment_prefix(
    cls: int, subject: str, chapter_slug: str, lesson: int, seg: int, version: int, language: str
) -> str:
    """Prefix ending in '/', e.g. class-9/maths/ch11/lesson-02/seg-04/v3/hinglish/."""
    _check(cls, subject, chapter_slug, lesson, language)
    if not isinstance(seg, int) or seg < 1:
        raise ValueError(f"seg must be >= 1, got {seg!r}")
    if not isinstance(version, int) or version < 1:
        raise ValueError(f"version must be >= 1, got {version!r}")
    return f"{lesson_prefix(cls, subject, chapter_slug, lesson)}/seg-{seg:02d}/v{version}/{language}/"


def segment_key(
    cls: int,
    subject: str,
    chapter_slug: str,
    lesson: int,
    seg: int,
    version: int,
    language: str,
    filename: str,
) -> str:
    if not isinstance(filename, str) or not _FILE.match(filename):
        raise ValueError(f"bad filename {filename!r}")
    return segment_prefix(cls, subject, chapter_slug, lesson, seg, version, language) + filename


def lesson_key(cls: int, subject: str, chapter_slug: str, lesson: int, language: str) -> str:
    _check(cls, subject, chapter_slug, lesson, language)
    return f"{lesson_prefix(cls, subject, chapter_slug, lesson)}/{language}/lesson.mp4"
