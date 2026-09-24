CREATE TABLE file_operations (
    operation_id TEXT PRIMARY KEY,
    track_id TEXT NOT NULL REFERENCES tracks(track_id),
    kind TEXT NOT NULL CHECK (kind IN ('rename', 'move', 'undo_move')),
    source_path TEXT NOT NULL,
    destination_path TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    expected_size_bytes INTEGER NOT NULL,
    expected_mtime_ns INTEGER NOT NULL,
    expected_file_id TEXT,
    expected_generation INTEGER NOT NULL,
    result_size_bytes INTEGER,
    result_mtime_ns INTEGER,
    result_file_id TEXT,
    result_generation INTEGER,
    status TEXT NOT NULL CHECK (status IN (
        'prepared', 'completed', 'failed', 'needs_recovery', 'undone'
    )),
    error TEXT NOT NULL DEFAULT '',
    recovery_path TEXT,
    undo_of TEXT REFERENCES file_operations(operation_id),
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE INDEX file_operations_track_history
    ON file_operations(track_id, created_at_utc DESC);

CREATE INDEX file_operations_pending
    ON file_operations(status) WHERE status IN ('prepared','needs_recovery');
