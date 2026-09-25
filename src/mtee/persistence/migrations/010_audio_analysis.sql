CREATE TABLE analysis_runs (
    run_id TEXT PRIMARY KEY,
    track_id TEXT NOT NULL,
    source_size_bytes INTEGER NOT NULL,
    source_mtime_ns INTEGER NOT NULL,
    source_file_id TEXT,
    source_generation INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running','succeeded','partial','failed','cancelled')),
    started_at_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    finished_at_utc TEXT NOT NULL DEFAULT ''
);

CREATE TABLE analysis_results (
    result_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    track_id TEXT NOT NULL,
    analyzer TEXT NOT NULL,
    analyzer_version TEXT NOT NULL,
    source_size_bytes INTEGER NOT NULL,
    source_mtime_ns INTEGER NOT NULL,
    source_file_id TEXT,
    source_generation INTEGER NOT NULL,
    config_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('available','uncertain','not_applicable','stale','failed')),
    metrics_json TEXT NOT NULL DEFAULT '[]',
    segments_json TEXT NOT NULL DEFAULT '[]',
    diagnostics TEXT NOT NULL DEFAULT '',
    coverage REAL,
    created_at_utc TEXT NOT NULL,
    UNIQUE(run_id, analyzer)
);

CREATE INDEX analysis_results_track_method_idx
    ON analysis_results(track_id, analyzer, created_at_utc DESC);
CREATE INDEX analysis_results_source_idx
    ON analysis_results(track_id, source_size_bytes, source_mtime_ns, source_generation);

CREATE TABLE analysis_overrides (
    override_id TEXT PRIMARY KEY,
    track_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    value_json TEXT NOT NULL,
    source_size_bytes INTEGER NOT NULL,
    source_mtime_ns INTEGER NOT NULL,
    source_file_id TEXT,
    source_generation INTEGER NOT NULL,
    active INTEGER NOT NULL CHECK (active IN (0,1)),
    created_at_utc TEXT NOT NULL
);

CREATE INDEX analysis_overrides_track_field_idx
    ON analysis_overrides(track_id, field_name, created_at_utc DESC);
