CREATE TABLE playback_session (
    session_id TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
