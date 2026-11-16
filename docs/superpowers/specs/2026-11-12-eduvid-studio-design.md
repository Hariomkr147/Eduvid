# EduVid Studio: video builder + NCE video player (design)

- **Date:** 2026-11-12
- **Status:** draft for Hariom's approval
- **Builds on:** `2026-11-11-eduvid-design.md` (stack, jobs, voice/words/render workers) and the NCE design kit
  (`studio/static/nce/`: `theme.css`, `app.css`, `fonts/`, `icons.js`, Bal Krishna images, logo; reference `design_ref.md`).

## 1. Goal

A teacher or admin opens **`https://<DOMAIN>/studio/`**, picks an NCERT target from the GyanSetu database, picks an
LLM (OpenRouter), a visual mode, voice and settings, reviews the generated script, and gets a narrated, word-synced
lesson video. Every video plays in an **NCE-styled player** with chapters, bilingual captions and pause-to-check questions.
Two visual modes can be generated from the **same script** and compared side by side.

## 2. Decisions (from Hariom, 2026-11-12)

| Item | Decision |
|---|---|
| TTS | Best benchmark performer: **IndicF5 `ref-female`** (spoken CER 0.048, MIT). Male: `ref-male`. English: Kokoro `am_michael`. Selectable in the builder, so it can change later. |
| Script LLM | **OpenRouter**, model chosen per build from the live OpenRouter model list (`/api/v1/models`, prices shown). Needs `OPENROUTER_API_KEY`. |
| Visuals | **Both**: (a) design templates, (b) LLM-written animation. Builder option "both" renders the two from one script for comparison. |
| Design | Copy the NCE kit exactly (tokens, fonts, icons, Bal Krishna); improve UX within those tokens. Light only. |
| Content | GyanSetu Postgres (read-only, `NCERT_DATABASE_URL`): `books → chapters → sections → teaching_units`. Grounding text = `teaching_units.assembled_context` (+ `description`, `bloom_level`, `difficulty`). |

## 3. Architecture

New service **`studio`** (FastAPI, CPU, Python 3.11) in `compose.yaml`, behind Caddy at `/studio/*`.

```
browser ─ Caddy /studio/* ─ studio (FastAPI: UI pages + /studio/api/*)
                               │  read-only ─ GyanSetu Postgres (NCERT content)
                               │  OpenRouter (script + custom scene code)
                               │  eduvid Postgres (videos, jobs) · MinIO (projects, MP4s)
                               ▼
               jobs queue: voice → words (voice-worker, existing) → render (render-worker, existing) → publish (studio)
```

- The studio worker runs **inside the studio container** as a background loop (claims `studio_script`, `studio_build`
  and `studio_publish` jobs) so no new GPU container is needed.
- The **existing** `voice`, `words`, `render` jobs are reused unchanged. Studio writes an engine project (tar) to MinIO in the
  layout render-worker expects, then chains the jobs.
- Auth: a single admin login (`STUDIO_PASSWORD` in `.env`, signed session cookie). Builder and API need login;
  **player links are shareable** (`/studio/watch/<uuid>`, unguessable id), so students need no account.

## 4. The script (one JSON, shared by both visual modes)

The LLM returns JSON validated against a schema (pydantic). Invalid JSON gets one repair round with the error.

```json
{ "title": {"en": "...", "hi": "..."}, "language": "hinglish|hindi|english",
  "scenes": [ { "id": "s1", "kind": "title|concept|board|figure|solid|example|check|summary",
                "title": {"en":"","hi":""},
                "lines": [ {"say": "speakable Devanagari/English", "caps": "caption text, @n anchors"} ],
                "data": { ... per kind ... },
                "custom": { "brief": "what the animation shows" } } ],
  "sources": ["teaching unit id / section"] }
```

| kind | `data` | template look (NCE kit) |
|---|---|---|
| `title` | chapter, topic, objectives[] | Big display title, tag pill, Bal Krishna waving with welcome bubble |
| `concept` | points[] (each revealed on a spoken word) | Ask-style heading + steps-card bullets with chip numbers |
| `board` | steps[] `{latex, at_word, note}` | Figure card (lavender frame, warm paper, 30 px grid), KaTeX lines written in, key step in blue |
| `figure` | shapes[] (circle, cone, cylinder, sphere, rect, line, arrow, label, angle, axis, point) with `at_word` | Figure card, SVG drawn on, labels only (no sentences) |
| `solid` | solid `{shape, r, h, r2, l, b, unit, color, labels}`, moves[] `{do: revolve·unroll·fill·cut·orbit·show·paint, line, word}`, points[] | 3D (added 2026-11-16, roadmap phase 2): three.js renders into a hidden WebGL canvas copied under the 2D layer; rims, dimension lines and formula notes are 2D on top. A blank or missing WebGL frame draws the 2D figure instead. Never LLM-coded. |
| `example` | question, steps[], answer | Question card, numbered steps card, green answer feedback card |
| `check` | question, options[4], correct, hint, explain | Option cards A–D + "pause and try" countdown; the **player** pauses here and shows a real interactive question |
| `summary` | points[], next | Stat-tile style recap, Bal Krishna cheering |

