-- Tracks that a plugin provides and that have no file on this computer (plan 125.2).
-- Each gets a normal row in `tracks` (a per-machine UUID), so playlists, the queue, the play
-- log and the analysis refer to it like to any track. The plugin's own key and the display
-- metadata live here, keyed by (plugin_id, source_key). Nothing here is a file: `track_locations`
-- and `root_tracks` never hold such a track, so the scanner and every file operation ignore it.
--
-- `available` is cleared by the plugin's `remove`: the row, its track_id, the playlist entries and
-- the play log rows stay; the track only cannot be played. `revision` rises when the metadata
-- changes, so the interface reads the cover again. `metadata_json` is a MetadataSnapshot.
CREATE TABLE plugin_source_tracks (
    plugin_id      TEXT NOT NULL CHECK (plugin_id <> ''),
    source_key     TEXT NOT NULL CHECK (source_key <> ''),
    track_id       TEXT NOT NULL UNIQUE REFERENCES tracks(track_id) ON DELETE CASCADE,
    metadata_json  TEXT NOT NULL,
    album_artist   TEXT NOT NULL DEFAULT '',
    available      INTEGER NOT NULL DEFAULT 1 CHECK (available IN (0, 1)),
    revision       INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    updated_at_utc TEXT NOT NULL,
    PRIMARY KEY (plugin_id, source_key)
);

CREATE INDEX plugin_source_tracks_plugin ON plugin_source_tracks(plugin_id, available);
