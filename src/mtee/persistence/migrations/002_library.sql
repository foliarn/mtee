CREATE TABLE library_roots (
    root_id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    path_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    availability TEXT NOT NULL DEFAULT 'available'
        CHECK (availability IN ('available', 'scanning', 'partial', 'unavailable')),
    scan_generation INTEGER NOT NULL DEFAULT 0,
    last_scan_utc TEXT
);

CREATE TABLE tracks (
    track_id TEXT PRIMARY KEY
);

CREATE TABLE track_locations (
    path_key TEXT PRIMARY KEY,
    track_id TEXT NOT NULL UNIQUE REFERENCES tracks(track_id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    file_id TEXT,
    generation INTEGER NOT NULL DEFAULT 0,
    duration_us INTEGER,
    status TEXT NOT NULL CHECK (status IN ('readable', 'unreadable')),
    metadata_json TEXT NOT NULL
);

CREATE TABLE root_tracks (
    root_id TEXT NOT NULL REFERENCES library_roots(root_id) ON DELETE CASCADE,
    track_id TEXT NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL,
    seen_generation INTEGER NOT NULL,
    present INTEGER NOT NULL DEFAULT 1 CHECK (present IN (0, 1)),
    PRIMARY KEY (root_id, track_id),
    UNIQUE (root_id, relative_path)
);

CREATE INDEX root_tracks_folder ON root_tracks(root_id, relative_path, present);

CREATE TABLE library_folders (
    root_id TEXT NOT NULL REFERENCES library_roots(root_id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL,
    seen_generation INTEGER NOT NULL,
    present INTEGER NOT NULL DEFAULT 1 CHECK (present IN (0, 1)),
    PRIMARY KEY (root_id, relative_path)
);
