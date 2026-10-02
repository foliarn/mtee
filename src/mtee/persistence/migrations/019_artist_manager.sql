CREATE TABLE artists (
    artist_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    name_origin TEXT NOT NULL DEFAULT 'auto' CHECK (name_origin IN ('auto', 'manual')),
    state TEXT NOT NULL DEFAULT 'provisional'
        CHECK (state IN ('provisional', 'established', 'retired')),
    merged_into TEXT REFERENCES artists(artist_id),
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE UNIQUE INDEX artists_active_key ON artists(name_key) WHERE state <> 'retired';

CREATE TABLE artist_name_observations (
    artist_id TEXT NOT NULL REFERENCES artists(artist_id),
    track_id TEXT NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
    spelling TEXT NOT NULL,
    provenance TEXT NOT NULL,
    UNIQUE (track_id, provenance, spelling)
);

CREATE INDEX artist_name_observations_artist ON artist_name_observations(artist_id);

CREATE TABLE artist_aliases (
    alias_key TEXT PRIMARY KEY,
    artist_id TEXT NOT NULL REFERENCES artists(artist_id),
    spelling TEXT NOT NULL
);

CREATE TABLE track_artist_review (
    track_id TEXT PRIMARY KEY REFERENCES tracks(track_id) ON DELETE CASCADE,
    category TEXT NOT NULL CHECK (category IN ('from_tags', 'suggested', 'needs_input')),
    initial_category TEXT NOT NULL,
    review_state TEXT NOT NULL DEFAULT 'pending' CHECK (review_state IN ('pending', 'confirmed')),
    apply_state TEXT NOT NULL DEFAULT 'none'
        CHECK (apply_state IN ('none', 'queued', 'running', 'succeeded', 'failed', 'cancelled')),
    apply_error TEXT NOT NULL DEFAULT '',
    apply_note TEXT NOT NULL DEFAULT '',
    apply_write_tags INTEGER NOT NULL DEFAULT 0,
    source_size_bytes INTEGER,
    source_mtime_ns INTEGER,
    source_generation INTEGER,
    original_artists_json TEXT NOT NULL,
    original_title TEXT NOT NULL,
    proposal_source TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    proposed_title TEXT NOT NULL,
    confirmed_title TEXT,
    rules_version INTEGER NOT NULL,
    decision_version INTEGER NOT NULL DEFAULT 1,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE INDEX track_artist_review_category ON track_artist_review(category, review_state, apply_state);

CREATE TABLE track_artist_credits (
    track_id TEXT NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
    artist_id TEXT NOT NULL REFERENCES artists(artist_id),
    position INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'artist' CHECK (role IN ('artist', 'remixer')),
    confirmed INTEGER NOT NULL DEFAULT 0 CHECK (confirmed IN (0, 1)),
    PRIMARY KEY (track_id, confirmed, position),
    UNIQUE (track_id, confirmed, artist_id)
);

CREATE INDEX track_artist_credits_artist ON track_artist_credits(artist_id, confirmed);

CREATE TABLE artist_workflow (
    workflow_id INTEGER PRIMARY KEY CHECK (workflow_id = 1),
    mode TEXT NOT NULL CHECK (mode IN ('guided', 'free')),
    unlocked_step INTEGER NOT NULL DEFAULT 0,
    cohort_registered INTEGER NOT NULL DEFAULT 0 CHECK (cohort_registered IN (0, 1)),
    completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
    created_at_utc TEXT NOT NULL
);

CREATE TABLE artist_cohort (
    track_id TEXT PRIMARY KEY REFERENCES tracks(track_id) ON DELETE CASCADE
);

CREATE TABLE artist_operations (
    operation_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('confirm', 'rename', 'merge', 'delete')),
    label TEXT NOT NULL DEFAULT '',
    write_tags INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN (
        'prepared', 'running', 'completed', 'partial', 'cancelled', 'failed', 'undone'
    )),
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE artist_operation_items (
    operation_id TEXT NOT NULL REFERENCES artist_operations(operation_id),
    track_id TEXT NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
    mode TEXT NOT NULL DEFAULT 'full' CHECK (mode IN ('full', 'tags_only')),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'undone')),
    decision_version INTEGER NOT NULL,
    before_json TEXT NOT NULL DEFAULT '{}',
    path_before TEXT NOT NULL DEFAULT '',
    path_target TEXT NOT NULL DEFAULT '',
    path_final TEXT NOT NULL DEFAULT '',
    revision_before_json TEXT NOT NULL DEFAULT '',
    revision_after_json TEXT NOT NULL DEFAULT '',
    tags_phase TEXT NOT NULL DEFAULT 'pending'
        CHECK (tags_phase IN ('pending', 'done', 'unsupported', 'skipped')),
    tag_operation_id TEXT NOT NULL DEFAULT '',
    rename_phase TEXT NOT NULL DEFAULT 'pending' CHECK (rename_phase IN ('pending', 'done', 'noop')),
    error TEXT NOT NULL DEFAULT '',
    warning TEXT NOT NULL DEFAULT '',
    updated_at_utc TEXT NOT NULL,
    PRIMARY KEY (operation_id, track_id)
);

CREATE INDEX artist_operation_items_track ON artist_operation_items(track_id, updated_at_utc DESC);
