-- EduVid schema 0001 (Plan 1). Every table: id bigserial, created_at timestamptz.
-- Enumerated values are text + CHECK.

CREATE TABLE IF NOT EXISTS schema_migrations (
    id          bigserial PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now(),
    filename    text NOT NULL UNIQUE
);

CREATE TABLE users (
    id            bigserial PRIMARY KEY,
    created_at    timestamptz NOT NULL DEFAULT now(),
    email         text NOT NULL UNIQUE,
    name          text NOT NULL DEFAULT '',
    role          text NOT NULL DEFAULT 'reviewer' CHECK (role IN ('admin','editor','reviewer')),
    password_hash text,
    active        boolean NOT NULL DEFAULT true
);

CREATE TABLE chapters (
    id          bigserial PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now(),
    class       int  NOT NULL CHECK (class BETWEEN 1 AND 12),
    subject     text NOT NULL CHECK (subject ~ '^[a-z][a-z0-9-]*$'),
    slug        text NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9-]*$'),
    title       text NOT NULL,
    position    int,                                     -- NCERT topic order
    status      text NOT NULL DEFAULT 'planned'
                CHECK (status IN ('planned','in_progress','in_review','approved','published')),
    meta        jsonb NOT NULL DEFAULT '{}',
    UNIQUE (class, subject, slug)
);

CREATE TABLE lessons (
    id          bigserial PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now(),
    chapter_id  bigint NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    number      int  NOT NULL CHECK (number >= 1),
    title       text NOT NULL,
    status      text NOT NULL DEFAULT 'planned'
                CHECK (status IN ('planned','in_progress','in_review','approved','published')),
    plan        jsonb NOT NULL DEFAULT '{}',
    UNIQUE (chapter_id, number)
);

CREATE TABLE segments (
    id          bigserial PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now(),
    lesson_id   bigint NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    number      int  NOT NULL CHECK (number >= 1),
    kind        text NOT NULL CHECK (kind IN ('scene','board','practice')),
    title       text NOT NULL DEFAULT '',
    UNIQUE (lesson_id, number)
);

CREATE TABLE segment_versions (
    id          bigserial PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now(),
    segment_id  bigint NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    version     int  NOT NULL CHECK (version >= 1),
    status      text NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft','in_review','approved','rejected','superseded')),
    script      jsonb NOT NULL DEFAULT '{}',              -- say / caps per line, per language
    visual      jsonb NOT NULL DEFAULT '{}',
    notes       text NOT NULL DEFAULT '',
    created_by  bigint REFERENCES users(id),
    cost_usd    numeric(10,4) NOT NULL DEFAULT 0,
    UNIQUE (segment_id, version)
);

CREATE TABLE renders (
    id              bigserial PRIMARY KEY,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    version_id      bigint NOT NULL REFERENCES segment_versions(id) ON DELETE CASCADE,
    language        text NOT NULL CHECK (language IN ('hinglish','english','hindi')),
    quality         text NOT NULL CHECK (quality IN ('draft','final')),
    status          text NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','voiced','timed','rendering','done','failed')),
    voice           text,
    prefix          text,                                -- object key prefix (…/v{n}/{language}/)
    video_key       text,
    sheet_key       text,
    takes           jsonb,                               -- voice-to-script check report
    qa              jsonb,
    duration_s      numeric(8,3),
    gpu_seconds     numeric(10,2),
    webgl_renderer  text,
    UNIQUE (version_id, language, quality)
);

CREATE TABLE lesson_renders (
    id          bigserial PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now(),
    lesson_id   bigint NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    language    text NOT NULL CHECK (language IN ('hinglish','english','hindi')),
    status      text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','done','failed')),
    render_ids  bigint[] NOT NULL DEFAULT '{}',
    video_key   text,
    duration_s  numeric(8,3)
);

CREATE TABLE comments (
    id          bigserial PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now(),
    render_id   bigint NOT NULL REFERENCES renders(id) ON DELETE CASCADE,
    user_id     bigint REFERENCES users(id),
    t_s         numeric(8,3),                            -- timestamp-pinned
    body        text NOT NULL,
    source      text NOT NULL DEFAULT 'human' CHECK (source IN ('human','qa')),
    resolved    boolean NOT NULL DEFAULT false
);

CREATE TABLE approvals (
    id          bigserial PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now(),
    version_id  bigint NOT NULL REFERENCES segment_versions(id) ON DELETE CASCADE,
    render_id   bigint REFERENCES renders(id) ON DELETE CASCADE,
    user_id     bigint REFERENCES users(id),
    stage       text NOT NULL CHECK (stage IN ('script','visual','draft','final')),
    decision    text NOT NULL CHECK (decision IN ('approved','changes_requested','rejected')),
    note        text NOT NULL DEFAULT ''
);

CREATE TABLE jobs (
    id            bigserial PRIMARY KEY,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    type          text NOT NULL CHECK (type IN
                  ('plan','script','visual','voice','words','check','render','qa','assemble')),
    status        text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','done','failed')),
    payload       jsonb NOT NULL DEFAULT '{}',
    result        jsonb,
    priority      int  NOT NULL DEFAULT 100,
    attempts      int  NOT NULL DEFAULT 0,
    run_after     timestamptz NOT NULL DEFAULT now(),
    locked_until  timestamptz,
    locked_by     text,
    gpu           int,
    error         text,
    log_key       text,
    render_id     bigint REFERENCES renders(id) ON DELETE SET NULL,
    finished_at   timestamptz
);
CREATE INDEX jobs_claim_idx ON jobs (priority, id) WHERE status IN ('queued','running');
CREATE INDEX jobs_type_status_idx ON jobs (type, status);

CREATE TABLE glossary (
    id            bigserial PRIMARY KEY,
    created_at    timestamptz NOT NULL DEFAULT now(),
    subject       text NOT NULL,
    term_en       text NOT NULL,                          -- canonical English term
    hindi_term    text NOT NULL DEFAULT '',               -- shuddh Hindi word (Devanagari)
    hinglish_say  text NOT NULL DEFAULT '',               -- how it is spoken in Hinglish (Devanagari)
    hindi_say     text NOT NULL DEFAULT '',               -- how it is spoken in Hindi (Devanagari)
    english_say   text NOT NULL DEFAULT '',               -- spoken English form
    caption       text NOT NULL DEFAULT '',               -- Roman caption form
    notes         text NOT NULL DEFAULT '',
    UNIQUE (subject, term_en)
);

CREATE TABLE api_keys (
    id          bigserial PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now(),
    name        text NOT NULL,
    prefix      text NOT NULL,                            -- first chars, for display only
    hash        text NOT NULL UNIQUE,                     -- sha256(key) hex
    scopes      text[] NOT NULL DEFAULT '{}' CHECK (scopes <@ ARRAY['tts','stt']::text[]),
    rate_limit  int  NOT NULL DEFAULT 60,                 -- requests per minute
    pipeline    boolean NOT NULL DEFAULT false,
    revoked_at  timestamptz,
    last_used_at timestamptz
);

CREATE TABLE api_usage (
    id          bigserial PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now(),
    key_id      bigint REFERENCES api_keys(id) ON DELETE SET NULL,
    endpoint    text NOT NULL,
    model       text NOT NULL DEFAULT '',
    status      int  NOT NULL DEFAULT 200,
    characters  int,
    seconds     numeric(10,3),
    ms          int  NOT NULL
);
CREATE INDEX api_usage_key_time_idx ON api_usage (key_id, created_at);
