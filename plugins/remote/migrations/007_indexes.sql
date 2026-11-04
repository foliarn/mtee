-- MTEE Remote, review of 0.3.0: the lookups that ran on every pass, or on the graphical thread,
-- read whole tables. Indexes only: no row and no column changes.

-- The open operations of one track, read once per track on every pass (push._open_rows).
CREATE INDEX remote_queue_track ON remote_queue (track_id);

-- The server-only track of a server item: the availability filter and the badge column.
CREATE INDEX remote_server_items_source_track ON remote_server_items (source_track_id);

-- The conflicts that wait: the count of the header, the bell and the Remote window.
CREATE INDEX remote_conflicts_state ON remote_conflicts (state);
