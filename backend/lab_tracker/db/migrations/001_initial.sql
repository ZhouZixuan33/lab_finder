CREATE TABLE professors (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    title TEXT NOT NULL,
    email TEXT,
    directory_profile_url TEXT NOT NULL UNIQUE,
    homepage_url TEXT,
    lab_url TEXT,
    research_summary TEXT NOT NULL,
    tags_json TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(tags_json) AND json_type(tags_json) = 'array'),
    source_urls_json TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(source_urls_json) AND json_type(source_urls_json) = 'array'),
    source_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_checked_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_professors_normalized_name
ON professors(lower(trim(name)));

CREATE INDEX idx_professors_normalized_email
ON professors(lower(email))
WHERE email IS NOT NULL;

CREATE TABLE application_status (
    id INTEGER PRIMARY KEY,
    professor_id INTEGER NOT NULL UNIQUE,
    state TEXT NOT NULL
        CHECK (state IN ('interested', 'applied', 'accepted', 'rejected')),
    application_date TEXT,
    notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    FOREIGN KEY (professor_id) REFERENCES professors(id) ON DELETE CASCADE
);

CREATE INDEX idx_application_status_state
ON application_status(state);

CREATE TABLE publications (
    id INTEGER PRIMARY KEY,
    professor_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    year INTEGER NOT NULL,
    venue TEXT,
    publication_url TEXT,
    doi TEXT,
    source TEXT NOT NULL
        CHECK (source IN ('faculty_page', 'lab_page', 'openalex')),
    created_at TEXT NOT NULL,
    FOREIGN KEY (professor_id) REFERENCES professors(id) ON DELETE CASCADE,
    UNIQUE (professor_id, title, year)
);

CREATE INDEX idx_publications_professor_year
ON publications(professor_id, year DESC);

CREATE TABLE update_proposals (
    id INTEGER PRIMARY KEY,
    job_id TEXT NOT NULL,
    professor_id INTEGER NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('pending', 'applied', 'rejected')),
    old_values_json TEXT
        CHECK (old_values_json IS NULL OR json_valid(old_values_json)),
    new_values_json TEXT
        CHECK (new_values_json IS NULL OR json_valid(new_values_json)),
    publication_diff_json TEXT
        CHECK (publication_diff_json IS NULL OR json_valid(publication_diff_json)),
    source_urls_json TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(source_urls_json) AND json_type(source_urls_json) = 'array'),
    confidence REAL
        CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (professor_id) REFERENCES professors(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX uq_pending_proposal_per_professor
ON update_proposals(professor_id)
WHERE status = 'pending';

CREATE INDEX idx_update_proposals_job_id
ON update_proposals(job_id);

CREATE INDEX idx_update_proposals_status_created
ON update_proposals(status, created_at DESC);
