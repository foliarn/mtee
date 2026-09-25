CREATE TABLE conversion_attempts (
    conversion_id TEXT PRIMARY KEY,
    source_track_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    destination_path TEXT NOT NULL,
    source_size_bytes INTEGER NOT NULL,
    source_mtime_ns INTEGER NOT NULL,
    source_file_id TEXT,
    source_generation INTEGER NOT NULL,
    source_sha256 TEXT NOT NULL DEFAULT '',
    output_sha256 TEXT NOT NULL DEFAULT '',
    parameters_json TEXT NOT NULL,
    ffmpeg_version TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN ('prepared','running','completed','failed','cancelled','conflict')),
    validation_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE derivations (
    derived_track_id TEXT PRIMARY KEY,
    source_track_id TEXT NOT NULL,
    source_size_bytes INTEGER NOT NULL,
    source_mtime_ns INTEGER NOT NULL,
    source_file_id TEXT,
    source_generation INTEGER NOT NULL,
    conversion_id TEXT NOT NULL UNIQUE REFERENCES conversion_attempts(conversion_id),
    parameters_json TEXT NOT NULL,
    time_mapping_status TEXT NOT NULL CHECK (time_mapping_status IN ('identity','converted','unknown')),
    created_at_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX derivations_source_track_id_idx ON derivations(source_track_id);
