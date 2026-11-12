# EduVid: NCERT lesson video system (design)

- **Date:** 2026-11-11
- **Status:** approved with changes (2026-11-11): speakable text, check that the voice matches the script, forced alignment for timing, two-form lines + glossary. Defaults until Hariom says otherwise: 16:9 lessons, the proposed pilot chapters, an `sslip.io` address if there's no domain.
- **Owner:** Hariom
- **Builds on:** the `faceless-shorts` skill (script → voice → word timing → animated shots → sound → MP4)

---

## 1. Goal

A system running on one always-on GPU server that produces **full NCERT chapter lessons** (8–12 min videos) for a school, coaching institute or app. A small team of teachers reviews and signs off on every lesson. The same server also offers its **voice (TTS) and transcription (Whisper) models as an API** that other apps can call.

### Success criteria for the pilot
1. **Four pilot chapters are finished:** one each from maths, physics, chemistry and biology. Each has 3–5 lessons of 8–12 minutes in **Hinglish**, and every lesson is signed off by a subject teacher in the review app.
2. **A teacher comment is fixed in under 30 minutes.** A comment on one segment produces a corrected render of only that segment within 30 minutes of the fix being approved.
3. **Automatic QA catches problems first.** It flags at least the defects we already know about (overlaps, cut-off labels, wrong captions, words the voice didn't say) before a teacher sees the draft.
4. **The speech API works for outside apps.** At least one app other than this pipeline (for example OmniRoute, or a test client) uses `/v1/audio/speech` and `/v1/audio/transcriptions` with its own API key.
5. **Real costs are measured:** Claude API cost and GPU minutes per lesson, recorded in the database.

### Proposed pilot chapters (to confirm)
| Subject | Chapter (NCERT Class 9) | Why |
|---|---|---|
| Maths | Surface Areas and Volumes | The 3D net pieces already exist (cylinder, cone) |
| Physics | Motion | Graphs, vectors and board derivations |
| Chemistry | Atoms and Molecules | Atom and molecule kit, plus mole-concept problems |
| Biology | The Fundamental Unit of Life | Cell kit and labelled diagrams |

### Not in v1 (the design leaves room for them)
- English and Hindi tracks. Each language is a separate track, so adding them later needs no rebuild.
- Delivery formats for a specific buyer, such as LMS/SCORM, branding or app integration. These wait until the buyer's needs are known.
- YouTube publishing.
- Use by more than one organisation.
- Self-hosted text models for writing scripts. Scripts and animation code come from the Claude API, where quality matters most.

---

## 2. Constraints (known)

| Item | Value |
|---|---|
| Server | GCP `g2-standard-48`, project `gen-lang-client-0655989759`, zone `asia-southeast1-c`, on-demand, **always on** |
| GPUs | 4× NVIDIA L4, 23 GB each, driver 550.163.01, CUDA 12.4 |
| CPU / RAM | 48 vCPU / about 188 GB |
| Disk | 2.9 TB **persistent** disk (`nvme_card-pd`) at `/`, 2.8 TB free |
| User | `hariom`, with sudo (confirmed) |
| OS | **Debian 13 (trixie)**, confirmed 2026-11-11. Containers use Ubuntu-based CUDA 12.4 images. Kernel packages are held if the NVIDIA driver isn't in DKMS. |
| Cost | About $4.94/hour on-demand (about $3,600/month). This is fixed, so the GPUs should stay busy. |

---

## 3. Architecture

**Everything runs on the GPU VM for now** (option 3), as Docker containers, with **all state under `/srv/eduvid/`** on the persistent disk. It's built so storage can move to a separate server later (option 2) by changing settings, not code.

| Service | GPU | Purpose |
|---|---|---|
| `postgres` | — | Catalog, scripts, versions, comments, approvals, **job queue**, API keys, usage, costs |
| `minio` | — | S3-compatible file storage (audio, frames, MP4s, contact sheets, QA reports) |
| `speech-api` | **GPU 0** | OpenAI-compatible TTS and transcription: OmniVoice, Kokoro, Whisper large-v3 |
| `render-worker` ×2 | **GPU 1, GPU 2** | Headless Chrome renderers (several per GPU) + ffmpeg; take `render` jobs |
| `qa-worker` | **GPU 3** | Vision model reviews contact sheets and frames, plus audio checks; takes `render` jobs when idle |
| `studio-worker` | — | Calls the Claude API to plan lessons and write scripts and animation code |
| `core-api` + review app | — | Web app for admins and teachers, plus an internal API used by the workers |
| `caddy` | — | HTTPS reverse proxy with automatic certificates. Only **443** (and SSH) is open. |

### Rules that keep the later move easy
- Services reach each other only through settings: `DATABASE_URL`, `S3_ENDPOINT`/`S3_BUCKET`, `SPEECH_API_URL`. No shared local folders between services, except each worker's own temporary scratch space.
- Every file is read and written through the **S3 API**, even though MinIO runs locally.
- **Moving storage later:**
  1. `pg_dump` → restore on the new server.
  2. `mc mirror` the bucket.
  3. Change `DATABASE_URL` and `S3_ENDPOINT`.

  The GPU VM then keeps only `speech-api` and the workers.

### Language and stack choices
- **Python 3.11+ (FastAPI)** for `core-api`, `speech-api`, `studio-worker` and `qa-worker`. The voice and Whisper tooling is already in Python.
- **Node 22** for rendering. This reuses `capture.mjs`, the style engines and the kits from `faceless-shorts`.
- **The review app is served by FastAPI** (Jinja templates + HTMX) with a small amount of JavaScript for the video player and pinned comments. There's no separate front-end build. That's a deliberate YAGNI choice and can be revisited if the app grows.
- **The job queue lives in Postgres** (`SELECT … FOR UPDATE SKIP LOCKED`). There's no Redis.

---

## 4. Data model

### Hierarchy
```
chapter → lesson (8–12 min) → segment (1–3 min; kind = scene | board | practice)
        → segment_version (v1, v2… never edited, only replaced)
        → render (one per version × language)
lesson_render = approved segment renders for one language, put together into one file
```

### Tables (main columns)
- **`users`**: id, name, email, password_hash (argon2), role (`admin` | `teacher`), subjects[].
- **`chapters`**: id, class, subject, ncert_ref, title, status.
- **`lessons`**: id, chapter_id, position, title, objectives[], status (`planned` → `scripting` → `in_review` → `approved` → `assembled`).
- **`segments`**: id, lesson_id, position, kind, title, current_version_id, status.
- **`segment_versions`**: id, segment_id, n, `script` (JSONB: narration lines, captions, board steps, practice items with answers, sources), `visual` (JSONB settings for kits and board, or the `shots.js` text for custom scenes), created_by (`claude` | user id), parent_version_id, status (`draft` | `script_approved` | `approved` | `rejected`), cost_usd.
- **`renders`**: id, version_id, language (`hinglish` | `english` | `hindi`), voice, quality (`draft` | `final`), status, duration_s, keys for narration/words/video/sheet/qa, qa_status (`pass` | `warn` | `fail`), gpu_seconds.
- **`lesson_renders`**: id, lesson_id, language, segment render ids[], video_key, chapter markers (JSONB), status.
- **`comments`**: id, version_id, render_id, user_id, timecode_s, text, status (`open` | `resolved`), resolved_by_version_id.
- **`approvals`**: id, target_type, target_id, user_id, decision, note, created_at. This is the audit trail.
- **`jobs`**: id, type (`plan` | `script` | `visual` | `voice` | `words` | `check` | `render` | `qa` | `assemble`), payload (JSONB), status (`queued` | `running` | `done` | `failed`), priority, attempts, worker, gpu, started/finished, log_key, error.
- **`glossary`**: id, subject, term (canonical English), spoken_hinglish (Devanagari, as said, e.g. "सिलेंडर"), caption_roman ("cylinder"), spoken_english ("cylinder"), spoken_hindi ("बेलन"), notes. Every script prompt uses it, and a script check enforces it.
- **`api_keys`**: id, name, hash, scopes (`tts`, `stt`), rate_limit, active. **`api_usage`**: key_id, endpoint, model, chars or seconds, ms, created_at.

### File layout (MinIO bucket `eduvid`)
```
class-9/maths/ch11-surface-areas/lesson-02/seg-04/v3/hinglish/
  narration.wav  words.json  lines.json  cues.json  mix.wav  draft.mp4  final.mp4  sheet.jpg  qa.json  log.txt
class-9/maths/ch11-surface-areas/lesson-02/hinglish/lesson.mp4
```

### Languages
A version's **visual** is shared by every language. Each **render** has its own voice, captions, on-screen labels and **its own word timing**, so the same animation re-times itself to each language.

---

## 5. How a lesson moves through the system

1. **Plan.** An admin creates a chapter. A `plan` job (Claude) suggests lessons and segments: kind, learning objective, NCERT reference and target length. **The admin approves or edits the outline.**
2. **Script.** For each segment, a `script` job (Claude) writes:
   - Narration lines (one line = one cut), **each in two forms:**
     - **`say`** is the **speakable** form fed to the voice: Devanagari for Hinglish and Hindi, with English terms written as they're spoken and **every symbol spelt out** ("πr²" → "पाई आर स्क्वेयर्ड", "H₂SO₄" → "एच टू एस ओ फ़ोर"). English uses the same idea ("pi r squared").
     - **`caps`** is the caption form: Roman Hinglish with proper English spelling ("Cylinder ka *surface area*"). Each chunk is pinned to a spoken word with `@n`.
     - Both come from Claude in the same call; they are **never machine-transliterated**. The **glossary** keeps technical terms consistent. A rule-based check rejects any `say` text that still contains symbols, digits or Latin letters (for Hinglish and Hindi).
   - **Board steps** (equations as LaTeX, each appearing on a spoken word).
   - **Practice items** (question, a "pause and try" duration, solution steps, answer).
   - Sources.

   **A teacher approves it, or comments** → Claude revises → a new version is created.
3. **Visual.** A `visual` job (Claude) creates the visual:
   - **scene:** `shots.js` using the subject kits (as in `faceless-shorts`).
   - **board:** **no code**. The board engine draws the board steps from the script.
   - **practice:** **no code**. A fixed template: question card → countdown → worked solution on the board engine.
4. **Voice.** A `voice` job sends each sentence's `say` text to `speech-api` (OmniVoice for Hinglish and Hindi, Kokoro for English), producing `narration.wav` and `lines.json`.
   - **Voice-to-script check:** every sentence is transcribed back with Whisper large-v3 and compared with its `say` text, as a character error rate (CER) after normalisation.
   - If CER is over **12%** (to be tuned in the pilot), the sentence is **re-generated with a new seed**, up to 3 times. After that it's flagged for a person. This catches dropped, garbled or invented words before anyone hears them.
5. **Word timing.** A `words` job runs **forced alignment of the known script** (the `say` words) against `narration.wav`, using the WhisperX align step (wav2vec2 aligner for the language), with Meta MMS (`torchaudio` `MMS_FA`) as the fallback.
   - Every script word gets a start and end time, so nothing is misheard or misspelt, and caption anchors and 3D cues land exactly on their words.
   - Cuts inside a sentence are moved onto the aligned word boundaries. The result is written to `words.json` in the existing `{w, line, s, e, matched}` format.
6. **Check and draft render.** A `check` job then a `render` job (draft: 30 fps, NVENC) produce `draft.mp4` and `sheet.jpg`.
7. **Automatic QA.** A `qa` job (GPU 3) writes `qa.json`. On `fail`, the system sends the QA report to Claude to fix the visual and re-renders, **at most 2 automatic tries**, then flags it for a person.
8. **Teacher review** of the draft in the app. Comments pinned to timestamps create a new version through Claude, and only that segment is re-rendered. **Teacher approval** marks the version `approved`.
9. **Final render.** A `render` job at final quality: 60 fps for 2D (30 fps for 3D), lossless frames, x264 slow CRF 14 on the CPU, and −14 LUFS sound.
10. **Assemble.** When every segment of a lesson is approved and rendered, an `assemble` job joins them with short transitions, an intro and outro card, and chapter markers, producing `lesson.mp4`. **The teacher gives final sign-off** on the whole lesson.

**Retries:** a failed job is retried up to 3 times with a growing delay, then marked `failed` with its log saved. The review app shows failed jobs with their log and a "retry" button.

### New parts this needs (beyond `faceless-shorts`)
- **Board engine** (Chrome, canvas + KaTeX): handwriting-style reveal of LaTeX lines and simple diagrams, each step timed to a word, with highlight, cross-out and box-the-answer moves.
- **Practice template:** question card, a "pause and try" countdown chip, solution on the board engine, and an answer stamp.
- **Lesson assembler** (ffmpeg concat with crossfades + chapter metadata).
- **Subject kits for the pilot:** solids and their nets (maths); graphs, motion arrows, timeline (physics); atoms, molecules, formula builder (chemistry); cell and organelles with labels (biology).
- **16:9 format:** the render engine gets a 16:9 mode (1920×1080), with captions, labels and camera framing that adapt to the frame shape, because students watch lessons on laptops, projectors and app players. The existing 9:16 mode stays, so Shorts can be made from approved segments later. *(To confirm: 16:9 lessons.)*

---

## 6. Speech API (shared service on GPU 0)

OpenAI-compatible, so other apps and OmniRoute can use it as a provider.

| Endpoint | Purpose |
|---|---|
| `POST /v1/audio/speech` | `{ model: "omnivoice" \| "kokoro", input, voice, language?, instruct?, speed?, response_format: wav \| mp3 \| opus }` → audio |
| `POST /v1/audio/transcriptions` | multipart `file`, `model: "whisper-large-v3"` (WhisperX: faster-whisper + word alignment), `language?`, `prompt?`, `response_format: json \| verbose_json \| srt \| vtt`, `timestamp_granularities[]=word` |
| `POST /v1/audio/align` | multipart `file` + `text` (or JSON `words[]`), `language` → word-level `{word, start, end, score}` from forced alignment of the given text. Used by the pipeline, and open to outside apps. |
| `GET /v1/models`, `GET /v1/voices` | Lists of models and voices |
| `POST /v1/voices` | Register a cloned voice from a reference clip (OmniVoice). **Only with the speaker's written consent**, recorded in the database. |
| `GET /health` | Model status and GPU memory |

- **Auth:** `Authorization: Bearer <key>`, with keys stored hashed in `api_keys`. Each key has scopes and a rate limit. Every call is logged to `api_usage`.
- **Concurrency:** one model instance per engine, each with a request queue. The pipeline's jobs and outside calls share it fairly: pipeline work goes first, but outside callers always get a share.
- **Models (v1):**
  - **OmniVoice:** Hinglish and Hindi, female and male voices, voice cloning.
  - **Kokoro-82M:** English.
  - **Whisper large-v3** via WhisperX/faster-whisper (CUDA float16) for transcription and the voice-to-script check.
  - **Aligners:** WhisperX wav2vec2 aligners (Hindi, English), with MMS `MMS_FA` as the fallback, for `/v1/audio/align`.
  - **Candidates to compare by ear in the pilot** for Hindi and Hinglish: AI4Bharat Indic Parler-TTS and IndicF5, next to OmniVoice. Keep whichever wins on clarity and licence.

  The layout allows adding more models later (for example Indic TTS models) through a model registry.
- **OmniRoute:** register `https://<domain>/speech/v1` as an OpenAI-compatible provider. *(Check whether OmniRoute routes audio endpoints. If it doesn't, apps call the speech API directly.)*

---

## 7. Review app (for admins and teachers)

- **Login** (email and password, sessions). Roles: admin (everything) and teacher (only their subjects).
- **Catalog:** chapter → lessons → segments, each with a status badge and a "what's next" queue per teacher.
- **Script review:** narration and board steps side by side, with sources. Buttons: **approve** or **comment**.
- **Draft player:** the video plus the segment's QA flags as markers on the timeline. **Click to comment at the current time.** Comments show as pins and can be resolved.
- **Version compare:** play v2 and v3 side by side, and see which comments the new version fixed.
- **Lesson view:** the assembled lesson, chapter list and final sign-off.
- **Ops page (admin):** job queue, failed jobs with logs and retry, GPU use, disk use, and cost per lesson.
- Works on a phone browser too, so teachers can review on the go.

---

## 8. Automatic QA (GPU 3)

1. **Engine checks** (already exist): every frame draws; shot length; caption timing; words not heard; estimated timing.
2. **Audio checks:** overall loudness (−14 LUFS ±1), clipping, silences over 1.5 s inside narration, the **voice-to-script CER** for each sentence, and the alignment confidence score for each word (low scores are flagged).
3. **Vision review:** a local vision-language model (**Qwen2.5-VL-7B-Instruct**, served by vLLM on GPU 3) looks at contact sheets and key frames, with a checklist built from the segment's script:
   - Overlaps, and text cut off at the edges.
   - Captions colliding with the action.
   - Blank or broken frames.
   - Labels that don't match the narration.
   - Board text matching the LaTeX.

   The output is JSON issues with a time, a severity and a description.
4. **The overall result** (`pass`, `warn` or `fail`) and the issues go to `qa.json` and show as markers in the draft player.

*(Check that the vision model's quality is good enough on our frames in milestone M7. If it isn't, a larger model can run in 4-bit, or QA stays rule-based and teachers do more of it.)*

---

## 9. Rendering on L4

- **Chrome WebGL on the GPU:** headless Chrome using the L4 through EGL or Vulkan, so 3D renders at full quality. **This must be proven first (milestone M3).** If it fails, software rendering on 48 vCPUs at lower 3D resolution is the fallback.
- **Workers per GPU:** start with 3 Chrome renderers per L4 on GPUs 1 and 2, then tune using measured GPU, memory and CPU use.
- **Encoding:** drafts use `h264_nvenc` (the GPU's encoder chip, very fast). Finals use `libx264 -preset slow -crf 14` on the CPU for the best quality. GPU and CPU work happen in parallel.
- **Temporary frames:** `/srv/eduvid/scratch/<job>` is deleted after each job.

---

## 10. Operations

- **Install:** Docker Engine + NVIDIA Container Toolkit, one `docker compose` stack in `/srv/eduvid`, and a systemd unit so it restarts after reboots.
- **Secrets:** `/srv/eduvid/.env` (mode 600). It holds `ANTHROPIC_API_KEY`, database and MinIO passwords, and the session secret. **It is never committed or copied into containers**; containers receive it as environment variables.
- **Network:** a domain (for example `studio.<domain>`, with `/speech` for the API) pointed at the VM's static IP. The GCP firewall allows **443 from anywhere** and **22 only from your IP**. Postgres and MinIO are never exposed to the internet.
- **Backups:**
  - **Nightly:** `pg_dump` plus `mc mirror` of the bucket to a GCS bucket (Nearline storage). Database dumps are kept for 14 days.
  - **Weekly:** a test restore of the database dump into a throwaway container.
- **Monitoring:** the ops page; GPU metrics (the dcgm exporter, or `nvidia-smi` polling); a disk alarm at 80%; a GCP budget alert.
- **Cleanup rule (later):** keep approved versions and the last 2 drafts per segment, and delete older drafts' frames and MP4s after 30 days.

---

## 11. Cost (to measure in the pilot)
- **GPU VM:** fixed (about $3,600/month at on-demand list price).
- **Claude API:** about $3–8 per lesson for planning, scripts, scene code and QA-driven fixes. This is an estimate, recorded per version in `segment_versions.cost_usd`.
- **Storage:** the local disk; the GCS backup costs well under $10/month at pilot size.

---

## 12. Risks and open questions

| # | Item | How it's resolved |
|---|---|---|
| 1 | Sudo access and OS version | Checked automatically at the start of M0 (stop and ask if there's no sudo) |
| 2 | Domain name for HTTPS | Use `DOMAIN` from `.env`; **default `<static-ip-with-dashes>.sslip.io`** |
| 3 | Chrome WebGL on L4, headless | Proven in M3; software fallback exists |
| 4 | **OmniVoice licence for commercial use** (selling lessons to schools) | Checked before M2. If unclear, a commercially licensed voice model is chosen for client deliverables. Kokoro is Apache-2.0, faster-whisper and Whisper are MIT, Qwen2.5-VL-7B is Apache-2.0 (to confirm). |
| 5 | Hinglish voice quality and pronunciation of technical terms | Glossary + speakable-text check + voice-to-script check; listening test of OmniVoice against the AI4Bharat models in M2 |
| 6 | What the buyer actually needs (D): formats, branding, LMS | Decided later; delivery is a separate step after `lesson.mp4` |
| 7 | 16:9 lessons (and 9:16 Shorts later) | **Default: 16:9.** Change if Hariom says otherwise. |
| 8 | NCERT content | Facts and order of topics only; never textbook text or figures |
| 9 | One server holds everything (option 3) | Nightly off-server backup now; move to option 2 later |

---

## 13. Build order (milestones; details in the implementation plan)

| Milestone | Delivers | Done when |
|---|---|---|
| **M0 Base server** | Docker, NVIDIA toolkit, firewall, domain, Caddy, `/srv/eduvid` layout | `docker run --gpus all nvidia/cuda… nvidia-smi` shows 4 L4s; HTTPS hello page loads |
| **M1 Storage** | Postgres + MinIO + database setup scripts + nightly backup | The tables exist; a backup and restore have been tested |
| **M2 Speech API** | OmniVoice, Kokoro, Whisper large-v3 (WhisperX), forced aligner behind `/v1/audio/*`, keys, usage, speakable-text check + glossary | An outside `curl` with a key gets Hinglish audio; `/align` returns word times for a known script; a garbled take gets re-done |
| **M3 Render worker** | `faceless-shorts` engine in a GPU container; WebGL on L4 proven; NVENC drafts | The `area-volume` Deep Dive video renders on the server at full quality |
| **M4 Board + practice** | Board engine, practice template, 16:9 format, lesson assembler | A hand-written board segment and a practice segment render and assemble |
| **M5 Studio + jobs** | Job queue, `plan`/`script`/`visual` Claude jobs, the full flow of section 5 | One lesson goes from a topic to a draft with no manual steps |
| **M6 Review app** | Login, catalog, script review, draft player with pinned comments, approvals, ops page | A teacher reviews, comments, approves; a fix re-renders one segment |
| **M7 Automatic QA** | Audio checks, vision model on GPU 3, QA markers in the player | Known defect samples get flagged |
| **M8 Pilot** | The four chapters in Hinglish | Every pilot lesson has a teacher's sign-off; cost per lesson recorded |
