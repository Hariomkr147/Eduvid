"""Kokoro-82M (Apache-2.0) via kokoro-onnx on onnxruntime-gpu, CPU fallback."""
import logging
import os
import urllib.request
from pathlib import Path

from eduvid_common.tts_server import Backend, make_app

log = logging.getLogger("kokoro")
MODEL_DIR = Path(os.environ.get("KOKORO_DIR", "/models/kokoro"))
RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
FILES = ("kokoro-v1.0.onnx", "voices-v1.0.bin")
# voice-name prefix -> espeak language
LANGS = {"a": "en-us", "b": "en-gb", "h": "hi", "e": "es", "f": "fr-fr", "i": "it", "p": "pt-br"}


class KokoroBackend(Backend):
    name = "kokoro"

    def load(self) -> None:
        import onnxruntime as ort
        from kokoro_onnx import Kokoro

        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        for f in FILES:
            p = MODEL_DIR / f
            if not p.exists():
                log.warning("downloading %s", f)
                tmp = p.with_suffix(".part")
                urllib.request.urlretrieve(f"{RELEASE}/{f}", tmp)
                tmp.rename(p)
        providers = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in ort.get_available_providers()]
        sess = ort.InferenceSession(str(MODEL_DIR / FILES[0]), providers=providers)
        log.warning("onnxruntime providers in use: %s", sess.get_providers())
        self.provider = sess.get_providers()[0]
        self.k = Kokoro.from_session(sess, str(MODEL_DIR / FILES[1]))

    def voices(self) -> list[dict]:
        out = []
        for v in sorted(self.k.get_voices()):
            lang = LANGS.get(v[0])
            if lang:
                out.append({"id": v, "language": lang, "description": f"kokoro {v} ({lang}, {self.provider})"})
        return out

    def synthesize(self, text, voice, language, instruct, speed, seed):
        lang = language or LANGS[voice[0]]
        samples, sr = self.k.create(text, voice=voice, speed=speed, lang=lang)
        return samples, sr


app = make_app(KokoroBackend())
