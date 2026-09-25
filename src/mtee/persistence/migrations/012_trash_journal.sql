CREATE TABLE trash_operations (
    operation_id TEXT PRIMARY KEY,
    track_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    expected_size_bytes INTEGER NOT NULL,
    expected_mtime_ns INTEGER NOT NULL,
    expected_file_id TEXT,
    expected_generation INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('prepared','recycled','failed','conflict')),
    result_message TEXT NOT NULL DEFAULT '',
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE INDEX trash_operations_status_time
    ON trash_operations(status, created_at_utc);
