ALTER TABLE root_tracks ADD COLUMN parent_relative_path TEXT NOT NULL DEFAULT '';
ALTER TABLE library_folders ADD COLUMN parent_relative_path TEXT NOT NULL DEFAULT '';

WITH RECURSIVE folder_parts(root_id, track_id, remaining, parent) AS (
    SELECT root_id, track_id, relative_path, '' FROM root_tracks
    UNION ALL
    SELECT root_id, track_id,
           substr(remaining, instr(remaining, '/') + 1),
           CASE WHEN parent = ''
                THEN substr(remaining, 1, instr(remaining, '/') - 1)
                ELSE parent || '/' || substr(remaining, 1, instr(remaining, '/') - 1)
           END
    FROM folder_parts
    WHERE instr(remaining, '/') > 0
)
UPDATE root_tracks
SET parent_relative_path = COALESCE(
    (SELECT parent FROM folder_parts
     WHERE folder_parts.root_id = root_tracks.root_id
       AND folder_parts.track_id = root_tracks.track_id
       AND instr(folder_parts.remaining, '/') = 0),
    ''
);

WITH RECURSIVE folder_parts(root_id, relative_path, remaining, parent) AS (
    SELECT root_id, relative_path, relative_path, '' FROM library_folders
    UNION ALL
    SELECT root_id, relative_path,
           substr(remaining, instr(remaining, '/') + 1),
           CASE WHEN parent = ''
                THEN substr(remaining, 1, instr(remaining, '/') - 1)
                ELSE parent || '/' || substr(remaining, 1, instr(remaining, '/') - 1)
           END
    FROM folder_parts
    WHERE instr(remaining, '/') > 0
)
UPDATE library_folders
SET parent_relative_path = COALESCE(
    (SELECT parent FROM folder_parts
     WHERE folder_parts.root_id = library_folders.root_id
       AND folder_parts.relative_path = library_folders.relative_path
       AND instr(folder_parts.remaining, '/') = 0),
    ''
);

CREATE INDEX root_tracks_parent_present
    ON root_tracks(root_id, parent_relative_path, present, relative_path);
CREATE INDEX library_folders_parent_present
    ON library_folders(root_id, parent_relative_path, present, relative_path);
