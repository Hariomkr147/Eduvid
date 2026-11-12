"""Maya Research Veena (licence unclear: card says apache-2.0 but is also tagged "proprietary").

Llama-style LM emitting SNAC 24 kHz codes. Prompt/token layout and decoding follow the model card;
weights load in bf16 (no 4-bit) on the GPU.
"""
import os

from eduvid_common.tts_server import Backend, make_app

REPO = os.environ.get("VEENA_REPO", "maya-research/veena-tts")
SPEAKERS = {"kavya": "female", "agastya": "male", "maitri": "female", "vinaya": "female"}
START_OF_SPEECH, END_OF_SPEECH = 128257, 128258
START_OF_HUMAN, END_OF_HUMAN = 128259, 128260
START_OF_AI, END_OF_AI = 128261, 128262
AUDIO_BASE = 128266
MAX_NEW_TOKENS = int(os.environ.get("VEENA_MAX_NEW_TOKENS", "4096"))  # card caps at 700 (~8 s); we allow longer


class VeenaBackend(Backend):
    name = "veena"

    def load(self) -> None:
        import torch
        from snac import SNAC
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        tok = os.environ.get("HF_TOKEN") or None
        self.model = AutoModelForCausalLM.from_pretrained(REPO, torch_dtype=torch.bfloat16, device_map="cuda:0",
                                                          trust_remote_code=True, token=tok).eval()
        self.tok = AutoTokenizer.from_pretrained(REPO, trust_remote_code=True, token=tok)
        self.snac = SNAC.from_pretrained("hubertsiuzdak/snac_24khz").eval().to("cuda:0")

    def voices(self) -> list[dict]:
        return [{"id": k, "language": "hi", "description": f"Veena speaker {k} ({g})"} for k, g in SPEAKERS.items()]

    def _decode(self, codes: list[int]):
        torch = self.torch
        n = len(codes) // 7
        codes = codes[: n * 7]
        if n == 0:
            raise ValueError("no audio tokens generated")
        l0, l1, l2 = [], [], []
        for f in range(n):
            c = [codes[f * 7 + i] - AUDIO_BASE - i * 4096 for i in range(7)]
            if any(not 0 <= x < 4096 for x in c):
                raise ValueError("audio token out of range")
            l0.append(c[0])
            l1 += [c[1], c[4]]
            l2 += [c[2], c[3], c[5], c[6]]
        hier = [torch.tensor(x, dtype=torch.int32, device="cuda:0").unsqueeze(0) for x in (l0, l1, l2)]
        with torch.inference_mode():
            audio = self.snac.decode(hier)
        return audio.squeeze().clamp(-1, 1).float().cpu().numpy()

    def synthesize(self, text, voice, language, instruct, speed, seed):
        torch = self.torch
        prompt = self.tok.encode(f"<spk_{voice}> {text}", add_special_tokens=False)
        ids = [START_OF_HUMAN, *prompt, END_OF_HUMAN, START_OF_AI, START_OF_SPEECH]
        x = torch.tensor([ids], device="cuda:0")
        max_new = min(int(len(text) * 1.3) * 7 + 21, MAX_NEW_TOKENS)
        with torch.inference_mode():
            out = self.model.generate(x, attention_mask=torch.ones_like(x), max_new_tokens=max_new, do_sample=True,
                                      temperature=0.4, top_p=0.9, repetition_penalty=1.05,
                                      pad_token_id=self.tok.pad_token_id or END_OF_AI,
                                      eos_token_id=[END_OF_SPEECH, END_OF_AI])
        gen = out[0, len(ids):].tolist()
        codes = [t for t in gen if AUDIO_BASE <= t < AUDIO_BASE + 7 * 4096]
        return self._decode(codes), 24000


app = make_app(VeenaBackend())
