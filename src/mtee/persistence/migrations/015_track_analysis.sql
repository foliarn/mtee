CREATE TABLE track_analysis (
    track_id TEXT PRIMARY KEY REFERENCES tracks(track_id) ON DELETE CASCADE,
    bpm REAL,
    key_tonic INTEGER CHECK (key_tonic IS NULL OR key_tonic BETWEEN 0 AND 11),
    key_minor INTEGER CHECK (key_minor IS NULL OR key_minor IN (0, 1)),
    bpm_user_edited INTEGER NOT NULL DEFAULT 0 CHECK (bpm_user_edited IN (0, 1)),
    key_user_edited INTEGER NOT NULL DEFAULT 0 CHECK (key_user_edited IN (0, 1)),
    source_duration_us INTEGER,
    algorithm_version INTEGER,
    analyzed_at_utc TEXT
);

CREATE TABLE track_waveforms (
    track_id TEXT PRIMARY KEY REFERENCES tracks(track_id) ON DELETE CASCADE,
    duration_us INTEGER NOT NULL,
    source_duration_us INTEGER,
    points BLOB NOT NULL,
    algorithm_version INTEGER NOT NULL,
    computed_at_utc TEXT NOT NULL
);
