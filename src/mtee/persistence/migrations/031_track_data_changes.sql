-- Change log of the track data (plan 127): the tempo, key and loudness of a track (track_analysis)
-- and the person's credit corrections (credit_overrides), for the plugins that keep devices in step.
-- Each write of those tables adds one row, from a trigger, in the same transaction, so no code path
-- can change them without the log. `seq` is AUTOINCREMENT: it rises for every row and is never
-- reused, which makes it a cursor that stays valid until the database is replaced (a restore).
-- A row names a track (`track_id`) or a credit (`credit_key`): a correction applies to every track
-- that holds the credit, and the core resolves that when it reads the log.
CREATE TABLE track_data_changes (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id   TEXT,
    credit_key TEXT,
    CHECK (track_id IS NOT NULL OR credit_key IS NOT NULL)
);

-- The data stored before this migration is in the log too, so a plugin that reads the log from its
-- start sends what the database already holds.
INSERT INTO track_data_changes (track_id) SELECT track_id FROM track_analysis ORDER BY track_id;
INSERT INTO track_data_changes (credit_key) SELECT credit_key FROM credit_overrides ORDER BY credit_key;

CREATE TRIGGER track_analysis_change_insert AFTER INSERT ON track_analysis
BEGIN
    INSERT INTO track_data_changes (track_id) VALUES (NEW.track_id);
END;

CREATE TRIGGER track_analysis_change_update AFTER UPDATE ON track_analysis
BEGIN
    INSERT INTO track_data_changes (track_id) VALUES (NEW.track_id);
END;

CREATE TRIGGER credit_override_change_insert AFTER INSERT ON credit_overrides
BEGIN
    INSERT INTO track_data_changes (credit_key) VALUES (NEW.credit_key);
END;

CREATE TRIGGER credit_override_change_update AFTER UPDATE ON credit_overrides
BEGIN
    INSERT INTO track_data_changes (credit_key) VALUES (NEW.credit_key);
END;

CREATE TRIGGER credit_override_change_delete AFTER DELETE ON credit_overrides
BEGIN
    INSERT INTO track_data_changes (credit_key) VALUES (OLD.credit_key);
END;
