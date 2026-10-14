-- Journal permanent d'écoute : une ligne par écoute, ajoutée une seule fois.
-- Les colonnes *_at_* et artist/title/album/duration_us figent l'état du morceau au
-- moment de l'écoute ; track_id n'est pas une clé étrangère pour que les statistiques
-- survivent à la suppression d'une entrée de bibliothèque.
CREATE TABLE play_events (
    event_id TEXT PRIMARY KEY,
    track_id TEXT NOT NULL,
    path_at_play TEXT NOT NULL,
    artist TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    album TEXT NOT NULL DEFAULT '',
    duration_us INTEGER NOT NULL DEFAULT 0 CHECK (duration_us >= 0),
    started_at_utc TEXT NOT NULL,
    ended_at_utc TEXT NOT NULL,
    heard_ms INTEGER NOT NULL CHECK (heard_ms >= 0),
    counted INTEGER NOT NULL CHECK (counted IN (0, 1)),
    device_id TEXT NOT NULL
);

CREATE INDEX play_events_started ON play_events(started_at_utc);
CREATE INDEX play_events_track_started ON play_events(track_id, started_at_utc);
CREATE INDEX play_events_album_started ON play_events(album, started_at_utc);

CREATE TRIGGER play_events_append_only BEFORE UPDATE ON play_events
BEGIN
    SELECT RAISE(ABORT, 'play events are append-only');
END;
