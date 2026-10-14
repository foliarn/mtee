CREATE TABLE artist_enrichment_schema (
    version INTEGER PRIMARY KEY,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE artist_enrichment_reviews (
    artist_id TEXT PRIMARY KEY REFERENCES artists(artist_id),
    decision TEXT NOT NULL CHECK (decision IN ('keep', 'exclude', 'uncertain', 'pending')),
    roles_json TEXT NOT NULL,
    bass_related INTEGER CHECK (bass_related IN (0, 1)),
    spotify_url TEXT NOT NULL,
    soundcloud_url TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    notes TEXT NOT NULL,
    identity_decision TEXT NOT NULL,
    validated_at_utc TEXT NOT NULL,
    record_json TEXT NOT NULL,
    observation_json TEXT NOT NULL
);
