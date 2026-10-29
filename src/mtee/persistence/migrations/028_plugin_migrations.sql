-- History of the migration scripts that plugins apply to their own tables (step 121).
-- Each plugin numbers its scripts from 001, so a number is only unique for one plugin_id.
-- The core never validates the rows of a plugin that is absent: removing a plugin leaves
-- its tables and its rows here in place.
CREATE TABLE plugin_migrations (
    plugin_id      TEXT NOT NULL,
    version        INTEGER NOT NULL CHECK (version > 0),
    name           TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL,
    PRIMARY KEY (plugin_id, version)
);
