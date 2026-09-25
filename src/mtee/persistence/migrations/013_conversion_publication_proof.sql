ALTER TABLE conversion_attempts ADD COLUMN temporary_path TEXT NOT NULL DEFAULT '';
ALTER TABLE conversion_attempts ADD COLUMN derived_track_id TEXT NOT NULL DEFAULT '';
ALTER TABLE conversion_attempts ADD COLUMN destination_path_key TEXT NOT NULL DEFAULT '';

CREATE INDEX conversion_attempts_destination_idx
    ON conversion_attempts(destination_path_key, status);
