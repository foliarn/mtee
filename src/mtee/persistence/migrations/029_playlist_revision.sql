-- Revision of a local playlist (plan 125.6), for the plugins that synchronize playlists.
-- It is a different counter from `version`, which the interface uses for its own optimistic
-- checks: `revision` rises by one on every change of the playlist made through any path
-- (the interface or a plugin), is never reset, and starts at 1 for the playlists that exist
-- when this script runs. The repository raises it in the same transaction as each change.
-- The trigger covers the one change no repository call makes: the library removing a track
-- turns the entry's track_id into NULL (ON DELETE SET NULL), which changes the playlist.
ALTER TABLE playlists ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1);

CREATE TRIGGER playlist_entry_unlinked AFTER UPDATE OF track_id ON playlist_entries
WHEN OLD.track_id IS NOT NULL AND NEW.track_id IS NULL
BEGIN
    UPDATE playlists SET revision = revision + 1 WHERE playlist_id = NEW.playlist_id;
END;
