# Model and library licences

Checked 2026-11-11 from the official repo and model-card pages (links below). Not legal advice.

> **⚠ Decision needed before Task 8: OmniVoice weights are NOT licensed for commercial use.**
> The OmniVoice model card says: *"The pre-trained model is licensed under the CC-BY-NC due to constraints
> from its training data (e.g., Emilia)."* The code is Apache-2.0, but the weights are non-commercial.
> Options: (a) keep OmniVoice for **internal / non-commercial use only** and mark it `"commercial": false`;
> (b) switch the Hindi/Hinglish voice to a commercially licensed candidate: **AI4Bharat Indic Parler-TTS**
> (Apache-2.0) or **IndicF5** (MIT, with a cloning-consent term of use).
>
> **The MMS forced aligner (`torchaudio.pipelines.MMS_FA`) is also CC-BY-NC 4.0**, so the `/align` fallback
> path has the same restriction.

| Component | Code licence | Weights licence | Commercial use? | Source | Notes |
|---|---|---|---|---|---|
| OmniVoice (`k2-fsa/OmniVoice`) | Apache-2.0 | **CC-BY-NC** (no version given) | **no** (weights) | [GitHub](https://github.com/k2-fsa/OmniVoice), [HF card](https://huggingface.co/k2-fsa/OmniVoice) | NC because of the training data (Emilia). |
| Kokoro-82M | — | Apache-2.0 | yes | [HF card](https://huggingface.co/hexgrad/Kokoro-82M) | The card welcomes commercial deployment. Training data is listed as permissive (CC BY 3.0/4.0 parts plus synthetic audio). |
| kokoro-onnx | MIT | Apache-2.0 (same Kokoro model, `kokoro-v1.0.onnx`, `voices-v1.0.bin`) | yes | [GitHub](https://github.com/thewh1teagle/kokoro-onnx) | |
| WhisperX | BSD-2-Clause | — | yes | [GitHub](https://github.com/m-bain/whisperX) | Diarization (not used) needs pyannote models with their own licences. |
| faster-whisper | MIT | — | yes | [GitHub](https://github.com/SYSTRAN/faster-whisper) | |
| Whisper large-v3 | — | Apache-2.0 (`openai/whisper-large-v3`); CTranslate2 conversion `Systran/faster-whisper-large-v3` tagged MIT | yes | [HF](https://huggingface.co/openai/whisper-large-v3), [HF](https://huggingface.co/Systran/faster-whisper-large-v3) | Attribute OpenAI. |
| WhisperX aligner, `en` = torchaudio `WAV2VEC2_ASR_BASE_960H` | — | **unclear** (the torchaudio page states no licence) | unclear | [alignment.py](https://github.com/m-bain/whisperX/blob/main/whisperx/alignment.py), [torchaudio pipelines](https://docs.pytorch.org/audio/stable/pipelines.html) | fairseq wav2vec2 base, LibriSpeech 960h. |
| WhisperX aligner, `hi` = `theainerd/Wav2Vec2-large-xlsr-hindi` | — | **unclear** (no licence on the card) | unclear | [HF card](https://huggingface.co/theainerd/Wav2Vec2-large-xlsr-hindi) | Base model `facebook/wav2vec2-large-xlsr-53` is Apache-2.0; the fine-tune is unlicensed. |
| MMS forced aligner (`torchaudio.pipelines.MMS_FA`) | CC-BY-NC 4.0 | **CC-BY-NC 4.0** | **no** | [torchaudio docs](https://docs.pytorch.org/audio/stable/generated/torchaudio.pipelines.MMS_FA.html), [fairseq MMS](https://github.com/facebookresearch/fairseq/tree/main/examples/mms) | |
| uroman | MIT-style, with an acknowledgement clause | — | yes | [LICENSE](https://github.com/isi-nlp/uroman/blob/master/LICENSE.txt) | "Any publication of projects using uroman shall acknowledge its use." |
| *Candidate:* AI4Bharat Indic Parler-TTS | — | Apache-2.0 | yes (per card) | [HF card](https://huggingface.co/ai4bharat/indic-parler-tts) | Gated. Training sets include CC BY 4.0 data (attribution). |
| *Candidate:* AI4Bharat IndicF5 | — | MIT | yes, with a term of use | [HF card](https://huggingface.co/ai4bharat/IndicF5) | Gated. "Only clone voices for which you have explicit permission." |

## What `/v1/models` reports

| Model id | `commercial` |
|---|---|
| `omnivoice` | `false` (CC-BY-NC weights) |
| `kokoro` | `true` |
| `whisper-large-v3` | `true` |
| align (`wav2vec2` path) | `false` until the aligner licences are clarified |
| align (`mms` path) | `false` (CC-BY-NC 4.0) |

## Determinism notes (Task 8)

_To be filled in after the TTS engine tests run._
