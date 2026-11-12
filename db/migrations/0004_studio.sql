-- EduVid Studio (docs/superpowers/specs/2026-11-12-eduvid-studio-design.md §8):
-- one row per built video, an event log per video for the builder's live step list.
CREATE TABLE studio_videos (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    title       text NOT NULL DEFAULT '',
    target      jsonb NOT NULL DEFAULT '{}',   -- NCERT target: book/chapter/section/unit ids + names, or pasted text
    settings    jsonb NOT NULL DEFAULT '{}',   -- builder settings (model, mode, aspect, voice, language, …)
    model       text NOT NULL DEFAULT '',
    script      jsonb,                         -- the validated video script (spec §4)
    status      text NOT NULL DEFAULT 'scripting' CHECK (status IN
                ('scripting','review','voicing','timing','coding','rendering','publishing','done','failed')),
    stage       jsonb NOT NULL DEFAULT '{}',   -- pipeline bookkeeping: job ids per step and variant
    variants    jsonb NOT NULL DEFAULT '[]',   -- [{mode, status, video_key, poster_key, manifest_key, duration_s, error}]
    compare_id  uuid,                          -- videos made together for comparison share this id
    cost_usd    numeric(10,4) NOT NULL DEFAULT 0,
    duration_s  real,
    error       text
);
CREATE INDEX studio_videos_created_idx ON studio_videos (created_at DESC);
CREATE INDEX studio_videos_active_idx ON studio_videos (status)
    WHERE status NOT IN ('review','done','failed');

CREATE TABLE studio_events (
    id        bigserial PRIMARY KEY,
    video_id  uuid NOT NULL REFERENCES studio_videos(id) ON DELETE CASCADE,
    ts        timestamptz NOT NULL DEFAULT now(),
    step      text NOT NULL,                   -- script | voice | words | code | render | publish
    status    text NOT NULL CHECK (status IN ('running','done','failed','info','skipped')),
    message   text NOT NULL DEFAULT ''
);
CREATE INDEX studio_events_video_idx ON studio_events (video_id, id);
