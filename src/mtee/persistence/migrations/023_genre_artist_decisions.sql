-- Explicit artist attribution decisions remain separate from confirmed credits.
CREATE TABLE gm_artist_decisions (
    track_id TEXT PRIMARY KEY REFERENCES tracks(track_id) ON DELETE CASCADE,
    credit_signature TEXT NOT NULL,
    artist_ids_json TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
