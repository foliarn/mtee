-- User choices on how a credit of the Artist tag is cut in the core Artists view (step 112).
-- credit_key is the normalized credit text (case and spacing are not significant); mode is
-- 'one_artist' (keep the credit whole) or 'split' (cut every & / x junction of it).
-- The table is read when the artist index is built; no tag is ever written from it.
-- The name avoids the "artist" prefix, which the plugin schema test reserves for the Artist
-- manager plugin: a new database must hold no artist table in the core.
CREATE TABLE credit_overrides (
    credit_key TEXT PRIMARY KEY,
    credit_text TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('one_artist', 'split')),
    updated_at_utc TEXT NOT NULL
);
