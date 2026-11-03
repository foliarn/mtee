-- MTEE Remote, plan 129.1: a mapping can start at a subfolder of its watched folder, for a trial
-- on one small folder. The subpath is POSIX and relative to local_root_path; empty means the whole
-- watched folder, which is what every mapping made before this migration syncs.

ALTER TABLE remote_mappings ADD COLUMN local_subpath TEXT NOT NULL DEFAULT '';
