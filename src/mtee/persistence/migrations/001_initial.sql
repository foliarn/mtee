-- MTEE — initial schema.
-- Only the schema history and the application settings belong to this step.
-- The catalogue of tracks is added by the explorer step, and every later
-- feature brings its own migration.

CREATE TABLE schema_migrations (
    version       INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE settings (
    key            TEXT PRIMARY KEY,
    value          TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
