-- Early schema-16 databases may predate the import journal. Apply a new
-- version so they are upgraded too; keep existing journal rows unchanged.
CREATE TABLE IF NOT EXISTS playlist_imports (
    operation_id TEXT PRIMARY KEY,
    archive_path TEXT NOT NULL,
    folder_path TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    phase TEXT NOT NULL,
    error TEXT NOT NULL DEFAULT '',
    result_playlist_id TEXT REFERENCES playlists(playlist_id) ON DELETE SET NULL
);
