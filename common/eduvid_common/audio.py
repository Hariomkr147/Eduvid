"""Pipeline audio helpers. Pipeline format: 24 kHz mono 16-bit PCM WAV.

Standard library + ffmpeg only (no numpy), so every image can use it.
"""
import io
import math
import subprocess
import wave
from array import array

SR = 24000


class AudioError(ValueError):
    pass


def to_wav_24k_mono(data: bytes) -> bytes:
    """Decode anything ffmpeg can read and return 24 kHz mono s16 WAV."""
    if not data:
        raise AudioError("could not decode audio: empty input")
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", "pipe:0", "-ac", "1", "-ar", str(SR),
         "-c:a", "pcm_s16le", "-f", "wav", "-bitexact", "pipe:1"],
        input=data, capture_output=True, timeout=300,
    )
    if p.returncode != 0 or len(p.stdout) <= 44:
        raise AudioError(f"could not decode audio: {p.stderr.decode(errors='replace')[-300:]}")
    # ffmpeg writing to a pipe leaves the RIFF sizes unset; rewrite a clean header.
    return _pcm_to_wav(_wav_pcm_from_ffmpeg(p.stdout), SR)


def _wav_pcm_from_ffmpeg(raw: bytes) -> bytes:
    i = raw.find(b"data")
    if i < 0:
        raise AudioError("could not decode audio: no data chunk")
    return raw[i + 8:]


def _pcm_to_wav(pcm: bytes, sr: int) -> bytes:
    if len(pcm) % 2:
        pcm = pcm[:-1]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return buf.getvalue()


def _read(wav: bytes) -> tuple[bytes, int, int, int]:
    try:
        with wave.open(io.BytesIO(wav)) as w:
            return w.readframes(w.getnframes()), w.getframerate(), w.getnchannels(), w.getsampwidth()
    except (wave.Error, EOFError) as e:
        raise AudioError(f"not a PCM wav: {e}") from e


def _pcm_24k_mono(wav: bytes) -> bytes:
    pcm, sr, ch, sw = _read(wav)
    if (sr, ch, sw) != (SR, 1, 2):
        pcm, *_ = _read(to_wav_24k_mono(wav))
    return pcm


def duration_s(wav: bytes) -> float:
    with wave.open(io.BytesIO(wav)) as w:
        return w.getnframes() / w.getframerate()


def rms_dbfs(wav: bytes) -> float:
    pcm, _, _, sw = _read(wav)
    if sw != 2:
        pcm, *_ = _read(to_wav_24k_mono(wav))
    a = array("h")
    a.frombytes(pcm)
    if not a:
        return -120.0
    rms = math.sqrt(sum(x * x for x in a) / len(a))
    return 20 * math.log10(rms / 32768) if rms > 0 else -120.0


def float_to_wav_24k_mono(samples, sr: int) -> bytes:
    """Float samples in [-1, 1] (list / numpy array, mono) at any rate -> 24 kHz mono s16 WAV."""
    a = array("h", (max(-32768, min(32767, int(round(float(x) * 32767)))) for x in samples))
    wav = _pcm_to_wav(a.tobytes(), sr)
    return wav if sr == SR else to_wav_24k_mono(wav)


def concat_with_gaps(wavs: list[bytes], gaps_s: list[float], lead_s: float, outro_s: float) -> bytes:
    """lead silence + wav0 + gap0 + wav1 + ... + outro silence, all at 24 kHz mono."""
    if wavs and len(gaps_s) != len(wavs) - 1:
        raise ValueError(f"need {len(wavs) - 1} gaps for {len(wavs)} clips, got {len(gaps_s)}")

    def silence(s: float) -> bytes:
        return b"\x00\x00" * int(round(max(0.0, s) * SR))

    parts = [silence(lead_s)]
    for i, w in enumerate(wavs):
        parts.append(_pcm_24k_mono(w))
        if i < len(gaps_s):
            parts.append(silence(gaps_s[i]))
    parts.append(silence(outro_s))
    return _pcm_to_wav(b"".join(parts), SR)
