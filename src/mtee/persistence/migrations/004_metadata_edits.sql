CREATE TABLE metadata_edit_operations (
    operation_id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL,
    track_id TEXT NOT NULL REFERENCES tracks(track_id),
    source_path TEXT NOT NULL,
    expected_generation INTEGER NOT NULL,
    expected_size_bytes INTEGER NOT NULL,
    expected_mtime_ns INTEGER NOT NULL,
    source_sha256 TEXT NOT NULL,
    new_sha256 TEXT,
    temporary_path TEXT NOT NULL,
    backup_path TEXT NOT NULL,
    before_json TEXT NOT NULL,
    after_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'prepared', 'publishing', 'published', 'completed', 'failed',
        'conflict', 'needs_recovery', 'undone'
    )),
    error TEXT NOT NULL DEFAULT '',
    undo_of TEXT REFERENCES metadata_edit_operations(operation_id),
    undone_by TEXT REFERENCES metadata_edit_operations(operation_id),
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE INDEX metadata_edit_track_history
    ON metadata_edit_operations(track_id, created_at_utc DESC);
