ALTER TABLE track_locations ADD COLUMN file_created_at_ns INTEGER;
ALTER TABLE track_locations ADD COLUMN file_modified_at_ns INTEGER;

UPDATE track_locations
SET file_modified_at_ns = mtime_ns;
