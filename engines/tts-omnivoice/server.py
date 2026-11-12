"""OmniVoice (k2-fsa). Code Apache-2.0, weights CC-BY-NC: internal / non-commercial use only."""
import os

from eduvid_common.tts_server import Backend, make_app

REPO = os.environ.get("OMNIVOICE_REPO", "k2-fsa/OmniVoice")
# voice id -> (language, instruct)
VOICES = {
    "hinglish-female": ("Hindi", "female, indian accent"),
    "hinglish-male": ("Hindi", "male, indian accent"),
    "hindi-female": ("Hindi", "female"),
    "hindi-male": ("Hindi", "male"),
    "english-female": ("English", "female, indian accent"),
    "english-male": ("English", "male, indian accent"),
}


class OmniVoiceBackend(Backend):
    name = "omnivoice"

    def load(self) -> None:
        import torch
        from omnivoice import OmniVoice

        self.model = OmniVoice.from_pretrained(REPO, device_map="cuda:0", dtype=torch.float16)

    def voices(self) -> list[dict]:
        return [{"id": k, "language": lang.lower(), "description": f"voice design: {ins}"}
                for k, (lang, ins) in VOICES.items()]

    def synthesize(self, text, voice, language, instruct, speed, seed):
        lang, ins = VOICES[voice]
        kw = {"speed": speed} if speed != 1.0 else {}
        audio = self.model.generate(text=text, language=language or lang, instruct=instruct or ins, **kw)
        return audio[0], 24000


app = make_app(OmniVoiceBackend())
