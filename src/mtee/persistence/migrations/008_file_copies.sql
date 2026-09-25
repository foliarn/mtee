CREATE TABLE file_copy_operations (
    operation_id TEXT PRIMARY KEY,
    source_track_id TEXT NOT NULL REFERENCES tracks(track_id),
    copied_track_id TEXT REFERENCES tracks(track_id),
    source_path TEXT NOT NULL,
    destination_path TEXT NOT NULL,
    temporary_path TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    expected_size_bytes INTEGER NOT NULL,
    expected_mtime_ns INTEGER NOT NULL,
    expected_file_id TEXT,
    expected_generation INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('prepared','completed','failed','needs_recovery')),
    error TEXT NOT NULL DEFAULT '',
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE INDEX file_copy_operations_pending
    ON file_copy_operations(status) WHERE status IN ('prepared','needs_recovery');
