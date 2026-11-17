# EduVid generation server

One Docker Compose stack on the 4×L4 GCP VM. Code: `/srv/eduvid/app` (this repo). State: `/srv/eduvid/data`.
Spec: `docs/superpowers/specs/2026-11-11-eduvid-design.md`. Plan: `docs/superpowers/plans/2026-11-11-eduvid-plan-1-foundation.md`.

## Host

| Item | Value |
|---|---|
| OS | Debian 13 (trixie), kernel `6.12.116+deb13-cloud-amd64` |
| GPUs | 4× NVIDIA L4, driver 550.163.01 / CUDA 12.4 |
| Driver install | Debian packages `nvidia-driver` + `nvidia-kernel-dkms` (DKMS module `nvidia-current/550.163.01`) |

### Driver protection (Task 1 Step 1b)

- The driver module is built by **DKMS**, so a kernel update rebuilds it. Kernel packages are **not** held.
- Every installed NVIDIA driver package (`nvidia-*`, `libnvidia-*`, `libcuda1`, `firmware-nvidia-*`) is on
  `apt-mark hold`, because `unattended-upgrades` is enabled and could otherwise replace the 550 driver.
  Check with `apt-mark showhold`. Undo only on purpose: `sudo apt-mark unhold <pkg>`.
- Never run `apt full-upgrade` and never change the NVIDIA driver on this host. Containers must use CUDA ≤ 12.4.

### Setup

```bash
sudo bash infra/bootstrap.sh   # Docker, Compose v2, NVIDIA Container Toolkit, data dirs; safe to re-run
newgrp docker                  # or log out and back in
bash infra/check_host.sh       # prints HOST OK
```

## GPU memory (Task 9)

