CREATE TABLE genres (
    genre_id TEXT PRIMARY KEY,
    parent_id TEXT REFERENCES genres(genre_id),
    name TEXT NOT NULL,
    name_key TEXT NOT NULL CHECK(length(name_key)>0),
    position INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
    revision INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX genres_root_name ON genres(name_key) WHERE parent_id IS NULL;
CREATE UNIQUE INDEX genres_child_name ON genres(parent_id,name_key) WHERE parent_id IS NOT NULL;
CREATE INDEX genres_parent ON genres(parent_id,position);
CREATE TABLE genre_aliases (
    genre_id TEXT NOT NULL REFERENCES genres(genre_id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_key TEXT NOT NULL,
    PRIMARY KEY(genre_id,alias_key)
);
CREATE INDEX genre_alias_search ON genre_aliases(alias_key);
CREATE TABLE genre_meta_families (
    meta_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
    revision INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE genre_meta_members (
    meta_id TEXT NOT NULL REFERENCES genre_meta_families(meta_id) ON DELETE CASCADE,
    genre_id TEXT NOT NULL REFERENCES genres(genre_id) ON DELETE CASCADE,
    PRIMARY KEY(meta_id,genre_id)
);
CREATE INDEX genre_meta_by_genre ON genre_meta_members(genre_id);
CREATE TABLE track_genres (
    track_id TEXT NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
    genre_id TEXT NOT NULL REFERENCES genres(genre_id),
    provenance TEXT NOT NULL CHECK(provenance IN ('folder','manual')),
    operation_id TEXT NOT NULL,
    assigned_at_utc TEXT NOT NULL,
    PRIMARY KEY(track_id,genre_id)
);
CREATE INDEX track_genres_by_genre ON track_genres(genre_id,track_id);
CREATE TABLE local_tags (
    tag_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    color TEXT,
    archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
    revision INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE track_local_tags (
    track_id TEXT NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
    tag_id TEXT NOT NULL REFERENCES local_tags(tag_id),
    operation_id TEXT NOT NULL,
    assigned_at_utc TEXT NOT NULL,
    PRIMARY KEY(track_id,tag_id)
);
CREATE INDEX track_tags_by_tag ON track_local_tags(tag_id,track_id);
-- These durable states and history deliberately have no FK to tracks or definitions.
CREATE TABLE genre_track_state (
    track_id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL DEFAULT 0,
    manual_edit INTEGER NOT NULL DEFAULT 0 CHECK(manual_edit IN (0,1)),
    seed_run_id TEXT,
    seed_folder TEXT
);
CREATE TABLE genre_seed_runs (
    run_id TEXT PRIMARY KEY,
    root_id TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    backup_path TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE genre_seed_tracks (
    run_id TEXT NOT NULL REFERENCES genre_seed_runs(run_id),
    track_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    PRIMARY KEY(run_id,track_id)
);
CREATE TABLE genre_operations (
    operation_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('committed','undone')),
    inverse_operation_id TEXT,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE genre_operation_items (
    operation_id TEXT NOT NULL REFERENCES genre_operations(operation_id),
    target_id TEXT NOT NULL,
    before_json TEXT NOT NULL,
    after_json TEXT NOT NULL,
    expected_revision INTEGER NOT NULL,
    PRIMARY KEY(operation_id,target_id)
);
