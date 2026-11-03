-- The time at which the hashes of a cached file were computed (plan 126.2, racy-git rule).
-- A cache entry is trusted only when its modification time is older than this time minus 2 s.
-- NULL for the entries stored before this migration: they are hashed again once.
ALTER TABLE remote_hash_cache ADD COLUMN hashed_at_ns INTEGER;
