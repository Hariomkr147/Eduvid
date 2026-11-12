"""Fakes for the gateway: synth makes a tone per word with short pauses, so cut placement has real pauses to find."""
import io
import math
import struct
import wave

import pytest

SR = 24000


def tone_wav(words: list[str], word_s: float = 0.3, pause_s: float = 0.12, lead_s: float = 0.05) -> bytes:
    frames = [0] * int(lead_s * SR)
    for k, _ in enumerate(words):
        frames += [int(9000 * math.sin(2 * math.pi * 220 * i / SR)) for i in range(int(word_s * SR))]
        if k < len(words) - 1:
            frames += [0] * int(pause_s * SR)
    frames += [0] * int(lead_s * SR)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(struct.pack(f"<{len(frames)}h", *frames))
    return buf.getvalue()


class FakeSpeech:
    """synth/transcribe/align with scripted behaviour. `bad_takes` = how many first takes per text come back garbled."""

    def __init__(self, bad_takes: int = 0):
        self.bad_takes = bad_takes
        self.synth_calls: list[tuple[str, str, int]] = []
        self._last_text = ""
        self._count: dict[str, int] = {}

    def synth(self, text: str, voice: str, seed: int) -> bytes:
        self.synth_calls.append((text, voice, seed))
        self._last_text = text
        self._count[text] = self._count.get(text, 0) + 1
        return tone_wav(text.split())

    def transcribe(self, wav: bytes, language: str) -> str:
        if self._count[self._last_text] <= self.bad_takes:
            return "गड़बड़ आवाज़"
        return self._last_text

    def align(self, wav: bytes, words: list[str], language: str) -> list[dict]:
        # words were spoken as tone_wav(words): lead 0.05, each 0.3 s, pause 0.12
        out, t = [], 0.05
        for w in words:
            out.append({"word": w, "start": round(t, 3), "end": round(t + 0.3, 3), "score": 0.9})
            t += 0.42
        return out


@pytest.fixture
def speech():
    return FakeSpeech()


def script(lines: list[dict], **kw) -> dict:
    return {"lead": 0.15, "gap": 0.3, "outro": 0.5, "lines": lines, **kw}