| GPU | Engines | Used |
|---|---|---|
| 1, 2 | render-worker-1, render-worker-2 (Chrome WebGL + NVENC, 3 renderers each) | per render |
| 0 | tts-omnivoice + tts-kokoro (onnxruntime CUDA) + asr-whisperx (large-v3 fp16, hi/en aligners) | 8089 MiB of 23034 (limit 21 GB) |
| 3 | tts-indicf5 (production: the studio's default voice) + benchmark candidates (`--profile bench`, stop with `docker compose --profile bench stop tts-chatterbox tts-veena tts-parler`) tts-chatterbox + tts-veena (bf16) + tts-parler | 17012 MiB |

## ASR note

Whisper large-v3 writes Hinglish loanwords in Latin script ("Cylinder का Surface Area 2π") unless it is given a
Devanagari prompt, and writes numbers as digits. Callers pass a prompt (see `engines/asr-whisperx/tests`), and
`textmetrics.cer_spoken` reads digits/symbols as spoken words when comparing to the script.

## Run it

| Task | Command |
|---|---|
| Start / update everything | `make up` (also runs on boot via `eduvid.service`) |
| Stop | `make down` |
| Status | `make ps` |
| Logs | `make logs` or `docker compose logs -f <service>`; job logs in MinIO at `<out_prefix>log.txt` / `logs/job-<id>.txt` |
| Schema migrations | `make migrate` |
| Unit tests | `make test` (common), `docker compose run --rm speech-api python -m pytest -q tests`, same for `voice-worker` and `render-worker-1` |
| Live tests (GPU) | `make test ARGS="-s tests/integration/test_voice_area_volume.py"` then `…/test_render_area_volume.py` |
| Acceptance | `bash infra/acceptance.sh` (public HTTPS) or `ACCEPTANCE_BASE_URL=http://speech-api:8000 bash infra/acceptance.sh` |
| Benchmark candidates | `docker compose --profile bench up -d`, then `tests/bench/tts_bench.py` (see `docs/tts-benchmark.md`) |

### API keys (speech API)

```bash
docker compose run --rm speech-api python manage_keys.py create --name my-app --scopes tts,stt
docker compose run --rm speech-api python manage_keys.py list
docker compose run --rm speech-api python manage_keys.py revoke --name my-app
```

The key is printed once; only its hash is stored. Outside apps call `https://$DOMAIN/speech/v1/audio/speech`,
`/v1/audio/transcriptions` and `/v1/audio/align` with `Authorization: Bearer <key>`. The pipeline's own key
(`--pipeline`) is `PIPELINE_API_KEY` in `.env`.

## EduVid Studio (video builder + NCE player)

Spec: `docs/superpowers/specs/2026-11-12-eduvid-studio-design.md`. Service `studio` (CPU) at `https://$DOMAIN/studio/`.

| Item | Where |
|---|---|
| Builder (login: `STUDIO_PASSWORD` in `.env`) | `/studio/` → script review → build; `/studio/library`, `/studio/compare` |
| Player (public link, no login) | `/studio/watch/<video id>[?mode=template\|llm]` |
| Script LLM | OpenRouter, model picked per video (`OPENROUTER_API_KEY` in `.env`, then `docker compose up -d studio`) |
| NCERT content | GyanSetu Postgres, read-only (`NCERT_DATABASE_URL`): books → chapters → sections → teaching units (`assembled_context`) |
| Default voice | `indicf5:ref-female` (best spoken CER in `docs/tts-benchmark.md`, MIT); English `kokoro:am_michael`. Change per video. |
| Render style | `engine/styles/nce-lesson/` (NCE design kit tokens/fonts/Bal Krishna, MathJax for LaTeX). Template scenes + LLM-written `draw(ctx, t, A)` scenes that fall back to the template if they throw or are slow. |
| Pipeline | studio writes the script (OpenRouter) → `voice` → `words` (voice-worker) → LLM scene code (studio) → `render` per visual mode (render-worker) → manifest + poster (studio). State in `studio_videos` / `studio_events`. |
| Files | MinIO `studio/<id>/voice/…`, `studio/<id>/<mode>/draft.mp4`, `manifest.json`, `poster.jpg`, `sheet.jpg`, `log.txt` |
| Tests | `docker compose exec studio python -m pytest -q tests` |

The IndicF5 engine is in the `bench` profile (GPU 3): if it is stopped, start it with
`docker compose --profile bench up -d tts-indicf5` (the gateway serves it while `ENGINE_INDICF5_URL` is set).

### Jobs

`voice` and `words` run in `voice-worker` (CPU, calls the gateway); `render` runs in `render-worker-1/2` (GPU 1/2).
Payloads: `services/voice-worker/voice_worker/main.py` and `services/render-worker/render_worker/render.py`.
A voice is `"<model>:<voice id>"`, e.g. `omnivoice:hinglish-female` or `kokoro:hf_alpha`.

## WebGL on the L4 (Task 13, spec risk #3)

Headless Chrome (Playwright Chromium 131) inside the render container uses the L4 for WebGL:

| `CHROME_FLAGS` | WebGL renderer | 3 browsers per GPU |
|---|---|---|
| `--use-gl=angle --use-angle=gl-egl` (**used**) | `ANGLE (NVIDIA Corporation, NVIDIA L4/PCIe/SSE2, OpenGL ES 3.2)` | works |
| `--use-angle=vulkan --enable-features=Vulkan --disable-vulkan-surface` | `ANGLE (NVIDIA, Vulkan 1.3.277 (NVIDIA L4))` | **fails**: 2nd browser loses its WebGL context |
| `--use-gl=egl`, or no flags | SwiftShader (software) | — |

Needs `NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics,video` and the NVIDIA EGL/Vulkan vendor files baked into
the image. The worker probes at start and logs `ready: webgl …`; if no flag set reaches the GPU it logs
`WARNING software GL` and renders at lower 3D resolution. NVENC (`h264_nvenc`) works with the apt ffmpeg 4.4.

The worker runs as user `render` (uid 1001, gid 1004: the host owner of `/srv/eduvid/data`) so Chrome keeps its
sandbox, because scenes run LLM-written code. Docker's default seccomp profile blocks the namespaces that sandbox needs;
compose gives the render workers `infra/seccomp/chrome.json` (Docker's default profile plus `clone`/`unshare`/`setns`).
Render workers get only the database and object-store credentials (`infra/check_secrets.sh` enforces this).

Measured on `area-volume` (45.9 s, 1080×1920): **draft 50 s** (JPEG frames, NVENC, 3 browsers), **final 266 s**
(PNG frames, x264 slow CRF 14).

## Operations

- **Alerts:** `infra/alert.sh` writes to syslog (`journalctl -t eduvid`), `/srv/eduvid/data/alerts.log` and, if set,
  `ALERT_WEBHOOK_URL` in `.env` (an ntfy topic URL, or a Slack / Google Chat / Discord incoming webhook).
- **Monitor:** `infra/monitor.sh` from hariom's crontab every 5 min: alerts once per new problem: a container that
  restarted, is unhealthy or is down; failed jobs and studio videos; a failed or missing (older than 36 h) backup.
- **Disk alarm:** `infra/disk_alarm.sh` from hariom's crontab every 15 min; over 80 % it alerts (at most every 6 h).
- **Backups:** nightly `pg_dump` (keep 14) + restore test, and a tar of the MinIO data (keep 7) in
  `/srv/eduvid/data/backups` (`eduvid-backup.timer`, 02:30 IST). Those copies are on the same disk. The off-site GCS
  copy is **off for now** (`BACKUP_SKIP_GCS=1` in the unit) until the bucket exists; spec §10 wants it nightly.
- **Deploy:** this directory is a checkout of `github.com/Hariomkr147/Eduvid` (`main`): commit, push, then `make up`.
- **CI:** `.github/workflows/ci.yml` runs ruff, the compose secrets check and every service's unit tests on each push.
- **Studio:** a failed video's Retry resumes from the failed step (finished narration, timing and renders are reused
  unless the script or voice changed). Deleting a video cancels its queued jobs and deletes its files. Logins are
  limited to 10 wrong passwords per IP (60 in total) per 15 min. Speech API docs are off unless `SPEECH_API_DOCS=1`.
- **Budget alert:** set in GCP Billing → Budgets (owner action).

## Not in this repository

Generated media (narration, renders, test recordings), model weights and database data are not committed.
Models download into `/srv/eduvid/data/models` on first start; Postgres and MinIO state live in `/srv/eduvid/data`.
Secrets go in `.env` (copy `.env.example`). The GPU tests of `engines/asr-whisperx` need two recordings in
`tests/fixtures/`: `hinglish_female.wav` and `english_michael.wav` (24 kHz mono), made with the speech API from the
texts beside them, e.g. `POST /v1/audio/speech` with `omnivoice:hinglish-female` and `kokoro:am_michael`.
