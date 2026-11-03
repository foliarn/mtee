-- MTEE Remote, plan 126.2: the link table, the server items, the first match and the sync
-- bookkeeping. Every table name starts with remote_. A hash is a matching key, never an
-- identity: a track is linked to one server item through remote_links, and that is all.

-- A local track linked to one server item. The audio hash is kept with the link for the
-- matching of later runs; the SHA-256 is the file's own, and it is the one that tells a
-- replacement from the same file.
CREATE TABLE remote_links (
    track_id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL,
    item_revision INTEGER NOT NULL DEFAULT 0,
    local_sha256 TEXT NOT NULL,
    audio_hash TEXT,
    linked_at_utc TEXT NOT NULL
);
CREATE UNIQUE INDEX remote_links_item_id ON remote_links (item_id);

-- The server's view of the items that have no local track (server only). Filled by the first
-- match and, later, by the fetch of plan 126.4.
CREATE TABLE remote_server_items (
    item_id TEXT PRIMARY KEY,
    root_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    sha256 TEXT,
    audio_hash TEXT,
    revision INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT,
    source_track_id TEXT,
    updated_at_utc TEXT NOT NULL DEFAULT ''
);
CREATE INDEX remote_server_items_sha256 ON remote_server_items (sha256);
CREATE INDEX remote_server_items_audio_hash ON remote_server_items (audio_hash);

-- A watched folder of this computer and the server folder it is synced with. The subpath is
-- relative to the root and empty for the whole root.
CREATE TABLE remote_mappings (
    local_root_path TEXT PRIMARY KEY,
    server_root_id TEXT NOT NULL,
    server_subpath TEXT NOT NULL DEFAULT ''
);

-- Work waiting for the sync: uploads (126.3), moves and replacements, downloads (126.4).
CREATE TABLE remote_queue (
    op_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    track_id TEXT,
    item_id TEXT,
    state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'running', 'failed', 'done')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
CREATE INDEX remote_queue_state ON remote_queue (state);

-- Two versions of one track that the sync cannot settle alone. The state is open until the
-- person chooses (126.6); decide_later is the default of a first match.
CREATE TABLE remote_conflicts (
    conflict_id TEXT PRIMARY KEY,
    track_id TEXT,
    item_id TEXT,
    local_json TEXT NOT NULL DEFAULT '{}',
    server_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'open'
        CHECK (state IN ('open', 'decide_later', 'resolved'))
);
CREATE INDEX remote_conflicts_track ON remote_conflicts (track_id);

-- The hashes of a local file, keyed by its path and its size and modification time. A file
-- whose size and time are unchanged is never hashed twice.
CREATE TABLE remote_hash_cache (
    path TEXT PRIMARY KEY,
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    audio_hash TEXT
);

-- The activity log of the plugin, newest last.
CREATE TABLE remote_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    at_utc TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'info' CHECK (level IN ('info', 'warning', 'error')),
    text TEXT NOT NULL
);

-- Named positions in the server's journal and in the play log.
CREATE TABLE remote_cursors (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
