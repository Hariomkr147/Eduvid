"""The video script (spec 2026-11-12 §4): one JSON shared by the template and the LLM-animation renders.

On-screen text is bilingual ({en, hi}); spoken text (`say`) is in the video language and must be speakable
(eduvid_common.speakable). Items that appear during a scene are anchored to a line of that scene (`line`) and,
optionally, to a word of it (`word`, a prefix of a spoken word in that line's `say`).
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from eduvid_common.speakable import violations

KINDS = ("title", "concept", "board", "figure", "example", "check", "summary")
Kind = Literal["title", "concept", "board", "figure", "example", "check", "summary"]
LANGUAGES = ("hinglish", "hindi", "english")


class Bi(BaseModel):
    en: str = ""
    hi: str = ""

    @model_validator(mode="before")
    @classmethod
    def _from_str(cls, v):
        return {"en": v, "hi": v} if isinstance(v, str) else v


class Line(BaseModel):
    say: str = Field(min_length=1, max_length=400)       # what the voice speaks (speakable)
    caps: str = ""                                        # caption in the video language ("|" splits chunks, "@n" pins)
    en: str = ""                                          # English caption (player's English track)
    gap: float | None = Field(default=None, ge=0, le=20)  # silence after this line (check scenes use it to pause)


class Anchor(BaseModel):
    line: int = Field(default=0, ge=0)
    word: str = ""


class Point(Anchor):
    text: Bi
    tex: str = ""


class Step(Anchor):
    tex: str = ""
    text: Bi = Bi()
    key: bool = False


SHAPES = ("point", "segment", "line", "arrow", "circle", "arc", "rect", "polygon", "cylinder", "cone", "sphere",
          "hemisphere", "cuboid", "angle", "axes", "curve", "label", "brace", "dim")


class Shape(Anchor):
    type: Literal[SHAPES]  # type: ignore[valid-type]
    # geometry in a 160 × 90 unit box (x right, y down); meaning of numbers depends on the type
    x: float = 0
    y: float = 0
    x2: float = 0
    y2: float = 0
    r: float = 0
    w: float = 0
    h: float = 0
    a1: float = 0
    a2: float = 0
    pts: list[list[float]] = []
    label: str = ""          # short label or maths only: shared pictures carry no sentences
    color: Literal["ink", "primary", "start", "good", "flame", "gold", "muted"] = "ink"
    fill: bool = False
    dashed: bool = False


class Scene(BaseModel):
    id: str = ""
    kind: Kind
    title: Bi
    lines: list[Line] = Field(min_length=1, max_length=10)
    # per-kind content (validated in Script._kinds)
    tag: Bi = Bi()
    subtitle: Bi = Bi()
    objectives: list[Bi] = []
    points: list[Point] = []
    steps: list[Step] = []
    shapes: list[Shape] = []
    question: Bi = Bi()
    options: list[Bi] = []
    correct: int = 0
    hint: Bi = Bi()
    explain: Bi = Bi()
    answer: Bi = Bi()
    answer_tex: str = ""
    next: Bi = Bi()
    pause_s: float = Field(default=6, ge=2, le=20)
    custom_brief: str = ""                    # what an LLM-written animation should show
    custom_code: str | None = None            # filled by the code step (LLM-animation mode)


class Script(BaseModel):
    title: Bi
    language: Literal["hinglish", "hindi", "english"]
    screen_lang: Literal["en", "hi"] = "en"
    scenes: list[Scene] = Field(min_length=1, max_length=40)
    sources: list[str] = []

    @field_validator("scenes")
    @classmethod
    def _ids(cls, scenes):
        for i, s in enumerate(scenes):
            s.id = f"s{i + 1}"
        return scenes

    @model_validator(mode="after")
    def _kinds(self):
        for s in self.scenes:
            n = len(s.lines)
            for item in [*s.points, *s.steps, *s.shapes]:
                if item.line >= n:
                    item.line = n - 1
            if s.kind == "check":
                if len(s.options) < 2 or len(s.options) > 4:
                    raise ValueError(f"scene {s.id}: a check needs 2-4 options")
                if not 0 <= s.correct < len(s.options):
                    raise ValueError(f"scene {s.id}: correct must index an option")
                if n < 2:
                    raise ValueError(f"scene {s.id}: a check needs a question line and an answer line")
                s.lines[0].gap = s.pause_s
        return self

    def speakable_problems(self) -> list[str]:
        out = []
        for s in self.scenes:
            for j, ln in enumerate(s.lines):
                bad = violations(ln.say, self.language)
                if bad:
                    out.append(f"{s.id} line {j}: 'say' has {''.join(bad)!r}: {ln.say[:80]}")
        return out


def voice_script(script: Script, music: str = "none") -> dict:
    """The flat script the voice worker reads: one line per narration line, a sentence break at every scene end."""
    lines = []
    for s in script.scenes:
        for j, ln in enumerate(s.lines):
            say = ln.say.strip()
            item = {"say": say, "text": ln.caps or say, "caps": ln.caps, "scene": s.id}
            if j == len(s.lines) - 1:
                item["break"] = True
                item["gap"] = 0.7
            if ln.gap is not None:
                item["gap"] = ln.gap
                item["break"] = True
            lines.append(item)
    return {"title": script.title.en or script.title.hi, "lead": 0.4, "gap": 0.32, "outro": 1.2,
            "music": music, "lines": lines}
