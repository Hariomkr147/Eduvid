-- Align the schema with spec §4 (docs/superpowers/specs/2026-11-11-eduvid-design.md).
-- 0001 was written before the spec was on the server; this renames columns and enum values to the spec's.
-- Columns the spec doesn't name (slug, prefix, takes, webgl_renderer, source, stage, …) stay.

-- users: roles admin | teacher; teachers see only their subjects
ALTER TABLE users DROP CONSTRAINT users_role_check;
UPDATE users SET role = CASE role WHEN 'admin' THEN 'admin' WHEN 'editor' THEN 'admin' ELSE 'teacher' END;
ALTER TABLE users ALTER COLUMN role SET DEFAULT 'teacher',
    ADD CONSTRAINT users_role_check CHECK (role IN ('admin','teacher')),
    ADD COLUMN subjects text[] NOT NULL DEFAULT '{}';

-- chapters: NCERT reference ("NCERT Mathematics Class 9, Chapter 11")
ALTER TABLE chapters ADD COLUMN ncert_ref text NOT NULL DEFAULT '';

-- lessons: position, objectives, status planned → scripting → in_review → approved → assembled
ALTER TABLE lessons RENAME COLUMN number TO position;
ALTER TABLE lessons DROP CONSTRAINT lessons_status_check;
UPDATE lessons SET status = CASE status WHEN 'in_progress' THEN 'scripting' WHEN 'published' THEN 'assembled'
                                        ELSE status END;
ALTER TABLE lessons ADD COLUMN objectives text[] NOT NULL DEFAULT '{}',
    ADD CONSTRAINT lessons_status_check
        CHECK (status IN ('planned','scripting','in_review','approved','assembled'));

-- segment_versions: n, parent version, status draft | script_approved | approved | rejected.
-- created_by: NULL = written by Claude, else the user who wrote it.
ALTER TABLE segment_versions RENAME COLUMN version TO n;
ALTER TABLE segment_versions DROP CONSTRAINT segment_versions_status_check;
UPDATE segment_versions SET status = CASE status WHEN 'in_review' THEN 'draft' WHEN 'superseded' THEN 'rejected'
                                                 ELSE status END;
ALTER TABLE segment_versions
    ADD COLUMN parent_version_id bigint REFERENCES segment_versions(id) ON DELETE SET NULL,
    ADD CONSTRAINT segment_versions_status_check CHECK (status IN ('draft','script_approved','approved','rejected'));
COMMENT ON COLUMN segment_versions.created_by IS 'NULL = Claude; otherwise the user who wrote this version';

-- segments: position, current version, status
ALTER TABLE segments RENAME COLUMN number TO position;
ALTER TABLE segments
    ADD COLUMN current_version_id bigint REFERENCES segment_versions(id) ON DELETE SET NULL,
    ADD COLUMN status text NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned','scripting','in_review','approved','done'));

-- renders: a key per artefact, QA result
ALTER TABLE renders
    ADD COLUMN narration_key text,
    ADD COLUMN words_key text,
    ADD COLUMN qa_key text,
    ADD COLUMN qa_status text CHECK (qa_status IN ('pass','warn','fail'));

-- lesson_renders: chapter markers for the assembled lesson
ALTER TABLE lesson_renders ADD COLUMN chapter_markers jsonb NOT NULL DEFAULT '[]';

-- comments: on a version (and optionally the render watched), at a time, open | resolved
ALTER TABLE comments RENAME COLUMN t_s TO timecode_s;
ALTER TABLE comments RENAME COLUMN body TO text;
ALTER TABLE comments
    ADD COLUMN version_id bigint REFERENCES segment_versions(id) ON DELETE CASCADE,
    ADD COLUMN status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved')),
    ADD COLUMN resolved_by_version_id bigint REFERENCES segment_versions(id) ON DELETE SET NULL,
    ALTER COLUMN render_id DROP NOT NULL;
UPDATE comments c SET version_id = r.version_id, status = CASE WHEN c.resolved THEN 'resolved' ELSE 'open' END
  FROM renders r WHERE r.id = c.render_id;
ALTER TABLE comments DROP COLUMN resolved,
    ALTER COLUMN version_id SET NOT NULL;

-- approvals: one audit trail for any target (outline, script, draft, lesson sign-off)
ALTER TABLE approvals
    ADD COLUMN target_type text,
    ADD COLUMN target_id bigint;
UPDATE approvals SET target_type = CASE WHEN render_id IS NOT NULL THEN 'render' ELSE 'segment_version' END,
                     target_id = COALESCE(render_id, version_id);
ALTER TABLE approvals DROP COLUMN version_id, DROP COLUMN render_id,
    ALTER COLUMN stage DROP NOT NULL,
    ALTER COLUMN target_type SET NOT NULL,
    ALTER COLUMN target_id SET NOT NULL,
    ADD CONSTRAINT approvals_target_type_check
        CHECK (target_type IN ('chapter','lesson','segment_version','render','lesson_render'));
CREATE INDEX approvals_target ON approvals (target_type, target_id);

-- jobs: worker, started_at
ALTER TABLE jobs RENAME COLUMN locked_by TO worker;
ALTER TABLE jobs ADD COLUMN started_at timestamptz;

-- glossary: the spec's names (hindi_term, the written Hindi term, stays as an extra column)
ALTER TABLE glossary RENAME COLUMN term_en TO term;
ALTER TABLE glossary RENAME COLUMN hinglish_say TO spoken_hinglish;
ALTER TABLE glossary RENAME COLUMN caption TO caption_roman;
ALTER TABLE glossary RENAME COLUMN english_say TO spoken_english;
ALTER TABLE glossary RENAME COLUMN hindi_say TO spoken_hindi;
