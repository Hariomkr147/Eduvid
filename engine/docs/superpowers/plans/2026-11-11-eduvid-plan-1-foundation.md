# EduVid Plan 1: Foundation (M0–M3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the 4×L4 GCP VM into an always-on generation server. It runs Postgres + MinIO storage, a Postgres job queue, a shared OpenAI-compatible speech API (OmniVoice, Kokoro, WhisperX transcription and forced alignment) on GPU 0, and GPU render workers that make the existing `faceless-shorts` videos at full quality.

**Architecture:** One Docker Compose stack in `/srv/eduvid` with all state in `/srv/eduvid/data`. Each speech engine runs in its **own container** on GPU 0, because the TTS and ASR libraries have conflicting dependencies. A CPU-only `speech-api` gateway in front of them handles auth, usage logging, limits and fair scheduling. Render workers on GPUs 1 and 2 claim jobs from Postgres and run the `faceless-shorts` Node engine in headless Chrome with GPU WebGL. Every service reaches the others only through URLs set in the environment, so storage can move to another server later.

**Tech Stack:**
- **Debian 13 (trixie)** host (Debian 12 and Ubuntu 22.04/24.04 also accepted) + Docker Engine + NVIDIA Container Toolkit. The host OS only affects Docker and the toolkit; every service runs in Ubuntu-based CUDA images.
- Postgres 16, MinIO
- Python 3.11 (FastAPI, psycopg 3, boto3, pytest)
- Base image `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04`, PyTorch 2.5.x cu124
- WhisperX, OmniVoice, kokoro-onnx
- Node 22, Chrome for Testing (via Playwright), ffmpeg with NVENC
- Caddy

**Spec:** `docs/superpowers/specs/2026-11-11-eduvid-design.md` (approved with changes 2026-11-11). Read it before starting.

## Global Constraints

- Host: GCP `g2-standard-48`, `asia-southeast1-c`, 4× L4 (23 GB), **driver 550.163.01 / CUDA 12.4**. Container CUDA must be **≤ 12.4**. Use `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04` and PyTorch `+cu124` wheels.
- GPU roles: **GPU 0** = speech engines; **GPUs 1 and 2** = render workers; **GPU 3** = QA (Plan 4) and overflow rendering. Assign them with compose `device_ids`, never by sharing.
- GPU containers that render or encode set `NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics,video`, which is needed for WebGL (EGL/Vulkan) and NVENC.
- All state lives in `/srv/eduvid/data/{postgres,minio,backups,scratch}`. The app code is a git repo at `/srv/eduvid/app`.
- Services use only `DATABASE_URL`, `S3_ENDPOINT`, `S3_BUCKET=eduvid`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `SPEECH_API_URL` and `ENGINE_*_URL` from `/srv/eduvid/app/.env` (mode **600**, never committed; `.env.example` is committed).
- Exposed to the internet: **443** (Caddy), and **22** only from the owner's IP. Postgres, MinIO and the engines are never published on host ports. Admin access to them is through an SSH tunnel.
- `DOMAIN` comes from `.env`. Default `<static-ip-with-dashes>.sslip.io`. Caddy serves `https://$DOMAIN/` (later the review app) and `https://$DOMAIN/speech/v1/*` (the gateway).
- The object key layout is fixed: `class-{n}/{subject}/{chapter_slug}/lesson-{nn}/seg-{nn}/v{n}/{language}/{file}` and `class-{n}/{subject}/{chapter_slug}/lesson-{nn}/{language}/lesson.mp4`.
- Speech: audio inside the pipeline is **24 kHz mono 16-bit WAV**. Voice-to-script check: **CER > 0.12 → re-generate with a new seed, up to 3 times**, then flag. Text is normalised to **NFC** before any comparison.
- Speakable text for Hinglish and Hindi must contain no symbols, digits or Latin letters. English speakable text must contain no math symbols.
- Jobs: claimed with `FOR UPDATE SKIP LOCKED`, **max 3 attempts**, backoff **30 s × 2^(attempt−1)**, then `failed` with `log_key`.
- Final audio target **−14 LUFS**. This is already done by `engine/shared/tools/mix.py`, so don't re-implement it.
- Python 3.11, `ruff` + `pytest`. Each Python service has its own `requirements.txt` with **pinned** versions, written after the versions are proven to work together.
- NCERT: facts and topic order only. Never copy textbook text or figures (this matters for test fixtures too).

## Review Focus

1. **Very long TTS input from outside apps** (for example 20,000 characters): expect `413` with `{"error":"input too long","max_chars":4000}`, not a timeout. Test in Task 11.
2. **Outside apps flooding the API while the pipeline is rendering:** pipeline calls still go through, outside calls get at least 1 in 3 engine slots, and a full queue (32 waiting per engine) returns `429` with `Retry-After`. Test in Task 11.
3. **Odd audio uploads** (mp3, m4a, stereo, 48 kHz, 0-byte or corrupt): anything ffmpeg can decode is normalised to 16 kHz mono for ASR. Empty or corrupt files return `400` with a clear message. Test in Task 9.
4. **An engine crashes or runs out of GPU memory:** the gateway returns `503 {"error":"engine unavailable","engine":...}` within 5 s, `/health` shows the engine down, and Docker restarts the container. Test in Task 11.
5. **A worker crashes mid-render and leaves frames behind:** the worker deletes its `scratch/<job_id>` folder on success, failure and **startup** (orphans), and the job is returned to the queue when its lock expires. Test in Tasks 5 and 13.

---

## File Structure

