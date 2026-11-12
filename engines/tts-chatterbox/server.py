"""Chatterbox Multilingual v3 (Resemble AI, MIT). Upstream is retired/unmaintained. Output is watermarked (PerTh)."""
import os
from pathlib import Path

from eduvid_common.tts_server import Backend, make_app

T3 = os.environ.get("CHATTERBOX_T3", "v3")
REFS = Path(os.environ.get("CHATTERBOX_REFS", "/models/refs/chatterbox"))
# voice id -> (language_id, reference clip or None for the built-in default voice)
BASE_VOICES = {"hindi-default": ("hi", None), "english-default": ("en", None)}


class ChatterboxBackend(Backend):
    name = "chatterbox"

    def load(self) -> None:
        import torch
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        self.model = ChatterboxMultilingualTTS.from_pretrained(device=torch.device("cuda"), t3_model=T3)
        self.v = dict(BASE_VOICES)
        for wav in sorted(REFS.glob("*.wav")) if REFS.exists() else []:
            lang = "en" if wav.stem.startswith("english") else "hi"
            self.v[wav.stem] = (lang, str(wav))

    def voices(self) -> list[dict]:
        return [{"id": k, "language": lang, "description": "built-in voice" if ref is None else f"reference {ref}"}
                for k, (lang, ref) in self.v.items()]

    def synthesize(self, text, voice, language, instruct, speed, seed):
        lang, ref = self.v[voice]
        wav = self.model.generate(text, language_id=language or lang, audio_prompt_path=ref)
        return wav.squeeze(0).cpu().numpy(), self.model.sr


app = make_app(ChatterboxBackend())