Language rules from the spec stay: `say` has no digits/symbols/Latin letters for Hinglish/Hindi (the existing
`speakable.violations` check runs before voice; failures go back to the LLM once). Grounding: the prompt contains the
teaching-unit context and the instruction to use only those facts; `sources` lists the unit ids.

## 5. Visual modes

Both are the new engine style **`nce-lesson`** (`engine/styles/nce-lesson/`), a DOM/SVG/canvas page implementing the
capture protocol (`window.OP`: `ready`, `duration()`, `seek(t)`, `cues()`), sized 1920×1080 (16:9) or 1080×1920 (9:16).

- **Templates:** each scene kind above is a deterministic renderer: given `t` and the word timings it draws the exact frame.
  Motion = the kit's `pop` / `screenIn` feel; reveals land on their words; captions at the bottom (2 lines max).
- **LLM animation:** for each scene the LLM writes a function body `draw(ctx, t, A)` (canvas 2D, 1920×1080) where `A`
  gives the kit tokens, fonts, easing, word times (`A.at('word')`), and helpers (text, KaTeX-to-image, shapes, arrows,
  Bal Krishna). Code runs in the capture page only (no network, no DOM access beyond its canvas). Studio runs a **check
  render** (`capture.mjs check` + a contact sheet); on error the error text goes back to the LLM, up to 2 tries, then that
  scene falls back to its template.
- **Compare:** "both" = one script, one voice track, two renders. The builder shows them side by side, synced.

## 6. Builder (`/studio/`): built like `app/builder.html`, improved

720 px column, numbered cards, NCE header ("EduVid Studio" + "Video Factory" pill, links: Library, Player, Compare).

1. **Curriculum target:** Class → Subject/Book → Chapter → Section → Teaching unit (multi-select to make a longer video),
   loaded live from GyanSetu, with unit difficulty/Bloom tags and a context preview drawer. Or "paste your own text".
2. **AI model:** searchable OpenRouter model picker (name, context, $/M tokens), cost chip with an estimate,
   temperature, spending cap, "compare two models" (generates two scripts).
3. **Video style:** visual mode (templates / LLM animation / both), aspect (16:9, 9:16), target length (1–12 min),
   scene mix (toggle kinds, number of checks), Bal Krishna on/off, caption style, grid paper on/off, pace.
4. **Voice & language:** Hinglish / Hindi / English, voice from the gateway's `/v1/voices` (IndicF5 default) with a
   ▶ preview, speed.
5. **Review script:** editable scene cards (titles, `say`/`caps` lines, board steps, check questions), reorder, delete,
   regenerate one scene with a note. Approve → build.
6. **Build:** step list (script, voice, check, words, render, publish) with the kit's spinner/✓/✕ states, live log drawer,
   real cost; finished card (green fade) with the player link and download.

**Library** page: every video as a card (thumbnail, status, model, mode, cost, length), filters, open/compare/delete.

## 7. Player (`/studio/watch/<id>`)

Exactly section 11 of the design reference: NCE top bar with the **purple progress bar as the timeline** (scrub thumb,
chapter ticks), language switch (captions + UI), voice mute, close; video inside the figure card; current scene title in
`.ask` style with a "Part 2 of 5" tag; chapter pills (`.dstep` grey/blue/green); bottom bar with Back-10 / play-pause
(blue main button) / captions / speed; **pause-to-check** questions as real option cards with feedback card and Bal
Krishna hint, XP pill for right answers; **finish screen** (title, 3 stat tiles, Bal Krishna cheer, blue "Next").
Laptop ≥ 900 px: two columns (text/chapters left, video right). Keyboard: space, ←/→, c, f. Reduced-motion respected.

## 8. Data (eduvid Postgres, migration `0004_studio.sql`)

`studio_videos` (id uuid, title, target JSONB, settings JSONB, model, script JSONB, status, mode, parent_id for compares,
cost_usd, duration_s, keys for project/mp4/poster/manifest, error, created_at) and `studio_events` (video_id, step,
status, message, ts) for the live step list. Jobs use the existing `jobs` table.

## 9. Not in this version

Teacher accounts and comments (spec §7), automatic vision QA (M7), lesson assembly across many videos, MP4 export for
9:16 Shorts from 16:9 (render again instead).

## 10. Needs from Hariom

- `OPENROUTER_API_KEY` in `/srv/eduvid/app/.env`.
- `STUDIO_PASSWORD` for the builder login (or I generate one and tell you).