```
/srv/eduvid/app/                      (git repo)
  .env.example  .gitignore  compose.yaml  Makefile  README.md
  infra/
    bootstrap.sh            host setup (Docker, NVIDIA toolkit, dirs); safe to re-run
    check_host.sh           checks M0: GPUs visible in containers, dirs, permissions
    caddy/Caddyfile
    backup/backup.sh        nightly pg_dump + mc mirror → GCS
    backup/restore_test.sh  restores the latest dump into a throwaway postgres and counts tables
    systemd/eduvid.service  compose up on boot
    systemd/eduvid-backup.{service,timer}
  db/
    migrations/0001_init.sql
    migrate.py              applies migrations in order and records them in schema_migrations
  common/                   Python package eduvid_common (installed into every Python image)
    pyproject.toml
    eduvid_common/settings.py  db.py  storage.py  keys.py  jobs.py  textmetrics.py  speakable.py  audio.py
    tests/
  engines/
    tts-omnivoice/  Dockerfile requirements.txt server.py tests/
    tts-kokoro/     Dockerfile requirements.txt server.py tests/
    asr-whisperx/   Dockerfile requirements.txt server.py tests/
  services/
    speech-api/     Dockerfile requirements.txt speech_api/{app.py,auth.py,scheduler.py,routes.py,errors.py} tests/
    voice-worker/   Dockerfile voice_worker/{main.py,voice.py,words.py} tests/
    render-worker/  Dockerfile render_worker/{main.py,render.py} tests/
  engine/                   copied faceless-shorts (scripts/, shared/, styles/, kaggle/); changes only under engine/
  tests/integration/        end-to-end tests marked @pytest.mark.gpu
  docs/
    superpowers/specs/2026-11-11-eduvid-design.md
    superpowers/plans/2026-11-11-eduvid-plan-1-foundation.md
    licences.md
```

**Internal engine contract** (HTTP, Docker network only):
- **TTS engines:** `POST /synthesize` with JSON `{text: str, voice: str, language: str|null, instruct: str|null, speed: float=1.0, seed: int|null}` → `audio/wav` (24 kHz mono 16-bit). `GET /voices` → `[{id, language, description}]`. `GET /health` → `{ok, model, gpu_mem_mb}`.
- **ASR engine:**
  - `POST /transcribe` (multipart `file`, `language`, `prompt`) → `{text, language, segments:[{start,end,text,words:[{word,start,end,score}]}]}`
  - `POST /align` (multipart `file`, `words` JSON list[str], `language`) → `{words:[{word,start,end,score}], method:"wav2vec2"|"mms"}`
  - `GET /health`

---

### Task 1: Host bootstrap (M0)

**Files:**
- Create: `infra/bootstrap.sh`, `infra/check_host.sh`, `.gitignore`, `README.md`

**Interfaces:**
- Produces: the host has Docker, Compose v2, the NVIDIA Container Toolkit and `/srv/eduvid/{app,data/{postgres,minio,backups,scratch}}` owned by `hariom`. `check_host.sh` exits 0 only when everything below holds.

