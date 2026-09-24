ALTER TABLE file_operations
    ADD COLUMN phase TEXT NOT NULL DEFAULT 'prepared';

UPDATE file_operations
SET phase = CASE status
    WHEN 'completed' THEN 'completed'
    WHEN 'failed' THEN 'failed'
    WHEN 'needs_recovery' THEN 'needs_recovery'
    WHEN 'undone' THEN 'undone'
    ELSE 'prepared'
END;
