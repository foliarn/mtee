-- The plugin numbers its own scripts from 001 and prefixes its tables with its id.
CREATE TABLE sample_items (
    item_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('local', 'missing'))
);

INSERT INTO sample_items (item_id, title, artist, state) VALUES
    ('one', 'Sample one', 'Sample artist', 'local'),
    ('two', 'Sample two', 'Sample artist', 'missing'),
    ('three', 'Sample three', 'Another artist', 'missing');
