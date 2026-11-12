-- Proposed PostgreSQL target model, NOT an executable migration for existing data.
-- Existing slides.question must be converted before replacing the current table.
CREATE TABLE slide_type_versions (
    type text NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version > 0),
    PRIMARY KEY (type, schema_version)
);

INSERT INTO slide_type_versions (type, schema_version) VALUES
    ('multiple-choice', 1), ('word-cloud', 1), ('ranking', 1),
    ('open-ended', 1), ('scale', 1), ('content', 1);

CREATE TABLE slides_v2 (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    presentation_id uuid NOT NULL REFERENCES presentations(id) ON DELETE CASCADE,
    position integer NOT NULL CHECK (position >= 0),
    type text NOT NULL,
    schema_version integer NOT NULL DEFAULT 1,
    revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
    content jsonb NOT NULL CHECK (jsonb_typeof(content) = 'object'),
    settings jsonb NOT NULL CHECK (jsonb_typeof(settings) = 'object'),
    extensions jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(extensions) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (type, schema_version) REFERENCES slide_type_versions(type, schema_version),
    UNIQUE (presentation_id, position) DEFERRABLE INITIALLY DEFERRED
);

-- Private authoring/scoring data. Participant queries must never join this table.
-- Absence of a row represents assessment.mode = 'none'.
CREATE TABLE slide_assessments (
    slide_id uuid PRIMARY KEY REFERENCES slides_v2(id) ON DELETE CASCADE,
    correct_answer jsonb NOT NULL CHECK (jsonb_typeof(correct_answer) = 'object'),
    correct_milli_points integer NOT NULL CHECK (correct_milli_points >= 0),
    incorrect_penalty_milli_points integer NOT NULL DEFAULT 0 CHECK (incorrect_penalty_milli_points >= 0),
    max_speed_bonus_milli_points integer NOT NULL DEFAULT 0 CHECK (max_speed_bonus_milli_points >= 0),
    explanation text
);

-- The unique constraint already indexes presentation_id/position for ordered reads.
-- Save content/settings/assessment together in one transaction:
-- UPDATE slides_v2 SET content = :content, settings = :settings,
-- revision = revision + 1, updated_at = now()
-- WHERE id = :id AND revision = :expected_revision;
-- Require exactly one updated row; otherwise return a conflict.
