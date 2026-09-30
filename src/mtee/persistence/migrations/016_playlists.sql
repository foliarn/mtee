CREATE TABLE playlist_folders (
    folder_id TEXT PRIMARY KEY,
    parent_id TEXT REFERENCES playlist_folders(folder_id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE playlists (
    playlist_id TEXT PRIMARY KEY,
    folder_id TEXT REFERENCES playlist_folders(folder_id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    cover_ref TEXT NOT NULL DEFAULT '',
    pinned INTEGER NOT NULL DEFAULT 0 CHECK(pinned IN (0,1)),
    ordinal INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 0,
    updated_at_utc TEXT NOT NULL
);
CREATE TABLE playlist_entries (
    entry_id TEXT PRIMARY KEY,
    playlist_id TEXT NOT NULL REFERENCES playlists(playlist_id) ON DELETE CASCADE,
    track_id TEXT REFERENCES tracks(track_id) ON DELETE SET NULL,
    ordinal INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    UNIQUE(playlist_id,ordinal),
    UNIQUE(playlist_id,track_id)
);
CREATE TABLE liked_tracks (
    track_id TEXT PRIMARY KEY REFERENCES tracks(track_id) ON DELETE CASCADE,
    liked_at_utc TEXT NOT NULL
);
CREATE INDEX playlist_folder_parent ON playlist_folders(parent_id,ordinal);
CREATE INDEX playlist_folder ON playlists(folder_id,ordinal);
CREATE INDEX playlist_entry_track ON playlist_entries(track_id);
CREATE TABLE playlist_imports (
    operation_id TEXT PRIMARY KEY,
    archive_path TEXT NOT NULL,
    folder_path TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    phase TEXT NOT NULL,
    error TEXT NOT NULL DEFAULT '',
    result_playlist_id TEXT REFERENCES playlists(playlist_id) ON DELETE SET NULL
);
