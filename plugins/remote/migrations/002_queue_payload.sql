-- MTEE Remote, plan 126.3: the queue keeps the payload of each operation, and the state of a
-- blocked operation is added (a path taken or a stale revision waits for the person, plan 126.6).
-- A link keeps the server path that the item had when this computer last saw it: the move rule
-- compares it with the local path.

ALTER TABLE remote_links ADD COLUMN server_path TEXT;

-- SQLite cannot change a CHECK constraint in place, so the queue is rebuilt with the same rows.
CREATE TABLE remote_queue_next (
    op_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    track_id TEXT,
    item_id TEXT,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'running', 'failed', 'blocked', 'done')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

INSERT INTO remote_queue_next (op_id, kind, track_id, item_id, state, attempts, last_error,
    payload_json, created_at_utc, updated_at_utc)
SELECT op_id, kind, track_id, item_id, state, attempts, last_error, '{}', created_at_utc,
    updated_at_utc
FROM remote_queue;

DROP TABLE remote_queue;
ALTER TABLE remote_queue_next RENAME TO remote_queue;
CREATE INDEX remote_queue_state ON remote_queue (state);
