# TTS benchmark (2026-11-11)

Run: `docker compose --profile bench up -d` then `docker compose run --rm tools python tests/bench/tts_bench.py` (add `--merge --engines x,y` to add engines, `--rescore` to recompute).
Listening report: `python tests/bench/report.py` (published privately as "Hindi TTS Bake-off").

Spoken CER = CER of the Whisper large-v3 transcript (Devanagari prompt) vs the script, reading digits/symbols as their spoken words. 11 Hindi/Hinglish + 2 English sentences x 3 seeds. Indic Parler-TTS and IndicF5 need `HF_TOKEN` in `.env` and the account must accept each model's terms. IndicF5 voices are synthetic reference clips from Kokoro hf_alpha/hm_omega (`/models/refs/indicf5/ref-*.wav` + `.txt`), so they sound like Kokoro.

| engine | voice | lang | n | errors | mean spoken CER | spoken CER>0.12 | mean raw CER | median RTF | median latency s | chars/s |
|---|---|---|---|---|---|---|---|---|---|---|
| omnivoice | hinglish-female | hi | 33 | 0 | 0.079 | 7/33 | 0.120 | 0.36 | 1.38 | 15.5 |
| omnivoice | hinglish-male | hi | 33 | 0 | 0.068 | 5/33 | 0.114 | 0.36 | 1.37 | 15.8 |
| kokoro | hf_alpha | hi | 33 | 0 | 0.067 | 3/33 | 0.109 | 0.05 | 0.23 | 13.0 |
| kokoro | hm_omega | hi | 33 | 0 | 0.082 | 5/33 | 0.125 | 0.05 | 0.24 | 12.3 |
| kokoro | am_michael | en | 6 | 0 | 0.000 | 0/6 | 0.000 | 0.05 | 0.20 | 15.0 |
| chatterbox | hindi-default | hi | 33 | 0 | 0.079 | 5/33 | 0.124 | 0.89 | 3.36 | 16.4 |
| chatterbox | english-default | en | 6 | 0 | 0.000 | 0/6 | 0.000 | 0.90 | 3.03 | 18.0 |
| veena | kavya | hi | 33 | 0 | 0.088 | 8/33 | 0.121 | 2.62 | 10.28 | 14.7 |
| veena | agastya | en | 6 | 0 | 0.000 | 0/6 | 0.000 | 2.61 | 9.46 | 16.9 |
| veena | maitri | hi | 33 | 0 | 0.106 | 10/33 | 0.142 | 2.61 | 10.70 | 14.4 |
| parler | divya | hi | 33 | 0 | 0.098 | 10/33 | 0.132 | 1.56 | 8.55 | 11.2 |
| parler | divya | en | 6 | 0 | 0.000 | 0/6 | 0.000 | 1.56 | 8.11 | 10.9 |
| parler | rohit | hi | 33 | 0 | 0.081 | 6/33 | 0.122 | 1.56 | 7.56 | 12.5 |
| parler | rohit | en | 6 | 0 | 0.000 | 0/6 | 0.000 | 1.57 | 7.76 | 12.4 |
| indicf5 | ref-female | hi | 33 | 0 | 0.048 | 2/33 | 0.093 | 1.16 | 5.93 | 12.2 |
| indicf5 | ref-male | hi | 33 | 0 | 0.055 | 5/33 | 0.099 | 1.19 | 6.47 | 11.6 |

| engine | warm-up s | GPU MB (reserved) | peak GPU MB |
|---|---|---|---|
| omnivoice | 1.41 | 2526 | 2526 |
| kokoro | 0.62 | 0 | 0 |
| chatterbox | 14.43 | 3790 | 3790 |
| veena | 3.99 | 7318 | 7318 |
| parler | 2.65 | 7240 | 7240 |
| indicf5 | 4.47 | 1558 | 1558 |
