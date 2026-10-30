ALTER TABLE trash_operations
    ADD COLUMN acknowledged_at_utc TEXT NOT NULL DEFAULT '';
