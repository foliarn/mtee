-- MTEE Remote, plan 126.4: the fetch (server to computer) and the follow-up of the first match.

-- A local track that the first match left out as a second copy of a track already matched. The
-- push skips it, so the copy is never uploaded as a new server item.
CREATE TABLE remote_excluded (
    track_id TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    at_utc TEXT NOT NULL
);

-- A file that the fetch downloaded for a new server item and put in a mapped folder. It is linked
-- to the item once the library scan has picked it up (the path and the SHA-256 must match).
CREATE TABLE remote_imports (
    item_id TEXT PRIMARY KEY,
    local_path TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0,
    audio_hash TEXT,
    created_at_utc TEXT NOT NULL
);
