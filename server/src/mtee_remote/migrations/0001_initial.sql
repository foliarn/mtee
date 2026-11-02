-- MTEE Remote, first schema. Times are UTC ISO-8601 text. Folders are not stored:
-- they are derived from the relative paths of the items.

CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    disabled INTEGER NOT NULL DEFAULT 0,
    quota_bytes INTEGER,
    -- Relative to the music volume; normally the username.
    library_dir TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

CREATE TABLE devices (
    device_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('desktop', 'phone', 'web')),
    token_hash TEXT NOT NULL UNIQUE,
    created_at_utc TEXT NOT NULL,
    last_seen_utc TEXT,
    revoked_at_utc TEXT
);

CREATE INDEX devices_user ON devices(user_id);

CREATE TABLE roots (
    root_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    -- Relative to the user's library folder; '' means the whole library folder.
    relative_dir TEXT NOT NULL,
    adopted INTEGER NOT NULL DEFAULT 0,
    created_at_utc TEXT NOT NULL,
    UNIQUE (user_id, name)
);

CREATE TABLE items (
    item_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    root_id TEXT NOT NULL REFERENCES roots(root_id),
    relative_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    inode INTEGER,
    sha256 TEXT,
    audio_hash TEXT,
    hash_state TEXT NOT NULL DEFAULT 'pending' CHECK (hash_state IN ('pending', 'done', 'error')),
    metadata_json TEXT,
    duration_us INTEGER,
    revision INTEGER NOT NULL DEFAULT 1,
    state TEXT NOT NULL DEFAULT 'present' CHECK (state IN ('present', 'trashed')),
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE UNIQUE INDEX items_present_path ON items(root_id, relative_path) WHERE state = 'present';
CREATE INDEX items_user_sha256 ON items(user_id, sha256);
CREATE INDEX items_user_audio_hash ON items(user_id, audio_hash);

CREATE TABLE item_revisions (
    item_id TEXT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    sha256 TEXT,
    size_bytes INTEGER NOT NULL,
    device_id TEXT,
    at_utc TEXT NOT NULL,
    PRIMARY KEY (item_id, revision)
);

CREATE TABLE journal (
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    item_id TEXT,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    at_utc TEXT NOT NULL,
    PRIMARY KEY (user_id, seq)
);

CREATE TABLE device_cursors (
    device_id TEXT PRIMARY KEY REFERENCES devices(device_id) ON DELETE CASCADE,
    seq INTEGER NOT NULL
);

CREATE TABLE uploads (
    upload_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    device_id TEXT NOT NULL,
    purpose TEXT NOT NULL CHECK (purpose IN ('item', 'backup')),
    root_id TEXT,
    relative_path TEXT,
    base_item_id TEXT,
    base_revision INTEGER,
    label TEXT,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    received_bytes INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'conflict', 'done', 'cancelled')),
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE trash (
    trash_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('item', 'backup')),
    item_id TEXT,
    backup_id TEXT,
    -- Relative to <data>/trash/.
    stored_path TEXT NOT NULL,
    original_root_id TEXT,
    original_relative_path TEXT,
    size_bytes INTEGER NOT NULL,
    trashed_at_utc TEXT NOT NULL,
    trashed_by_device_id TEXT
);

CREATE TABLE backups (
    backup_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    device_id TEXT,
    label TEXT,
    kind TEXT NOT NULL CHECK (kind IN ('manual', 'automatic')),
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'present' CHECK (state IN ('present', 'trashed')),
    created_at_utc TEXT NOT NULL
);

CREATE TABLE server_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);

CREATE TABLE user_settings (
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    PRIMARY KEY (user_id, key)
);
