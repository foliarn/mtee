-- MTEE Remote, plan 126.7: the records that travel (playlists and track data).

-- The playlist of this computer and its server copy, with the revisions both sides had when they
-- last agreed. A change on one side is a revision above its synced one.
CREATE TABLE remote_playlists (
    local_playlist_id TEXT PRIMARY KEY,
    server_playlist_id TEXT NOT NULL UNIQUE,
    synced_local_revision INTEGER NOT NULL,
    synced_server_revision INTEGER NOT NULL,
    synced_at_utc TEXT NOT NULL
);

-- The digest (SHA-256 of the canonical JSON) of each track data layer as it was last sent or
-- received, so that a layer is sent only when it changed and a received one is not sent back.
CREATE TABLE remote_track_data_sync (
    item_id TEXT NOT NULL,
    layer TEXT NOT NULL,
    digest TEXT NOT NULL,
    PRIMARY KEY (item_id, layer)
);
