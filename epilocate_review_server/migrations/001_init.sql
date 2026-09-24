PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('reviewer', 'admin')),
    reviewer_slot INTEGER,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_token_hash TEXT NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at_utc TEXT NOT NULL,
    expires_at_utc TEXT NOT NULL,
    revoked_at_utc TEXT
);
CREATE INDEX IF NOT EXISTS sessions_expiry_idx ON sessions(expires_at_utc);

CREATE TABLE IF NOT EXISTS auth_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL COLLATE NOCASE,
    source_ip TEXT NOT NULL,
    attempted_at_utc TEXT NOT NULL,
    success INTEGER NOT NULL CHECK (success IN (0, 1))
);
CREATE INDEX IF NOT EXISTS auth_attempts_lookup_idx
    ON auth_attempts(username, source_ip, attempted_at_utc);

CREATE TABLE IF NOT EXISTS review_assignments (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    case_order INTEGER NOT NULL,
    left_candidate_key TEXT NOT NULL,
    right_candidate_key TEXT,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY (user_id, case_id)
);
CREATE INDEX IF NOT EXISTS assignments_case_idx ON review_assignments(case_id);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'SUBMITTED')),
    version INTEGER NOT NULL DEFAULT 1,
    observations_json TEXT NOT NULL DEFAULT '{}',
    decision TEXT NOT NULL DEFAULT 'PENDING',
    selected_series_uid TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    image_evidence_reviewed INTEGER NOT NULL DEFAULT 0 CHECK (image_evidence_reviewed IN (0, 1)),
    metadata_evidence_reviewed INTEGER NOT NULL DEFAULT 0 CHECK (metadata_evidence_reviewed IN (0, 1)),
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    submitted_at_utc TEXT,
    UNIQUE (user_id, case_id)
);
CREATE INDEX IF NOT EXISTS reviews_case_idx ON reviews(case_id);

CREATE TABLE IF NOT EXISTS review_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER NOT NULL REFERENCES users(id),
    case_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    review_id INTEGER REFERENCES reviews(id),
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS review_events_case_idx ON review_events(case_id, id);

CREATE TABLE IF NOT EXISTS final_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL UNIQUE,
    decision TEXT NOT NULL,
    selected_series_uid TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL,
    image_evidence_reviewed INTEGER NOT NULL CHECK (image_evidence_reviewed IN (0, 1)),
    metadata_evidence_reviewed INTEGER NOT NULL CHECK (metadata_evidence_reviewed IN (0, 1)),
    decided_by_user_id INTEGER NOT NULL REFERENCES users(id),
    reviewed_at_utc TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_version(version, applied_at_utc)
VALUES (1, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));
