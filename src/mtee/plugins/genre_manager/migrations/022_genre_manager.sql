-- Genre Manager has a new contract. Version 021 is intentionally absent.
CREATE TABLE gm_genres (
    genre_id TEXT PRIMARY KEY,
    parent_id TEXT REFERENCES gm_genres(genre_id),
    name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    CHECK (parent_id IS NULL OR parent_id <> genre_id)
);
CREATE UNIQUE INDEX gm_genres_sibling_name ON gm_genres(COALESCE(parent_id, ''), name_key);
CREATE INDEX gm_genres_parent_order ON gm_genres(parent_id, sort_order, name);

CREATE TABLE gm_genre_aliases (
    genre_id TEXT NOT NULL REFERENCES gm_genres(genre_id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_key TEXT NOT NULL,
    PRIMARY KEY (genre_id, alias_key)
);

CREATE TABLE gm_tags (
    tag_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE gm_track_state (
    track_id TEXT PRIMARY KEY REFERENCES tracks(track_id) ON DELETE CASCADE,
    genre_revision INTEGER NOT NULL DEFAULT 0,
    tag_revision INTEGER NOT NULL DEFAULT 0,
    reviewed_revision INTEGER,
    updated_at_utc TEXT NOT NULL,
    CHECK (reviewed_revision IS NULL OR reviewed_revision <= genre_revision)
);
CREATE INDEX gm_track_state_reviewed ON gm_track_state(reviewed_revision, genre_revision);

CREATE TABLE gm_track_genres (
    track_id TEXT NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
    genre_id TEXT NOT NULL REFERENCES gm_genres(genre_id),
    position INTEGER NOT NULL CHECK (position >= 0),
    PRIMARY KEY (track_id, genre_id),
    UNIQUE (track_id, position)
);
CREATE INDEX gm_track_genres_genre ON gm_track_genres(genre_id, track_id);

CREATE TABLE gm_track_tags (
    track_id TEXT NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
    tag_id TEXT NOT NULL REFERENCES gm_tags(tag_id),
    PRIMARY KEY (track_id, tag_id)
);
CREATE INDEX gm_track_tags_tag ON gm_track_tags(tag_id, track_id);

CREATE TABLE gm_decision_operations (
    operation_id TEXT PRIMARY KEY,
    track_id TEXT NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('genres', 'tags', 'review')),
    before_json TEXT NOT NULL,
    after_json TEXT NOT NULL,
    before_revision INTEGER NOT NULL,
    after_revision INTEGER NOT NULL,
    undone INTEGER NOT NULL DEFAULT 0 CHECK (undone IN (0, 1)),
    created_at_utc TEXT NOT NULL
);
CREATE INDEX gm_decision_operations_track ON gm_decision_operations(track_id, created_at_utc DESC);

CREATE TABLE gm_sessions (
    session_id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('folder', 'playlist', 'new')),
    root_id TEXT REFERENCES library_roots(root_id),
    source_key TEXT NOT NULL,
    source_label TEXT NOT NULL,
    include_subfolders INTEGER NOT NULL DEFAULT 0 CHECK (include_subfolders IN (0, 1)),
    view_mode TEXT NOT NULL DEFAULT 'all' CHECK (view_mode IN ('all', 'to_review')),
    interaction_mode TEXT NOT NULL DEFAULT 'selection'
        CHECK (interaction_mode IN ('selection', 'brush')),
    search_text TEXT NOT NULL DEFAULT '',
    selected_json TEXT NOT NULL DEFAULT '[]',
    brush_kind TEXT NOT NULL DEFAULT 'genre' CHECK (brush_kind IN ('genre', 'tag')),
    brush_id TEXT NOT NULL DEFAULT '',
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
CREATE TABLE gm_session_tracks (
    session_id TEXT NOT NULL REFERENCES gm_sessions(session_id) ON DELETE CASCADE,
    track_id TEXT NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    PRIMARY KEY (session_id, track_id),
    UNIQUE (session_id, position)
);
CREATE INDEX gm_session_tracks_track ON gm_session_tracks(track_id, session_id);

CREATE TABLE gm_destinations (
    root_id TEXT NOT NULL REFERENCES library_roots(root_id) ON DELETE CASCADE,
    genre_id TEXT NOT NULL REFERENCES gm_genres(genre_id),
    relative_folder TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    PRIMARY KEY (root_id, genre_id)
);

CREATE TABLE gm_organization_operations (
    operation_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES gm_sessions(session_id),
    status TEXT NOT NULL CHECK (status IN
        ('prepared', 'running', 'completed', 'partial', 'cancelled', 'failed')),
    preview_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
CREATE TABLE gm_organization_items (
    operation_id TEXT NOT NULL REFERENCES gm_organization_operations(operation_id),
    track_id TEXT NOT NULL REFERENCES tracks(track_id),
    ordinal INTEGER NOT NULL,
    source_path TEXT NOT NULL,
    destination_path TEXT NOT NULL,
    source_revision_json TEXT NOT NULL,
    genre_revision INTEGER NOT NULL,
    genre_id TEXT NOT NULL REFERENCES gm_genres(genre_id),
    phase TEXT NOT NULL CHECK (phase IN
        ('prepared', 'moving', 'moved', 'catalogued', 'completed', 'conflict', 'failed', 'undone')),
    error TEXT NOT NULL DEFAULT '',
    updated_at_utc TEXT NOT NULL,
    PRIMARY KEY (operation_id, track_id),
    UNIQUE (operation_id, ordinal),
    UNIQUE (operation_id, destination_path)
);
CREATE INDEX gm_organization_items_phase ON gm_organization_items(phase, operation_id);

CREATE TABLE gm_artist_contributions (
    track_id TEXT NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
    artist_id TEXT NOT NULL REFERENCES artists(artist_id),
    genre_id TEXT NOT NULL REFERENCES gm_genres(genre_id),
    decision_source TEXT NOT NULL CHECK (decision_source IN ('rule', 'manual')),
    rules_version INTEGER NOT NULL,
    updated_at_utc TEXT NOT NULL,
    PRIMARY KEY (track_id, artist_id, genre_id)
);
CREATE INDEX gm_artist_contributions_artist ON gm_artist_contributions(artist_id, genre_id);

CREATE TABLE gm_artist_uncertainties (
    track_id TEXT NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
    genre_id TEXT NOT NULL REFERENCES gm_genres(genre_id),
    reason TEXT NOT NULL,
    title_excerpt TEXT NOT NULL,
    rules_version INTEGER NOT NULL,
    updated_at_utc TEXT NOT NULL,
    PRIMARY KEY (track_id, genre_id)
);
