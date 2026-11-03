-- MTEE Remote, records (milestone 126.7): play log, playlists, per-track data and synced
-- settings. The values are opaque JSON text; the server stores them without interpreting them.

CREATE TABLE play_events (
    user_id TEXT NOT NULL REFERENCES users ON DELETE CASCADE,
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    device_id TEXT,
    payload_json TEXT NOT NULL,
    received_at_utc TEXT NOT NULL,
    UNIQUE(user_id, event_id)
);

CREATE TABLE record_playlists (
    user_id TEXT NOT NULL REFERENCES users ON DELETE CASCADE,
    playlist_id TEXT NOT NULL,
    name TEXT NOT NULL,
    revision INTEGER NOT NULL,
    entries_json TEXT NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0,
    updated_at_utc TEXT NOT NULL,
    updated_by_device_id TEXT,
    PRIMARY KEY(user_id, playlist_id)
);

CREATE TABLE record_track_data (
    user_id TEXT NOT NULL REFERENCES users ON DELETE CASCADE,
    item_id TEXT NOT NULL,
    layer TEXT NOT NULL CHECK (layer IN ('analysis', 'loudness', 'corrections')),
    value_json TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    PRIMARY KEY(user_id, item_id, layer)
);

CREATE TABLE record_settings (
    user_id TEXT NOT NULL REFERENCES users ON DELETE CASCADE,
    key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    PRIMARY KEY(user_id, key)
);
