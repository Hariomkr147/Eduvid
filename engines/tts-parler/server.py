"""AI4Bharat Indic Parler-TTS (Apache-2.0; gated on Hugging Face: needs HF_TOKEN with the terms accepted)."""
import os

from eduvid_common.tts_server import Backend, make_app

REPO = os.environ.get("PARLER_REPO", "ai4bharat/indic-parler-tts")
# Hindi speakers from the model card (recommended: Rohit, Divya)
SPEAKERS = {"divya": ("Divya", "female"), "rohit": ("Rohit", "male"), "rani": ("Rani", "female"),
            "aman": ("Aman", "male")}
STYLE = ("{name}'s voice is clear and expressive with a moderate pace, "
         "with a very close recording that has no background noise.")


class ParlerBackend(Backend):
    name = "parler"

    def load(self) -> None:
        import torch
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer

        tok = os.environ.get("HF_TOKEN") or None
        self.torch = torch
        self.model = ParlerTTSForConditionalGeneration.from_pretrained(REPO, token=tok).to("cuda:0")
        self.tok = AutoTokenizer.from_pretrained(REPO, token=tok)
        self.desc_tok = AutoTokenizer.from_pretrained(self.model.config.text_encoder._name_or_path, token=tok)

    def voices(self) -> list[dict]:
        return [{"id": k, "language": "hi", "description": f"{n} ({g}), Indic Parler-TTS"}
                for k, (n, g) in SPEAKERS.items()]

    def synthesize(self, text, voice, language, instruct, speed, seed):
        name = SPEAKERS[voice][0]
        desc = instruct if instruct and name in instruct else STYLE.format(name=name)
        d = self.desc_tok(desc, return_tensors="pt").to("cuda:0")
        p = self.tok(text, return_tensors="pt").to("cuda:0")
        with self.torch.inference_mode():
            gen = self.model.generate(input_ids=d.input_ids, attention_mask=d.attention_mask,
                                      prompt_input_ids=p.input_ids, prompt_attention_mask=p.attention_mask)
        return gen.cpu().float().numpy().squeeze(), self.model.config.sampling_rate


app = make_app(ParlerBackend())
