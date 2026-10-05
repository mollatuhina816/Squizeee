BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 38225079a1ae

CREATE TABLE organizations (
    name VARCHAR(120) NOT NULL, 
    faculty_lite_permissions JSON NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE TABLE users (
    email VARCHAR(320) NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    password_hash VARCHAR(255) NOT NULL, 
    is_super_admin BOOLEAN NOT NULL, 
    active BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (email)
);

CREATE TABLE audit_events (
    organization_id UUID, 
    actor_id UUID NOT NULL, 
    action VARCHAR(100) NOT NULL, 
    resource_id VARCHAR(100) NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(actor_id) REFERENCES users (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_audit_events_organization_id ON audit_events (organization_id);

CREATE TABLE auth_sessions (
    user_id UUID NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    revoked BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_auth_sessions_user_id ON auth_sessions (user_id);

CREATE TABLE departments (
    organization_id UUID NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    UNIQUE (organization_id, id), 
    UNIQUE (organization_id, name)
);

CREATE INDEX ix_departments_organization_id ON departments (organization_id);

CREATE TABLE memberships (
    organization_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    role VARCHAR(30) NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT membership_role CHECK (role IN ('owner','admin','department_admin','faculty','faculty_lite')), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    UNIQUE (organization_id, id), 
    UNIQUE (organization_id, user_id)
);

CREATE INDEX ix_memberships_organization_id ON memberships (organization_id);

CREATE INDEX ix_memberships_user_id ON memberships (user_id);

CREATE TABLE department_assignments (
    organization_id UUID NOT NULL, 
    membership_id UUID NOT NULL, 
    department_id UUID NOT NULL, 
    PRIMARY KEY (organization_id, membership_id, department_id), 
    FOREIGN KEY(organization_id, department_id) REFERENCES departments (organization_id, id), 
    FOREIGN KEY(organization_id, membership_id) REFERENCES memberships (organization_id, id)
);

CREATE TABLE presentations (
    organization_id UUID NOT NULL, 
    owner_id UUID NOT NULL, 
    department_id UUID, 
    title VARCHAR(160) NOT NULL, 
    revision INTEGER NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, department_id) REFERENCES departments (organization_id, id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE INDEX ix_presentations_organization_id ON presentations (organization_id);

CREATE INDEX ix_presentations_owner_id ON presentations (owner_id);

INSERT INTO alembic_version (version_num) VALUES ('38225079a1ae') RETURNING alembic_version.version_num;

-- Running upgrade 38225079a1ae -> 942331ac7bf1

CREATE TABLE bank_questions (
    organization_id UUID NOT NULL, 
    owner_id UUID NOT NULL, 
    subject VARCHAR(120) NOT NULL, 
    chapter VARCHAR(120) NOT NULL, 
    topic VARCHAR(120) NOT NULL, 
    difficulty VARCHAR(20) NOT NULL, 
    tags JSON NOT NULL, 
    question JSON NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE INDEX ix_bank_questions_organization_id ON bank_questions (organization_id);

CREATE INDEX ix_bank_questions_owner_id ON bank_questions (owner_id);

CREATE TABLE live_sessions (
    presentation_id UUID NOT NULL, 
    organization_id UUID NOT NULL, 
    owner_id UUID NOT NULL, 
    join_code VARCHAR(6), 
    state VARCHAR(20) NOT NULL, 
    active_index INTEGER NOT NULL, 
    revision INTEGER NOT NULL, 
    questions JSON NOT NULL, 
    opened_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    FOREIGN KEY(owner_id) REFERENCES users (id), 
    FOREIGN KEY(presentation_id) REFERENCES presentations (id), 
    UNIQUE (join_code)
);

CREATE INDEX ix_live_sessions_organization_id ON live_sessions (organization_id);

CREATE INDEX ix_live_sessions_presentation_id ON live_sessions (presentation_id);

CREATE TABLE slides (
    presentation_id UUID NOT NULL, 
    ordinal INTEGER NOT NULL, 
    question JSON NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(presentation_id) REFERENCES presentations (id), 
    UNIQUE (presentation_id, ordinal)
);

CREATE INDEX ix_slides_presentation_id ON slides (presentation_id);

CREATE TABLE participants (
    session_id UUID NOT NULL, 
    nickname VARCHAR(60) NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(session_id) REFERENCES live_sessions (id), 
    UNIQUE (token_hash)
);

CREATE INDEX ix_participants_session_id ON participants (session_id);

CREATE TABLE answers (
    session_id UUID NOT NULL, 
    participant_id UUID NOT NULL, 
    question_index INTEGER NOT NULL, 
    value JSON NOT NULL, 
    correct BOOLEAN, 
    score INTEGER NOT NULL, 
    elapsed_ms INTEGER NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(participant_id) REFERENCES participants (id), 
    FOREIGN KEY(session_id) REFERENCES live_sessions (id), 
    UNIQUE (session_id, participant_id, question_index)
);

CREATE INDEX ix_answers_session_id ON answers (session_id);

UPDATE alembic_version SET version_num='942331ac7bf1' WHERE alembic_version.version_num = '38225079a1ae';

-- Running upgrade 942331ac7bf1 -> 4b02c14516f0

CREATE TABLE import_batches (
    organization_id UUID NOT NULL, 
    owner_id UUID NOT NULL, 
    rows JSON NOT NULL, 
    errors JSON NOT NULL, 
    committed BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id) REFERENCES organizations (id), 
    FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE INDEX ix_import_batches_organization_id ON import_batches (organization_id);

UPDATE alembic_version SET version_num='4b02c14516f0' WHERE alembic_version.version_num = '942331ac7bf1';

COMMIT;

