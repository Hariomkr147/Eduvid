import io
import math
import struct
import subprocess
import wave

import pytest

from eduvid_common import audio


def _tone(seconds=1.0, sr=48000, channels=2, amp=8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = bytearray()
        for i in range(int(seconds * sr)):
            v = int(amp * math.sin(2 * math.pi * 440 * i / sr))
            frames += struct.pack("<h", v) * channels
        w.writeframes(bytes(frames))
    return buf.getvalue()


def _info(wav: bytes):
    with wave.open(io.BytesIO(wav)) as w:
        return w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()


def test_to_wav_24k_mono_from_48k_stereo():
    out = audio.to_wav_24k_mono(_tone(1.0, 48000, 2))
    sr, ch, sw, n = _info(out)
    assert (sr, ch, sw) == (24000, 1, 2)
    assert abs(n / sr - 1.0) < 0.01


def test_to_wav_24k_mono_from_mp3(tmp_path):
    src = tmp_path / "a.wav"
    src.write_bytes(_tone(2.0, 44100, 2))
    mp3 = tmp_path / "a.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), str(mp3)], check=True)
    out = audio.to_wav_24k_mono(mp3.read_bytes())
    assert _info(out)[:2] == (24000, 1)
    assert abs(audio.duration_s(out) - 2.0) < 0.1


def test_to_wav_rejects_garbage():
    with pytest.raises(audio.AudioError):
        audio.to_wav_24k_mono(b"not audio at all" * 10)
    with pytest.raises(audio.AudioError):
        audio.to_wav_24k_mono(b"")


def test_duration_and_rms():
    w = audio.to_wav_24k_mono(_tone(1.5, 24000, 1, amp=8000))
    assert abs(audio.duration_s(w) - 1.5) < 0.01
    # sine of amplitude 8000: rms = 8000/sqrt(2) -> 20*log10(5657/32768) ≈ -15.3 dBFS
    assert -16.5 < audio.rms_dbfs(w) < -14.0
    silent = audio.to_wav_24k_mono(_tone(0.5, 24000, 1, amp=0))
    assert audio.rms_dbfs(silent) <= -90


def test_concat_with_gaps():
    a = audio.to_wav_24k_mono(_tone(1.0, 24000, 1))
    b = audio.to_wav_24k_mono(_tone(0.5, 24000, 1))
    out = audio.concat_with_gaps([a, b], [0.3], lead_s=0.2, outro_s=0.5)
    assert _info(out)[:2] == (24000, 1)
    assert abs(audio.duration_s(out) - (0.2 + 1.0 + 0.3 + 0.5 + 0.5)) < 0.005


def test_concat_gap_count_must_match():
    a = audio.to_wav_24k_mono(_tone(0.2, 24000, 1))
    with pytest.raises(ValueError):
        audio.concat_with_gaps([a, a], [], 0, 0)


def test_concat_resamples_odd_inputs():
    a = _tone(1.0, 48000, 2)  # not 24k mono: must be normalised first
    out = audio.concat_with_gaps([a], [], 0.0, 0.0)
    assert _info(out)[:2] == (24000, 1)
    assert abs(audio.duration_s(out) - 1.0) < 0.01


def test_pcm_float_to_wav():
    samples = [math.sin(2 * math.pi * 440 * i / 16000) * 0.5 for i in range(16000)]
    out = audio.float_to_wav_24k_mono(samples, 16000)
    assert _info(out)[:2] == (24000, 1)
    assert abs(audio.duration_s(out) - 1.0) < 0.01