- [ ] **Step 1: Check prerequisites and stop if they fail.** Run `sudo -n true && echo SUDO_OK; head -2 /etc/os-release; nvidia-smi -L`. Expected: `SUDO_OK`, an `ID` of **debian (12 or 13)** or **ubuntu (22.04 or 24.04)**, and 4 lines `GPU n: NVIDIA L4`. **If there's no sudo, or it's another OS, stop and ask Hariom.** *(Checked 2026-11-11: Debian 13 trixie, sudo OK, 4× L4, driver 550.163.01 / CUDA 12.4, 2.8 TB free.)*
- [ ] **Step 1b: Protect the GPU driver from kernel updates.**
  - Record how the driver was installed: `dpkg -l | grep -Ei 'nvidia-(driver|kernel)|cuda-drivers'; dkms status; uname -r`.
  - If the driver is **not** in DKMS (for example GCP's runfile installer), a kernel upgrade followed by a reboot would break the GPUs. Run `sudo apt-mark hold $(dpkg -l 'linux-image-*' 'linux-headers-*' | awk '/^ii/{print $2}')`.
  - Never run `apt full-upgrade` or change the NVIDIA driver in this plan. Write the result in `README.md`.
- [ ] **Step 2: Write `infra/check_host.sh` (the failing test).** It checks:
  - `docker compose version` works.
  - `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi -L | grep -c "NVIDIA L4"` prints `4`.
  - All 4 data dirs exist and are writable by `hariom`.
  - At least 2 TB is free on `/`.

  It prints `HOST OK` or the first failing check.
- [ ] **Step 3: Run it.** `bash infra/check_host.sh`. Expected: FAIL (Docker not installed yet).
- [ ] **Step 4: Write `infra/bootstrap.sh`.** It's safe to re-run and does the following:
  - Docker Engine from Docker's official apt repo, **chosen by `ID` in `/etc/os-release`**. For Debian that's `https://download.docker.com/linux/debian` with suite = `VERSION_CODENAME` (`trixie`), in the deb822 `docker.sources` format from docs.docker.com; for Ubuntu it's the `linux/ubuntu` URL. Packages: `docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin`.
  - NVIDIA Container Toolkit from NVIDIA's apt repo (the generic `stable/deb` list from `nvidia.github.io/libnvidia-container`, which works on Debian), **without touching the driver packages**, then `nvidia-ctk runtime configure --runtime=docker` and restart Docker.
  - Add `hariom` to the `docker` group.
  - Create the data dirs.
  - `sudo systemctl enable docker`.
- [ ] **Step 5: Run it.** `sudo bash infra/bootstrap.sh && newgrp docker`, then `bash infra/check_host.sh`. Expected: `HOST OK`.
- [ ] **Step 6: Get the code in.**
  1. `git init /srv/eduvid/app`.
  2. Copy the `faceless-shorts` folder from Hariom's PC into `engine/`. Hariom runs this in Git Bash on Windows: `scp -r ~/Documents/faceless-shorts hariom@<VM_IP>:/srv/eduvid/app/engine`. Or ask him for a private git URL.
  3. Remove `engine/_backup*.tar.gz`, `engine/.env`, `engine/kaggle_output`, and the `renders/` and `review/` folders under `engine/videos/*`.
  4. Add `.gitignore` covering `.env`, `data/`, `**/renders/`, `**/review/`, `__pycache__/` and `*.wav` (except `tests/fixtures/*.wav`).
- [ ] **Step 7: Commit.** `git add -A && git commit -m "chore: host bootstrap, host check, engine import"`

---

### Task 2: Compose skeleton, settings, HTTPS front door (M0)

**Files:**
- Create: `compose.yaml`, `.env.example`, `Makefile`, `infra/caddy/Caddyfile`, `common/pyproject.toml`, `common/eduvid_common/settings.py`, `common/tests/test_settings.py`

**Interfaces:**
- Produces: `eduvid_common.settings.Settings` (pydantic-settings) with the fields `database_url, s3_endpoint, s3_bucket="eduvid", s3_access_key, s3_secret_key, speech_api_url, engine_omnivoice_url, engine_kokoro_url, engine_asr_url, scratch_dir="/data/scratch", domain`, and `get_settings() -> Settings` (cached).
- Produces: Make targets `up`, `down`, `logs`, `test`, `migrate`, `ps`.

- [ ] **Step 1: Failing test.** `test_settings_reads_env` sets `DATABASE_URL=postgresql://u:p@db:5432/eduvid` and `S3_ENDPOINT=http://minio:9000` in `monkeypatch.setenv` and asserts `get_settings().database_url` and `.s3_bucket == "eduvid"`. `test_missing_required_raises` (with `DATABASE_URL` unset) expects `ValidationError`.
- [ ] **Step 2: Run.** `cd common && pip install -e .[test] && pytest -q`. Expected: FAIL (import error).
- [ ] **Step 3: Implement `settings.py`.** Use `pydantic_settings.BaseSettings` with `env_file=None` (compose injects the values) and `@lru_cache` on `get_settings`.
- [ ] **Step 4: Run.** `pytest -q`. Expected: PASS.
- [ ] **Step 5: Set up the stack config.**
  - **`.env.example`** lists every variable with placeholder values plus `DOMAIN=` and `ACME_EMAIL=`.
  - **`compose.yaml`** defines the `caddy` service only for now (ports `443:443` and `80:80` for the ACME challenge; volumes for the Caddyfile and `caddy_data`), plus a named network `eduvid`.
  - **The Caddyfile:**
    - `{$DOMAIN}` → `respond "eduvid ok" 200` at `/`.
    - `handle_path /speech/*` → `reverse_proxy speech-api:8000`. It's commented out until Task 11.
- [ ] **Step 6: Network.**
  - Reserve a static external IP for the VM, and open firewall ports 443 and 80 to anywhere and 22 only to Hariom's IP. **Print these `gcloud` commands for Hariom to run in Cloud Shell** if the VM's service account lacks permission:
    - `gcloud compute addresses create eduvid-ip --region asia-southeast1`
    - Assign the address to the instance.
    - `gcloud compute firewall-rules create eduvid-https --allow tcp:443,tcp:80 --target-tags eduvid`
    - Tag the instance `eduvid`.
  - If `DOMAIN` is empty, set it to `<ip-with-dashes>.sslip.io`.
- [ ] **Step 7: Verify.** `cp .env.example .env && chmod 600 .env` (fill in values), `make up`, then `curl -s https://$DOMAIN/`. Expected: `eduvid ok` with a valid certificate (no `-k`).
- [ ] **Step 8: Commit.** `git add -A && git commit -m "feat: compose skeleton, settings, https front door"`

---

### Task 3: Postgres and schema (M1)

**Files:**
- Create: `db/migrations/0001_init.sql`, `db/migrate.py`, `common/eduvid_common/db.py`, `common/tests/test_schema.py`
- Modify: `compose.yaml` (add `postgres:16`, volume `/srv/eduvid/data/postgres`, healthcheck `pg_isready`, no host port)

**Interfaces:**
- Produces: `eduvid_common.db.connect() -> psycopg.Connection` (autocommit off), and `eduvid_common.db.pool() -> psycopg_pool.ConnectionPool`.
- Produces: the tables from spec §4, exactly: `users, chapters, lessons, segments, segment_versions, renders, lesson_renders, comments, approvals, jobs, glossary, api_keys, api_usage, schema_migrations`.
  - **Enumerated values are `text` + `CHECK`**, with the values from spec §4. For example `segments.kind IN ('scene','board','practice')`, `renders.language IN ('hinglish','english','hindi')`, `jobs.type IN ('plan','script','visual','voice','words','check','render','qa','assemble')`, `jobs.status IN ('queued','running','done','failed')`.
  - **Every table** has `id bigserial` and `created_at timestamptz default now()`.
  - **`jobs`** also has `run_after timestamptz default now()` and `locked_until timestamptz`.
- [ ] **Step 1: Failing test.** `test_schema.py` (it uses a `pg_url` fixture pointing at the compose Postgres, through `make test`, which runs tests inside a `python:3.11` container on the `eduvid` network). It covers:
  - `test_all_tables_exist`: the set above is ⊆ `information_schema.tables`.
  - `test_segment_kind_check`: inserting `kind='video'` raises `CheckViolation`.
  - `test_render_unique_per_version_language_quality`: a second insert with the same `(version_id, language, quality)` raises `UniqueViolation`.
- [ ] **Step 2: Run.** `make test ARGS="common/tests/test_schema.py"`. Expected: FAIL (no tables).
- [ ] **Step 3: Implement `0001_init.sql` and `migrate.py`.** `migrate.py` applies `db/migrations/*.sql` in order, each in a transaction, and records the filename in `schema_migrations`. Add a `make migrate` target.
- [ ] **Step 4: Run.** `make migrate && make test ARGS="common/tests/test_schema.py"`. Expected: 3 passed.
- [ ] **Step 5: Commit.** `git commit -am "feat: postgres service, schema 0001, migrations"`

---

### Task 4: MinIO and file storage (M1)

**Files:**
- Create: `common/eduvid_common/storage.py`, `common/eduvid_common/keys.py`, `common/tests/test_storage.py`, `common/tests/test_keys.py`
- Modify: `compose.yaml` (add `minio`, volume `/srv/eduvid/data/minio`, plus a one-shot `minio-init` that creates bucket `eduvid` with `mc`)

**Interfaces:**
- Produces:
  - `keys.segment_key(cls: int, subject: str, chapter_slug: str, lesson: int, seg: int, version: int, language: str, filename: str) -> str`
  - `keys.lesson_key(cls, subject, chapter_slug, lesson, language) -> str`
  - `storage.put_file(key: str, path: Path, content_type: str|None=None) -> None`
  - `storage.put_bytes(key: str, data: bytes, content_type: str) -> None`
  - `storage.get_file(key: str, dest: Path) -> Path`
  - `storage.exists(key: str) -> bool`
  - `storage.presigned_url(key: str, expires_s: int = 3600) -> str`
- [ ] **Step 1: Failing tests.**
  - `test_segment_key_layout` asserts `segment_key(9,"maths","ch11-surface-areas",2,4,3,"hinglish","draft.mp4") == "class-9/maths/ch11-surface-areas/lesson-02/seg-04/v3/hinglish/draft.mp4"`.
  - `test_key_rejects_bad_language` (`"french"` → `ValueError`).
  - `test_put_get_roundtrip` (bytes in = bytes out, `exists` is true).
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** `keys.py` is plain string formatting with validation. `storage.py` uses boto3 with `endpoint_url=settings.s3_endpoint` and path-style addressing.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -am "feat: minio service, storage + key layout"`

---

### Task 5: Job queue (M1)

**Files:**
- Create: `common/eduvid_common/jobs.py`, `common/tests/test_jobs.py`

**Interfaces:**
- Produces:
  - `enqueue(type: str, payload: dict, priority: int = 100, run_after: datetime|None = None) -> int`
  - `claim(types: list[str], worker: str, gpu: int|None, lock_s: int = 900) -> Job|None`. This is atomic `UPDATE … WHERE id = (SELECT id … WHERE status='queued' AND run_after<=now() OR (status='running' AND locked_until<now()) ORDER BY priority, id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *`, setting `status='running'`, `attempts=attempts+1`, `locked_until=now()+lock_s`.
  - `heartbeat(job_id: int, lock_s: int = 900) -> None`
  - `complete(job_id: int, result: dict|None = None) -> None`
  - `fail(job_id: int, error: str, log_key: str|None = None, retry: bool = True) -> str`. It returns `'requeued'` or `'failed'`: if `retry` and `attempts < 3` it sets `status='queued'` and `run_after = now() + 30s * 2^(attempts-1)`, else `status='failed'`.
  - The `Job` dataclass has `id, type, payload, attempts, priority`.
- [ ] **Step 1: Failing tests.**
  - `test_claim_returns_oldest_highest_priority`.
  - `test_two_workers_never_claim_same_job`: 20 jobs, 4 threads each claiming until empty; the claimed ids are unique and number 20.
  - `test_fail_backoff_then_failed`: after `fail` once, `run_after ≈ now+30s`; twice, `≈ now+60s`; the third time returns `'failed'`.
  - `test_fail_without_retry_is_final`: `fail(id, "bad input", retry=False)` returns `'failed'` on the first attempt.
  - `test_expired_lock_is_reclaimed`: claim with `lock_s=1`, sleep 1.5 s, claim again returns the same id with `attempts == 2`. This is the crash recovery in Review Focus 5.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement `jobs.py`** with the SQL above, using the connection pool from Task 3.
- [ ] **Step 4: Run.** Expected: 4 passed.
- [ ] **Step 5: Commit.** `git commit -am "feat: postgres job queue with skip-locked claims, backoff, lock expiry"`

---

### Task 6: Backups and restart on boot (M1)

**Files:**
- Create: `infra/backup/backup.sh`, `infra/backup/restore_test.sh`, `infra/systemd/eduvid.service`, `infra/systemd/eduvid-backup.service`, `infra/systemd/eduvid-backup.timer`

**Interfaces:**
- Consumes: `.env` (`BACKUP_GCS_BUCKET=gs://<project>-eduvid-backup`).
- Produces:
  - `backup.sh` writes `pg_dump -Fc` to `/srv/eduvid/data/backups/eduvid-YYYYmmdd-HHMM.dump`, keeps the last 14 locally, then `gsutil -m rsync -r` for dumps and `mc mirror --overwrite` (or `gsutil rsync` of `data/minio`) to the bucket.
  - `restore_test.sh` restores the newest dump into a temporary `postgres:16` container and prints `RESTORE OK tables=<n>`, failing if fewer than 14 tables come back.
- [ ] **Step 1: Create the bucket.** Hariom runs this in Cloud Shell if needed: `gsutil mb -l asia-southeast1 -c nearline gs://<project>-eduvid-backup`.
- [ ] **Step 2: Run** `bash infra/backup/restore_test.sh`. Expected: FAIL (no dump yet).
- [ ] **Step 3: Implement both scripts and the systemd units.** The timer runs daily at 02:30 IST; `eduvid.service` runs `docker compose up -d` in `/srv/eduvid/app` after `docker.service`.
- [ ] **Step 4: Verify.**
  1. `bash infra/backup/backup.sh && bash infra/backup/restore_test.sh` → `RESTORE OK tables=14`.
  2. `sudo systemctl enable --now eduvid.service eduvid-backup.timer`.
  3. `sudo reboot`, then `make ps` shows everything up.
- [ ] **Step 5: Commit.** `git commit -am "feat: nightly backups to GCS, restore test, systemd units"`

---

### Task 7: Licences and engine choice (M2)

**Files:**
- Create: `docs/licences.md`

- [ ] **Step 1: Record the licences.** For **OmniVoice** (`k2-fsa/OmniVoice`, both code and model weights), Kokoro-82M, kokoro-onnx, WhisperX, faster-whisper / Whisper large-v3, the WhisperX Hindi and English wav2vec2 aligners, MMS (`torchaudio` `MMS_FA`), and as candidates AI4Bharat Indic Parler-TTS and IndicF5, record the licence name, link, and the answer to "**commercial use allowed?**" (yes / no / unclear). Read the official repo and model-card pages.
- [ ] **Step 2: Decide.** If OmniVoice weights are **not clearly** licensed for commercial use, write that at the top of `docs/licences.md` and **ask Hariom before Task 8** whether to continue with OmniVoice (internal use only) or switch to a commercially licensed candidate. Engines whose licence is unclear get `"commercial": false` in `/v1/models`.
- [ ] **Step 3: Commit.** `git add docs/licences.md && git commit -m "docs: model licences and commercial-use decision"`

---

### Task 8: TTS engines: OmniVoice and Kokoro (M2)

**Files:**
- Create: `engines/tts-omnivoice/{Dockerfile,requirements.txt,server.py,tests/test_server.py}`, `engines/tts-kokoro/{Dockerfile,requirements.txt,server.py,tests/test_server.py}`, `common/eduvid_common/audio.py`, `common/tests/test_audio.py`
- Modify: `compose.yaml` (add `tts-omnivoice` and `tts-kokoro`, both `device_ids: ["0"]`, `restart: unless-stopped`, healthcheck `GET /health`, model caches on volume `/srv/eduvid/data/models`)

**Interfaces:**
- Consumes: the internal TTS contract above.
- Produces:
  - `audio.to_wav_24k_mono(data: bytes) -> bytes` (via ffmpeg).
  - `audio.duration_s(wav: bytes) -> float`
  - `audio.rms_dbfs(wav: bytes) -> float`
  - `audio.concat_with_gaps(wavs: list[bytes], gaps_s: list[float], lead_s: float, outro_s: float) -> bytes`
- Voices:
  - OmniVoice voice ids `hinglish-female`, `hinglish-male`, `hindi-female`, `hindi-male`, which map to `language="Hindi"` and `instruct="female, indian accent"` or `"male, indian accent"`.
  - Kokoro voice ids are the Kokoro names (`af_heart`, `am_michael`, `bm_george`, …).
- [ ] **Step 1: Failing tests** (`@pytest.mark.gpu`, run inside each container):
  - `test_synthesize_returns_24k_mono_wav`: the request `{"text":"सिलेंडर का सरफेस एरिया टू पाई आर एच होता है।","voice":"hinglish-female"}` returns a wav with sample rate 24000, 1 channel, duration 1.5–8 s and `rms_dbfs > -40`.
  - `test_same_seed_same_audio`: two calls with `seed=7` return byte-identical output. If the model can't do this, assert duration within 2% and note it in `docs/licences.md`.
  - `test_unknown_voice_400`.

  The Kokoro equivalents use `"The curved surface area of a cylinder is two pi r h."` and `am_michael`.
- [ ] **Step 2: Build and run the tests.** `docker compose build tts-omnivoice tts-kokoro && docker compose run --rm tts-omnivoice pytest -q -m gpu`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Each `server.py` is a FastAPI app that loads its model **once at startup** (OmniVoice in fp16 on `cuda:0`; Kokoro through onnxruntime-gpu, falling back to CPU), passes `seed` to the model's generator, and returns `to_wav_24k_mono(...)`.
  - Reuse the OmniVoice call pattern from `engine/scripts/voice.py::omnivoice_engine`.
  - Pin `requirements.txt` once `pip check` passes in the image.
- [ ] **Step 4: Run.** Expected: PASS in both containers. Then save one sample per voice to `tests/fixtures/{hinglish_female,english_michael}.wav`, generated by our own TTS (no copyrighted text), for Task 9.
- [ ] **Step 5: Commit.** `git commit -am "feat: omnivoice and kokoro tts engines on gpu0"`

---

> **Order note:** do **Task 10 before Task 9**. Task 9's tests use `textmetrics.cer`. The numbering stays as is, so references elsewhere keep working.

### Task 9: ASR engine: WhisperX transcription and forced alignment (M2)

**Files:**
- Create: `engines/asr-whisperx/{Dockerfile,requirements.txt,server.py,tests/test_server.py}`
- Modify: `compose.yaml` (`asr-whisperx`, `device_ids: ["0"]`)

**Interfaces:**
- Consumes: `tests/fixtures/hinglish_female.wav` and `english_michael.wav` with their known texts.
- Produces: `/transcribe` and `/align` as in the internal contract. `/align` uses the WhisperX `load_align_model` and `align` functions for `hi` and `en`. If no aligner exists for the language, or the mean score is below 0.3, it falls back to `torchaudio.pipelines.MMS_FA` (with romanised tokens via `uroman`).
- [ ] **Step 1: Failing tests** (`gpu`):
  - `test_align_known_hinglish_text`: align the fixture with its exact word list. It returns one entry per input word, in order, with `start < end`, times increasing, every time inside the clip length, and `method in {"wav2vec2","mms"}`.
  - `test_transcribe_hinglish_cer`: transcribe with `language="hi"`, then `textmetrics.cer(script, text) < 0.12`. This uses `textmetrics.cer` from Task 10, which is done before this task (see the order note).
  - `test_transcribe_english_words_have_times`.
  - `test_odd_formats_normalised`: the same fixture converted to 48 kHz stereo mp3 and to m4a both transcribe, with CER within 0.03 of the WAV.
  - `test_empty_or_corrupt_400`: a 0-byte upload and random bytes both return `400 {"error":"could not decode audio"}`. This is Review Focus 3.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement `server.py`.**
  - Load `large-v3` once (`compute_type="float16"`).
  - Decode every upload with ffmpeg to 16 kHz mono float32. If ffmpeg fails, return 400.
  - Cache aligner models per language.
- [ ] **Step 4: Run.** Expected: PASS. Record the GPU memory use of all three engines together (`nvidia-smi --query-gpu=memory.used --format=csv -i 0`) in `README.md`. It must stay under 21 GB.
- [ ] **Step 5: Commit.** `git commit -am "feat: whisperx transcription + forced alignment engine on gpu0"`

---

### Task 10: Text checks: speakable text, CER, glossary (M2)

**Files:**
- Create: `common/eduvid_common/textmetrics.py`, `common/eduvid_common/speakable.py`, `common/tests/test_textmetrics.py`, `common/tests/test_speakable.py`, `db/migrations/0002_glossary_seed.sql`

**Interfaces:**
- Produces:
  - `textmetrics.normalize(s: str) -> str`: NFC, lowercase, punctuation removed (keeping letters, marks and digits of any script), whitespace collapsed.
  - `textmetrics.cer(ref: str, hyp: str) -> float`: Levenshtein distance on characters of the normalised strings, divided by the reference length.
  - `speakable.violations(text: str, language: str) -> list[str]`. For `hinglish` and `hindi` it flags any Latin letter, ASCII digit or symbol in `=+−×÷/^²³√π∑∫<>%°`. For `english` it flags those math symbols and Unicode super/subscripts.
  - `glossary.lookup(term, subject)` lives in `speakable.py` and reads the `glossary` table.
- [ ] **Step 1: Failing tests.**
  - `cer("सिलेंडर का एरिया", "सिलेंडर का एरिया") == 0`.
  - `cer("टू पाई आर एच", "टू पाई एच") > 0`.
  - NFC handling: a decomposed `"क़"` equals the precomposed one.
  - `violations("A = πr²", "hinglish")` contains `"A"`, `"="`, `"π"`, `"²"`.
  - `violations("पाई आर स्क्वेयर्ड", "hinglish") == []`.
  - `violations("v = u + at", "english")` flags `=` and `+`.
  - `violations("v equals u plus a t", "english") == []`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Seed the glossary in `0002` with about 30 pilot terms (cylinder/सिलेंडर/बेलन, cone, radius, slant height, circumference, velocity, acceleration, displacement, atom, molecule, mole, valency, cell, nucleus, membrane, mitochondria, …), one row per term with every column from spec §4. Write the Hinglish spelling the way it's spoken.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -am "feat: cer, speakable-text checks, glossary seed"`

---

### Task 11: Speech API gateway (M2)

**Files:**
- Create: `services/speech-api/speech_api/{app.py,auth.py,scheduler.py,routes.py,errors.py}`, `services/speech-api/{Dockerfile,requirements.txt}`, `services/speech-api/tests/{conftest.py,test_routes.py,test_scheduler.py,test_auth.py}`, `services/speech-api/manage_keys.py`
- Modify: `compose.yaml` (`speech-api`, CPU only), `infra/caddy/Caddyfile` (enable `/speech/*`)

**Interfaces:**
- Consumes: the internal engine contract; `api_keys` and `api_usage`; `textmetrics`.
- Produces public endpoints (behind `https://$DOMAIN/speech`):
  - `POST /v1/audio/speech` with JSON `{model:"omnivoice"|"kokoro", input, voice, language?, instruct?, speed?=1.0, seed?, response_format:"wav"|"mp3"|"opus"="wav"}`. Max input **4,000 characters → 413**.
  - `POST /v1/audio/transcriptions` (OpenAI multipart: `file`, `model="whisper-large-v3"`, `language?`, `prompt?`, `response_format: json|verbose_json|srt|vtt|text`, `timestamp_granularities[]`). Max upload **100 MB / 60 min**.
  - `POST /v1/audio/align` (multipart `file` and `text`, or a `words` JSON list, plus `language`).
  - `GET /v1/models` (each with `commercial: bool` from Task 7), `GET /v1/voices`, `GET /health` (no auth).
- Auth:
  - Keys look like `ev_<32 urlsafe chars>`. Store `sha256(key)` in `api_keys.hash` with scopes `{"tts","stt"}`, a per-minute `rate_limit`, and an internal flag `pipeline` (bool).
  - The `manage_keys.py create --name X --scopes tts,stt [--pipeline]` command prints the key once.
- Scheduler: `EngineScheduler(engine: str, concurrency: int = 1, max_waiting: int = 32)` with `async submit(call, pipeline: bool) -> result`.
  - **Pipeline requests go first, but when external requests are waiting, every 3rd slot goes to them.**
  - When more than `max_waiting` requests are queued → `429` with `Retry-After: 10`.
  - Engine connection errors or 5xx → `503 {"error":"engine unavailable","engine":name}` within 5 s.
- Errors are always JSON `{"error": str, ...}`. Every successful call writes one `api_usage` row (key, endpoint, model, characters or seconds, ms).
- [ ] **Step 1: Failing tests** (engines replaced by fake ASGI apps in `conftest.py`):
  - `test_no_key_401`, `test_wrong_scope_403`.
  - `test_speech_roundtrip_wav` and `test_speech_mp3_content_type`.
  - `test_input_too_long_413`: 4,001 characters → `413` with `max_chars == 4000`. This is Review Focus 1.
  - `test_transcription_openai_shape`: `verbose_json` has `segments` and `words` when word granularity is requested.
  - `test_align_route`.
  - `test_usage_row_written`.
  - `test_engine_down_503_fast`: the fake engine refuses connections → 503 in under 5 s. This is Review Focus 4.
  - `test_scheduler_fairness`: with 30 pipeline and 6 external calls queued, at least 1 external call completes in every 3 consecutive completions while external calls are waiting. This is Review Focus 2.
  - `test_queue_full_429`.
- [ ] **Step 2: Run.** `docker compose run --rm speech-api pytest -q`. Expected: FAIL.
- [ ] **Step 3: Implement** with FastAPI + httpx (timeouts: connect 2 s, read 300 s). Convert mp3 and opus with ffmpeg in the gateway.
- [ ] **Step 4: Run.** Expected: PASS. Then **live check** (GPU engines up):
  1. `python manage_keys.py create --name curl-test --scopes tts,stt`.
  2. `curl -s https://$DOMAIN/speech/v1/audio/speech -H "Authorization: Bearer $KEY" -H 'content-type: application/json' -d '{"model":"omnivoice","voice":"hinglish-female","input":"सिलेंडर का एरिया"}' -o t.wav && ffprobe t.wav`. Expected: 24 kHz mono.
  3. Transcribe `t.wav` back through `/v1/audio/transcriptions`. Expected: Devanagari text.
- [ ] **Step 5: Commit.** `git commit -am "feat: openai-compatible speech gateway with keys, usage, fair scheduler"`

---

### Task 12: Voice and word-timing jobs (M2)

**Files:**
- Create: `services/voice-worker/voice_worker/{main.py,voice.py,words.py}`, `services/voice-worker/{Dockerfile,requirements.txt}`, `services/voice-worker/tests/{test_voice.py,test_words.py}`
- Modify: `compose.yaml` (`voice-worker`, CPU only; it calls the gateway with a `--pipeline` key from `.env` `PIPELINE_API_KEY`)

**Interfaces:**
- Consumes: `jobs.claim(["voice","words"], …)`, `storage`, `keys`, `textmetrics.cer`, `speakable.violations`, the speech gateway.
- Job payloads:
  - `voice`: `{render_id, script_key, language, voice, out_prefix}`. `script_key` points to a `script.json` in the `faceless-shorts` format extended with `say` (spoken form) and `caps` (Roman, with `@n` anchors) on each line, plus `lead`, `gap`, `outro`.
  - `words`: `{render_id, out_prefix, language}`.
- Produces:
  - `voice.build_narration(script: dict, language: str, voice: str, synth, transcribe) -> tuple[bytes, dict, list[dict]]` returns `(narration_wav, lines_json, take_report)`. It groups lines into sentences using the same rule as `engine/scripts/voice.py`, synthesises each sentence's joined `say`, runs the **voice-to-script check** (CER > 0.12 → retake with seeds 1, 2, 3, then mark `flagged`), and places the cuts inside each sentence by `say` length (they're refined in `words`). `lines_json` has the existing `{duration, lines:[{i,text,start,end,group,group_start,group_end}]}` shape.
  - `words.build_words(narration_wav: bytes, script: dict, lines_json: dict, language: str, align) -> tuple[list[dict], dict]` returns `(words_json, lines_json)`. It runs **forced alignment per sentence** (clipping audio to `group_start..group_end`), moves the inner cuts onto aligned word boundaries (the same rule as `engine/scripts/words.py::refine_cuts`), and outputs `[{w, line, s, e, matched, score}]`, where `w` is the `say` word and `matched = score >= 0.3`.
  - Uploads: `narration.wav`, `lines.json`, `takes.json` and `words.json` go to `out_prefix`. The `renders` row is updated.
  - **Before any synthesis**, `voice` runs `speakable.violations` on every `say` line. Any violation → `fail(job_id, error, retry=False)` with an error naming the line. Bad input isn't worth retrying.
- [ ] **Step 1: Failing tests** (with fake `synth` and `transcribe` and `align` functions):
  - `test_retake_on_high_cer`: fake transcribe returns a garbled first take → `synth` is called twice, `take_report[0]["takes"] == 2`.
  - `test_flag_after_three_bad_takes`: → `take_report[0]["flagged"] is True` (the job still completes).
  - `test_speakable_violation_fails_job_without_retry`.
  - `test_words_shape_and_order`: the output has one item per `say` word, `s` increases, every item is inside its line's window.
  - `test_cut_moves_to_aligned_boundary`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** `main.py` loops `claim → handle → complete/fail`, with a heartbeat every 60 s.
- [ ] **Step 4: Run.** Expected: PASS. Then **live check:**
  1. Convert `engine/videos/area-volume/script.json` into the new format. Its `text` lines are already the Devanagari spoken form, so copy them to `say` and keep `caps`.
  2. Upload it, `enqueue("voice", …)` then `enqueue("words", …)`.
  3. Download `words.json`. Expected: about 140 words, no `matched:false` cluster longer than 3 words, and a voice that is the female Hinglish one.
- [ ] **Step 5: Commit.** `git commit -am "feat: voice + words jobs with voice-to-script check and forced alignment"`

---

### Task 13: Render worker with GPU WebGL and NVENC (M3)

**Files:**
- Create: `services/render-worker/{Dockerfile,requirements.txt}`, `services/render-worker/render_worker/{main.py,render.py}`, `services/render-worker/tests/test_render.py`, `tests/integration/test_render_area_volume.py`
- Modify: `engine/shared/tools/capture.mjs` (add `--nvenc`), then run `bash engine/scripts/sync_shared.sh`. Also `compose.yaml` (`render-worker-1` on `device_ids:["1"]`, `render-worker-2` on `["2"]`, both with `NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics,video`, `shm_size: 8gb`, scratch volume `/srv/eduvid/data/scratch`).

**Interfaces:**
- Consumes: `jobs.claim(["render"], worker, gpu)`. The payload is `{render_id, project_key, data_prefix, quality:"draft"|"final", out_prefix}`. `project_key` is a tar.gz of the engine project in S3 (`index.html`, `src/`, `tools/`, `vendor/`, `fonts/`, `script.json`).
- Produces:
  - `render.run(job, scratch: Path) -> dict` returns `{video_key, sheet_key, check_key, gpu_seconds, webgl_renderer}`. It downloads the project and data (`narration.wav`, `lines.json`, `words.json`), runs `node tools/capture.mjs check` (must say `CHECK OK`), then `cues`, then `python tools/mix.py .`, then `sheet review/all.jpg 0.5 10`, then `video` with `--nvenc` for drafts or `--best` for finals. It uploads `draft.mp4` or `final.mp4`, `sheet.jpg`, `check.txt` and `mix.wav`.
  - `render.webgl_flags() -> str` runs once at worker start: it probes, in order, `--use-angle=vulkan --enable-features=Vulkan --disable-vulkan-surface`, `--use-gl=angle --use-angle=gl-egl` and `--use-gl=egl` using `capture.mjs gpu`, and returns the first whose renderer string contains `NVIDIA`, or `""` meaning software. On `""` it logs `WARNING software GL` and renders with `SOFTWARE_GL=1 QS='&res=0.75&aa=2&shadow=1024' FPS=24`.
  - `JOBS` (Chrome renderers per worker) defaults to **3**.
- `capture.mjs --nvenc` swaps `libx264` for `h264_nvenc -preset p5 -cq 23 -b:v 0`. `--best` stays `libx264 slow CRF 14`.
- [ ] **Step 1: Failing tests.**
  - `test_scratch_cleaned_on_success_and_failure_and_startup`: plant `scratch/999/` before startup → it's gone after `main.startup()`. A failing fake run leaves no `scratch/<id>`. This is Review Focus 5.
  - `test_check_failure_fails_job`: a project with a missing `Wd()` word → `fail()` is called and the log is uploaded.
  - `tests/integration/test_render_area_volume.py` (`gpu`): enqueue a draft render of `area-volume` with Task 12's data. The job finishes in **under 10 minutes**, `webgl_renderer` contains `NVIDIA`, and `ffprobe draft.mp4` shows 1080×1920 with an audio stream and a duration within 0.5 s of `lines.json`.
- [ ] **Step 2: Build.** The Dockerfile starts from `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04` and adds:
  - Node 22 from the nodejs.org binary.
  - `pip install playwright && playwright install --with-deps chromium`.
  - An ffmpeg build **with NVENC**. Verify `ffmpeg -hide_banner -encoders | grep h264_nvenc`; if the apt ffmpeg lacks it, use the BtbN static `ffmpeg-master-latest-linux64-gpl` build.
  - Fonts: `fonts-noto-core`, `fonts-noto-color-emoji`, `fonts-deva`.
  - Python 3.11 with numpy and scipy for `mix.py`.

  Run `docker compose run --rm render-worker-1 bash -lc 'cd /app/engine/videos/area-volume && node tools/capture.mjs gpu'` with each flag set until one prints `NVIDIA`. **Write the result in `README.md`. If none does, carry on in software mode and tell Hariom. This is the key unknown in the spec.**
- [ ] **Step 3: Run the tests.** Expected: the unit tests FAIL (not implemented).
- [ ] **Step 4: Implement** `main.py` (claim loop, heartbeat, scratch cleanup at startup and in `finally`), `render.py`, and the `--nvenc` flag in `capture.mjs`.
- [ ] **Step 5: Run the tests.** Expected: the unit tests PASS, and the integration test PASSES. Then render a **final** (`--best`) of `area-volume`. Download the contact sheet and look at it: frames must match the ones reviewed earlier, with no black or missing 3D.
- [ ] **Step 6: Commit.** `git commit -am "feat: gpu render workers (webgl on L4, nvenc drafts) + scratch hygiene"`

---

### Task 14: M0–M3 acceptance and operations basics

**Files:**
- Create: `tests/integration/test_acceptance_plan1.py`, `infra/disk_alarm.sh` (runs from cron every 15 min and writes `WARN disk > 80%` to syslog and `data/alerts.log`)
- Modify: `README.md` (how to start and stop, add an API key, run tests, where logs are, the GPU memory table, the WebGL result)

- [ ] **Step 1: Write the acceptance test** (`gpu`). It checks:
  1. `https://$DOMAIN/speech/health` shows 3 engines `ok`.
  2. An outside-style key gets Hinglish audio, a transcript with CER < 0.12 against its input, and `/align` word times.
  3. A full `voice` → `words` → `render`(draft) chain for `area-volume` finishes with no manual step.
  4. `api_usage` has rows for each call.
  5. `restore_test.sh` passes.
- [ ] **Step 2: Run it.** Expected: PASS. If anything fails, fix it in the owning task's code, not in the test.
- [ ] **Step 3: Set up a budget alert and the disk alarm.** Hariom sets a GCP budget alert (Billing → Budgets) and confirms. Install the `disk_alarm.sh` cron entry.
- [ ] **Step 4: Commit and tag.** `git commit -am "test: plan 1 acceptance" && git tag plan1-foundation`

---

## Next plans (written after Plan 1 lands; they depend on its results)

- **Plan 2: Lesson engine (M4).**
  - A 16:9 mode for the render engine: captions, labels and camera framing.
  - **Board engine:** KaTeX lines and simple diagrams, handwriting-style reveal on word anchors, highlight, cross-out and box-the-answer.
  - **Practice template:** question card, "pause and try" countdown, worked solution, answer stamp.
  - **Lesson assembler:** concat with crossfades, intro/outro cards, chapter metadata.
  - **Pilot subject kits:** solids and nets, motion graphs and vectors, atoms and molecules, cell.
- **Plan 3: Studio and review app (M5, M6).**
  - Claude `plan`, `script` and `visual` jobs: spoken form and caption form in one call, glossary-aware, cost recorded.
  - Job orchestration for the full flow in spec §5.
  - The FastAPI + HTMX review app: login, catalog, script review, draft player with timestamp-pinned comments, version compare, approvals, ops page.
  - Caddy routes `/` to it.
  - **Voice cloning** (`POST /v1/voices` from spec §6): a reference clip + speaker name + **written consent text**. It needs a `voices` table (migration) and an admin-only `voices` key scope. OmniVoice clones are registered as new voice ids.
- **Plan 4: Automatic QA and pilot (M7, M8).**
  - Audio checks.
  - Qwen2.5-VL-7B on GPU 3 via vLLM with script-aware checklists, and QA markers in the player.
  - Up to 2 automatic fix-and-re-render tries.
  - Producing the four pilot chapters, with cost per lesson recorded.
