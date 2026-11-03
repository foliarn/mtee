# Plugin contract

A plugin adds one optional feature to MTEE. The core works without any plugin. This document is
the single contract every plugin follows. Everything described here as the rule of the plugin
platform is **current**: it exists in the code (plan 121). The old plugins (Convert, Artist
manager, Genre Manager) are not ported yet and still use the legacy switch, see section 3.

## 1. Terms

- **Core**: everything under `src/mtee/` except the plugin packages.
- **Plugin**: a package `mtee.plugins.<id>` that follows this contract.
- **Plugin folder**: a folder the user gave to MTEE. Its children are plugin packages.
- **Plugin interface**: `mtee.plugins.api`, the only core module a plugin imports (plus the
  `Mtee` QML module for its QML files).
- **Manifest**: `manifest.py` of a plugin. It declares the plugin and is read before the plugin
  is enabled.

## 2. Layout of a plugin

    <plugin folder>/<id>/
        manifest.py       # MANIFEST = PluginManifest(...)
        __init__.py       # the module named by the manifest factory, or its package
        migrations/       # the plugin's SQL migrations, if it has tables
        *.qml             # the plugin's QML files, if it has any
        README.md         # the plugin's own description, see section 8

    tests/plugins/<id>/   # the plugin's tests

An `<id>` is lowercase snake_case, equals the name of its folder, and never changes after
release. It is the stable key in the settings, in the database and in the QML identities. An id
that MTEE itself uses (a module of `mtee.plugins` or an old plugin id) is refused.

The sample plugin `tests/plugins/sample/` is a complete example with one of each contribution,
and it uses the optional capabilities of the context.
`tests/plugins/sample_failing/` is a plugin whose factory raises, for the tests.

## 3. Discovery and registration

MTEE loads plugins from two places, and from nowhere else:

- The plugins folder `<data-dir>/plugins/`. Each installed plugin lives in
  `<data-dir>/plugins/<id>/`, laid out as its package (section 11). It is loaded at every start.
  A folder unpacked there by hand is loaded the same way.
- `--plugin-dir PATH` on the command line, repeatable. These folders are used for that run only
  and are not saved. It is a development flag.

The user manages plugins in the **Plugins** view, the activity of the left bar (see section 13).
Its switches are saved as `plugins.enabled`, a list of ids. Plugins are installed from a package
file (section 11.1) or from the Marketplace (section 12); the installer reads package files
only, and nothing is fetched from PyPI. The folder list of earlier versions (`plugins.folders`)
is no longer read.

Discovery lists the direct children of each folder that hold a `manifest.py`. It executes the
manifest file alone, never `__init__.py` or the factory module. The code of a plugin is imported
only once the plugin is enabled. A manifest is refused, with a readable reason, when:

- its `plugin_id` differs from the folder name, or is not lowercase snake_case;
- the folder has no `__init__.py`;
- its `api_version` is not one this MTEE supports (the factory module is not imported);
- its `factory` is not written `module:function` or is outside `mtee.plugins.<id>`;
- another plugin folder already provides the same id (the first one found is kept).

A refused plugin is shown `Failed` in the Plugins view with the reason. A shared library that
two loaded plugins cannot share is handled as section 11.2 describes; the plugin that cannot share
it is shown `Failed` with that sentence.

`manifest.py` defines `MANIFEST`:

    from mtee.plugins.api import PluginManifest

    MANIFEST = PluginManifest(
        plugin_id="sample",
        title="Sample plugin",
        description="One sentence for the user.",
        version="0.1.0",
        api_version=1,
        factory="mtee.plugins.sample:create",
        uses_network=False,   # shown to the user before the plugin is switched on
    )

**Legacy.** `src/mtee/plugins/registry.py` still lists the old plugins as `PluginDefinition`
(`plugin_id`, `title`, `description`, `factory_module`, `factory_name`). `load_plugin` refuses to
load while `PLUGIN_UI_ENABLED` is `False`, which it is in every release, and the hard-coded
hooks of `app.py` and the workspace serve those plugins. Each old plugin is
ported to the platform in its own plan; until then the legacy switch stays.

## 4. Lifecycle

1. **Declared**: the plugin is found in a plugin folder and its manifest is accepted.
2. **Enabled**: the user switched it on. A change applies at the next start; a plugin switched
   off stays running until then, and the Plugins view says `Restart needed`.
3. **Loaded**: after the core services exist, the core applies the plugin's migrations, imports
   the factory module and calls the factory with a `PluginContext`.
4. **Registered**: the core calls `contributions()` once and checks every contribution
   (identifiers, names, QML files). The plugin shows `Running`.
5. **Running**: the plugin works through the core's services. Startup tasks are submitted as
   jobs.
6. **Unloaded**: on exit. The core calls `unload()` (newest plugin first), forgets the plugin's
   modules and leaves its data in place.

A failure in step 3 or 4 (a migration, the factory, a broken contribution) disables that plugin
only. The core stores the message, logs it, shows one notice that names the plugin, and keeps
running. The Plugins view shows `Failed` with the message; the switch stays on, since it is
the user's choice. A plugin never stops the application from starting. A function of a
contribution that raises later is caught at the call, logged, and announced once.

## 5. Data and migrations

- A plugin stores its data in its own tables. Table names start with the plugin id followed by
  `_`, for example `sample_items`.
- A plugin numbers its own scripts from `001`, as `migrations/NNN_name.sql`. Numbers are per
  plugin and never collide with the core or another plugin, so nothing is reserved in the core.
- The core applies them with `Database.migrate_plugin(plugin_id, migrations)` before the
  factory runs, and records each in `plugin_migrations (plugin_id, version, name,
  applied_at_utc)`, apart from the core history in `schema_migrations`. Before the first
  pending script it writes the usual safety copy of the database. Each script runs in its own
  transaction. A recorded history that does not match the scripts, or a failing script, fails
  that plugin and leaves the database unchanged.
- The core never validates the rows of a plugin that is absent. Removing a plugin leaves its
  tables and rows in place and does not touch the core's data.
- A plugin never reads or writes another plugin's tables.
- A plugin's own files (`PluginContext.base_dir` and `data_dir`) are in
  `<data-dir>/plugin-data/<id>/`, outside the plugins folder. An update or an uninstall never
  removes them.
- The migrations 019 to 023 of the old plugins stay in `PLUGIN_OWNED_MIGRATIONS` of
  `src/mtee/persistence/database.py` for the legacy plugins.
- The plugin keeps the layers separate, as the core does: a plugin's analysis is stored apart
  from the tags written to the file.

## 6. PluginContext

The factory receives one `PluginContext`. It exposes only the following; nothing else of the
core is reachable from it.

| Field | What it gives |
| --- | --- |
| `plugin_id` | The plugin's id. |
| `database` | The shared `Database`. Use only your own tables. Each thread has its own connection. |
| `library` | `track_ids()`, `tracks(ids)` (`LibraryTrack`: id, path, title, artists, album, `duration_us`, `readable`, `isrc`), `roots()` (`LibraryRoot`: `root_id`, `path`), `add_watched_folder(path)` and `rescan(path)`. The last two on the graphical thread only. See "Library roots, read leases and ffmpeg". |
| `playlists` | `create(name, track_ids)`, `replace_entries(playlist_id, track_ids, expected_revision=None)` (returns the new revision), `rename(playlist_id, name, expected_revision=None)` (returns the new revision), `entries(playlist_id)`, `read(playlist_id)`, `revision(playlist_id)`, `name(playlist_id)` (`None` when it is gone), `exists(playlist_id)` and `list()` (`PlaylistInfo` of every local playlist), through the core playlist service. See "Store access for sync". |
| `jobs` | `submit(task, label=..., visible=...)` and `cancel(job_id)` on the core job service. |
| `files` | The core write services: `move_track(track_id, root_id, relative_folder)`, `import_file(source, folder)`, `replace_content(track_id, source)` and `attach_file(track_id, source, folder)` (optional capabilities, see below) and `recycle(track_ids)` (the user confirms in the usual dialog). Never a file API on a music file. `read_lease(track_id)` is the one read access: a context manager that yields the path under a read lease. See "Library roots, read leases and ffmpeg" and below. |
| `ffmpeg_path()` | The core's pinned `ffmpeg` executable, never one found on `PATH`. See "Library roots, read leases and ffmpeg". |
| `settings` | A key-value store scoped to the plugin: `get`, `set`, `get_json`, `set_json`, `delete`. Keys live under `plugins.<id>.` in the settings. |
| `base_dir`, `data_dir` | `<data-dir>/plugin-data/<id>/`. `data_dir` creates the folder when first read; use it for tokens and caches. It is outside the plugins folder, so an update or an uninstall keeps it. |
| `notify(text)` | Shows a message on the workspace message line. Any thread. |
| `log` | A logger named `mtee.plugins.<id>`. |
| `refresh_ui()` | Asks the core to read the rows, header buttons and cells of the plugin again after its data changed. Any thread. |
| `run_on_gui(fn)` | Runs `fn()` on the graphical thread, after the current event: a queued call, also when called from the graphical thread. Any thread. A `fn` that raises is logged under the plugin's logger. |
| `open_dialog(dialog_id, ref)` | Opens one of the plugin's `PluginDialog` as a modal popup over the window. Any thread. `ref` is handed to the dialog's QML. |
| `open_tab(kind, ref)` | Opens, or focuses when it is already open, a tab of one of the plugin's own `TabKind` (`kind` starts with `<plugin_id>.`, another is refused and logged). Any thread; the tab opens on the graphical thread. |
| `play_log`, `track_data`, `synced_settings`, `database_snapshot` | The optional store capabilities for sync, see "Store access for sync". A context built without them raises `CapabilityUnavailableError` at the first call. |
| `track_sources` | Stores the tracks the plugin provides without a file (`upsert`, `remove`, `list`, and the optional `adopt`), see "Track sources". Same error when absent. |
| `availability_changed` | `availability_changed(track_ids)`: asks the core to read `TrackAvailability` again for those tracks, or for every track with `None`, see "Track availability". Any thread. |
| `status_item` | `update(text, tone, progress, tooltip, icon)` and `clear()`: the plugin's item of the status bar, see "Status item". Any thread. Without a `StatusItem` declaration the calls change nothing visible. |

`files.import_file(source, folder) -> Path` moves a file that is **not in the library yet**
(for example a download) into a folder of the library and returns its final path. It never
replaces a file: a taken name gets the next free `name (2).ext`, `name (3).ext`..., also when
the name is taken while the file is being moved, and a path the library still owns counts as
taken. On another volume the file is copied to a hidden `.<name>.part` file of the folder and
put in place at the end, so the scanner never reads a half-written file under its final name.
`folder` is created when missing. The import does not touch the library: the scanner records
the file at the next scan, which the plugin may ask for with `library.rescan(folder)`. It may
be called from any thread. It raises `FileMoveError` when `folder` is outside the library or
`source` already belongs to it (use `move_track`), and `OSError` when the move fails, with
`source` untouched. A `source` already in `folder` is returned as it is.

`files.replace_content(track_id, source) -> Path` (an optional capability, `API_VERSION` stays 1)
puts `source` in place of the file of a track and returns the track's path. The track keeps its
path and its identifier. The current file goes to the Windows Recycle Bin through the core's trash
path, so the trash history shows it as after a delete; `source` takes its exact path; then the
library is refreshed from the new file (tags, size, revision). `source` must be a regular file
outside every library folder, and it is removed only after the replacement succeeded. On another
volume the file is first copied to a hidden `.<name>.part` file of the track's folder, so a failed
copy changes nothing. A reader (the player, an analysis) or a tag write on the track waits for the
replacement, up to 10 seconds. The call raises `NonFileTrackError` for a track without a file,
`LookupError` for an unknown track, `FileNotFoundError` when the track's file or `source` is
missing, and `ValueError` when `source` is not a regular file or lies inside a library folder.
MTEE cannot take a file back out of the Recycle Bin: when the replacement fails after the old file
went there, the readable error says where the old file is and that `source` is untouched. Once the
file is in place the views read the track again, as after a scan. Job thread only (`RuntimeError`
on the graphical thread); `CapabilityUnavailableError` without the capability.

`files.attach_file(track_id, source, folder) -> Path` (an optional capability, `API_VERSION` stays 1)
gives a source track of the plugin (see "Track sources") its local file. `source` is moved into
`folder`, a folder of the library, under the same `track_id`: a taken name gets the next free
`name (2).ext`, a file on another volume goes through a hidden `.<name>.part` file, and `folder` is
created when missing. The file is read again for its tags and recorded as a new revision, and the
plugin's source row of the track is removed. On failure `source` is back where it was and the track
stays a source track. It holds the write lease of the track, is for the job thread only, and raises
`ValueError` when the track is not a source track of this plugin, when `source` lies in the library
or `folder` is outside it, and `FileNotFoundError` when `source` is missing.

The factory returns a `PluginService` with two methods: `contributions()`, returning a list of
contributions, and `unload()`, which releases threads and files and leaves the data.

### Library roots, read leases and ffmpeg

Three optional capabilities (`API_VERSION` stays 1). A plugin that does not use them is unchanged.

- `library.roots() -> list[LibraryRoot]` lists the watched folders (`root_id`, `path`). Any thread.
- `files.read_lease(track_id)` is a context manager that yields the track's `Path` under the
  file-access coordinator's shared read lease, the one the player and analysis hold; a tag write or
  move on the track waits for the block to end. Job thread only (`RuntimeError` on the graphical
  thread). It waits up to 10 seconds, then raises `TimeoutError`; `NonFileTrackError` for a track
  without a file, `FileNotFoundError` when the file is missing, `LookupError` for an unknown track.
  Keep nothing from the path after the block.
- `ffmpeg_path() -> Path` is the core's pinned ffmpeg (never `PATH`). Any thread.
  `FileNotFoundError` when the runtime is missing.

### Helper processes

A plugin that must run Python code apart from MTEE starts a helper process with
`context.python_command(module, *args)`, a list for `subprocess`. Merge
`context.python_environment()` into the environment of that process; the helper needs it to find
the plugin's package and the shared libraries of the running plugins.

- From the sources the command is `sys.executable -I -m mtee.plugin_helper <plugin_id> <module>
  ...`. In the packaged exe it is `MTEE.exe --plugin-helper <plugin_id> <module> ...`. There
  `sys.executable` is the exe, so a plugin never starts `sys.executable` with a script or `-m`.
- `<module>` is a module of the plugin (`mtee.plugins.<id>.<name>`) or a bundled library (its
  top-level name). The helper runs it as `__main__` with `sys.argv` set to `[module, *args]` and
  exits with the module's exit code. It never opens a window and imports no Qt module.
- Do not set `PYINSTALLER_RESET_ENVIRONMENT` for a helper: it may reuse the files that MTEE
  unpacked for the exe.

### Store access for sync

Optional capabilities (`API_VERSION` stays 1). They serve any plugin that keeps devices in step; none
of them names a server. Each goes through the repository or service of the core and never hands out
a SQL handle. The manifest has no permission list yet (only `uses_network`), so a running plugin
gets all of them; the Plugins view shows nothing more for them.

- **`play_log`** (`PlayLogAccess`). `device_id` is this installation. `events_since(cursor, limit)
  -> (events, next_cursor)` returns `PlayLogEvent` in insertion order (the SQLite `rowid` of
  `play_events`, which has no sequence column; a start time would miss events appended later). The
  cursor is text, `None` for the first call; `next_cursor` equals the cursor passed when nothing is
  newer. Events of every device come back, each with its `device_id`; a pusher filters on its own.
  A cursor is valid for one log: a reset of the statistics numbers the rows again. A `PlayLogEvent`
  has no file path. `append_remote(events) -> int` stores the events of other devices and returns
  how many were new: an `event_id` already stored is skipped, each event keeps its `device_id`, an
  invalid event refuses the whole batch with `ValueError`. The log stays append-only. Any thread.
- **`playlists` revisions.** A playlist has a `revision`: 1 for a new playlist and for the playlists
  that existed when migration 029 ran, and +1 on every change through any path (interface, plugin,
  or the library removing a track an entry pointed to). It is a different counter from the
  interface's own `version`. `read(id)` returns `PlaylistSnapshot(name, revision, entries)`;
  the revision is read first so a concurrent change makes a later write stale, not lost.
  `replace_entries(id, track_ids, expected_revision)` raises `StaleRevisionError` (`expected`,
  `actual`) when the playlist moved on, in the same transaction as the write; without
  `expected_revision` it replaces unconditionally. Any thread.
  `list()` returns `PlaylistInfo(playlist_id, name, revision, entry_count)` for every local
  playlist, folders excluded; it reads the stored playlists and changes nothing. `rename(id, name,
  expected_revision)` renames a playlist as the interface does (the name is stripped and must be 1
  to 240 characters, `ValueError` otherwise) and returns the new revision; with `expected_revision`
  it raises `StaleRevisionError` in the same transaction, without it the rename is unconditional.
  Both run on any thread.
- **`track_data`** (`TrackDataAccess`). `read(track_id)` returns `TrackData`: `analysis` (tempo,
  key, edit flags, algorithm version, date), `loudness` (LUFS, sample peak, version) and
  `corrections` (the choices on the artist credits of the track, `one_artist` or `split`). The
  `write_*` calls store each layer in its own store: analysis and loudness in `track_analysis`
  (each leaving the other's columns alone, and keeping the version and date they come with, so
  an older result still reads as outdated), corrections in `credit_overrides`. A tempo or key the
  person edited here keeps its value. A correction is accepted only for a credit the track holds;
  corrections are added or changed, never removed. Audio files and tags are never touched.
  `LookupError` for an unknown track, `ValueError` for an invalid value. Any thread.
  `changed_since(cursor, limit)` lists the tracks whose analysis, loudness or corrections changed
  after `cursor`, and the cursor to keep. The core logs each write of `track_analysis` and
  `credit_overrides` in a change log (`track_data_changes`, migration 031, written by triggers in
  the same transaction). `cursor` is text, `None` for the first call; `limit` bounds the log records
  read per call, and a correction names every track that holds its credit, so one call can return
  more tracks than `limit`. The batch lists each track once, in the order of its first change, and
  an unchanged track is never listed. A cursor the core did not give, such as one from before a
  restore of the database, raises `ValueError`: start again from `None`. Any thread.
- **`synced_settings`** (`SyncedSettings`). The core decides which settings may travel:
  `mtee.plugins.synced_settings.SYNCED_SETTINGS` (rule and exclusions are written there). Today:
  `playback/normalization`, `profile/display_name`, `playlists/columns`, `plugins.enabled`. `keys`
  lists them, `read()` returns the stored text of those that are set, `write(values)` checks every
  key and value first (`SettingNotSyncedError` for a key outside the list, `ValueError` for a value
  the setting cannot hold) and stores them together; the running application then reads them again
  on the graphical thread. `subscribe(callback)` calls `callback(keys)` on the graphical thread when
  another writer changes an allowed key; the plugin's own `write` is not announced. It returns the
  function to call in `unload()`. `write` and `read` run on any thread.
- **`database_snapshot`** (`DatabaseSnapshot`). `snapshot(target_path)` writes a consistent copy
  with the SQLite backup API, checks it, and returns its path. `target_path` must be inside
  `base_dir` and must not exist. `request_restore(path)` checks that the file is a usable backup
  and offers it to the restore of Settings > Data & privacy: Settings opens on that page with its
  "Schedule restore" confirmation, and nothing changes until the person confirms; the restore is
  applied at the next start after a safety copy, as for any backup. Keep the file until the person
  has answered. The plugin never replaces the database. Both calls refuse the graphical thread
  (`RuntimeError`): submit them with `context.jobs`. The copy holds the whole library data; treat it
  as private.

### Track sources

An optional capability (`API_VERSION` stays 1) for a plugin that provides tracks which have **no
file on this computer**, for example the tracks of a server. It has two halves: `context.track_sources`
stores the tracks, and the `TrackSource` contribution opens them when they are played. Both are
generic; neither names a server.

**Storing the tracks.** `context.track_sources` (`TrackSourceAccess`) works on the plugin's own keys
and on nothing else, from any thread:

- `upsert(tracks) -> {source_key: track_id}` stores `SourceTrack` values (`source_key`, `title`,
  `artists`, `album`, `album_artist`, `track_number`, `duration_us`, `genre`, `year`; `artists` and
  `genre` take one string or several). The first time a key is stored, the core gives it a normal
  `track_id`, a per-machine UUID like any other. The id never changes for that key, not after
  `remove`, not after a restart. Calling `upsert` again with the same values changes nothing (it is
  idempotent and announces nothing); with other values it replaces the metadata under the same id.
  The call is one transaction: all tracks or none. Metadata is checked: an empty key, a negative
  duration or an over-long text raises `ValueError`.
- `remove(source_keys) -> int` makes the tracks unavailable and returns how many were available. The
  row, the `track_id`, the playlist entries that point to it and the play log rows stay. An unknown
  key and a track already removed are ignored. `upsert` brings a removed track back under its id.
- `list(available_only=False) -> [SourceTrackEntry]` returns the plugin's tracks, removed ones
  included, with `track_id`, `track` and `available`.
- `adopt(track_id, entry) -> track_id` (optional capability, `API_VERSION` stays 1) makes an existing
  library track without a file a source track of the plugin, under its own `track_id`; see the next
  paragraph.

**Keeping a track's identity.** A plugin that frees the disk space of a track, or downloads it again,
keeps the same `track_id` on both sides, so the playlists, the play log and the analysis still refer
to it. After the file of a library track has left the library (it was sent to the Recycle Bin), the
plugin calls `adopt(track_id, entry)` with the key the track gets: the track's file locations are
forgotten, its `tracks` row, playlist entries, play log rows and analysis stay, and the track now
shows as a source track. It raises `ValueError` while the track still has a file or a library folder
still lists it, when it belongs to another plugin, or when the key is taken by another track. The
reverse is `files.attach_file` (see the `files` row of the table in section 6): a downloaded copy goes
into a library folder under the same `track_id` and the source row is removed. A key that was attached is no longer
a source key: a later `upsert` of that key gives a new `track_id`, so the plugin must not store it
again as a source track. Both calls refresh the views of the interface, as a scan does.

The key rule: a key is held by the source row of its track, whether the track is available or
removed. `attach` deletes that row, so the key of an attached track is free: when its file is
recycled again, `adopt(track_id, entry)` with the same key works and keeps the same `track_id`
(the rows of the track keep pointing to it). A removed track keeps its key on purpose, because
`upsert` gives the key back to that track; `adopt` refuses another track under it.

**What the core does with them.** The tracks are stored in the core table `plugin_source_tracks`
(migration 030), keyed by `(plugin_id, source_key)`. They are not in `track_locations` or
`root_tracks`: the scanner never sees them and they are in no library folder, so they are not in the
Explorer. Everything that works on a `track_id` treats them as tracks: the Artists view, local
playlists, the queue, the history, the play log and the tracks of a plugin tab (`TrackListRow.track_id`).
The row the interface reads has `sourcePluginId` and `sourceKey` and an empty `path`. A track is
**unavailable** (greyed out, never played, skipped by Play, Shuffle and the queue, no "Add to
playlist") when the plugin removed it, or when the plugin that provides it is not running; the
playlist entry stays and returns to normal when the track is available again. The analysis of a
track (`track_data`) and its normalization loudness are stored by `track_id` like those of a file, so
loudness normalization applies. `context.library.tracks()` lists files only: use `track_sources.list()`.

**Never a file.** A track without a file is refused, with a sentence that names the plugin ("This
track is provided by X and has no file on this computer, so it cannot be moved"), by every file
operation: tag edit and undo, move, Recycle Bin, analysis, "Show in Explorer", playlist export (it
exports the entry as a name only), `files.move_track` and `files.recycle`. A plugin that wants the
audio on disk downloads it itself and imports it with `files.import_file`; the new file is then a
normal library track with another `track_id`. To keep the same `track_id`, it attaches the copy with
`files.attach_file` instead (see "Keeping a track's identity").

**Playing them.** The `TrackSource` contribution has two functions:

- `open(source_key) -> PlayableSource`. `PlayableSource` is either `path` (a local file the plugin
  made, for example a download; the player holds a read lease on it like on a library file) or `url`
  (`http` or `https`) with `headers`, a mapping sent with the requests for that track only (for
  example `Authorization`). A URL source is never locked by the file access coordinator. Header names
  must be HTTP tokens, values must have no control character and no trailing backslash;
  `PlayableSource` refuses anything else, and its `repr` never shows a header value or the query of the
  URL. **`open` runs on a job thread, never on the graphical thread.** It may take a network round
  trip, but it must return or raise in a reasonable time: the player waits for it while the track is
  `Loading`, and the user can choose another track meanwhile (the answer is then dropped). Do not
  call Qt widgets or models from it, and keep nothing it returns: the core calls it again for every
  play, and 15 seconds before the end of the current track for the gapless preparation of the next.
- `cover(source_key) -> bytes | None` (optional) returns the bytes of a PNG or JPEG cover, or
  `None`. It runs on an image worker thread when the interface asks for the picture and may be slow;
  the core caches a cover it got. A function that raises gives the usual placeholder.

**Errors.** When `open` raises, returns something else than a `PlayableSource`, or the player cannot
open what it returned (for example the server answers 401), the player shows an error that names the
plugin ("Remote could not open this track: ...") on the message line and goes on with the next track
of the queue; with no next track it stays in the error state with the same sentence. The failure is
logged; nothing is added to the play log for a track that could not be opened. A plugin that is not
running gives "X is not running, so its tracks cannot be played."

**Gapless.** A URL track is played gapless like a file. See "Gapless playback" below.

**What a plugin must not do.** Return a URL that redirects to another host unless that host may see
the headers (libmpv/FFmpeg send them to the redirect target too; not verified). Put a secret in
the URL when a header can carry it. Block the graphical thread. Keep a stale `PlayableSource`.
Assume that `open` is called once per track, or that two calls give the same URL. Write to a
`plugin_source_tracks` row directly: use `track_sources`. Use `source_key` values that contain
personal paths. Store a secret in `SourceTrack` (the metadata is stored, shown and copied to
playlist snapshots).

### Gapless playback

Nothing to do for a plugin. The player plays consecutive tracks with no gap, from files and from
`TrackSource` URLs, and applies the loudness gain of each track from its first sample. It is the
behaviour of the player: there is no setting. Measured on the pinned libmpv, a local file followed by
a URL track gives the same samples as the two decodes, with no run of zeros longer than one sample.

- The next track is prepared 15 seconds before the end of the playing one. For a `TrackSource`
  that means `open` runs once more for that track, on a job thread, as in "Track sources".
- A queue change, shuffle, repeat, a manual next or previous, and a change of normalization
  cancel the prepared track. The core does not keep it.
- A track at another sample rate is resampled to the rate of the first track, so its start is
  gapless within the device buffer.
- The core sets the request headers of a prepared URL track itself, so the headers of one track
  do not reach the next one.

## 7. Contributions

A contribution is data. The core draws it with its own components and colours; a plugin never
names a core QML type in it. Icons are icon names of the core (`music`, `repeat`,
`arrow-down`...). Every identifier is lowercase snake_case and unique within its kind.

- `PluginActivity(activity_id, title, icon, actions=(), foot=None, badge=None)`: a button in the
  activity bar and a sidebar pane. `actions` are `PaneAction(action_id, tip, icon, run, label="",
  visible=None)` buttons in the pane header: with a `label` they are small ghost text buttons
  instead of icon buttons, and `visible()` decides whether a button is drawn. `foot` is a
  `PluginRowsModel` of `{"text", "tone"}` rows (`tone`: `secondary`, `muted` or `warning`) drawn at
  the bottom. `badge()` returns the number drawn on the activity bar button like the badge of
  Tasks (hidden at 0). `badge`, `visible` are read when the plugin calls `refresh_ui()` and at
  registration; a function that raises counts as 0, or as hidden. The id may not be a core
  activity name.
- `SidebarSection(section_id, title, activity, model, actions=(), activate=None, on_fold=None,
  count=None, expanded=True)`: a collapsible section. `activity` is `"playlists"` (below the local
  playlists), `"explorer"` or the `activity_id` of a `PluginActivity` of the same plugin. `model` is
  a `PluginRowsModel` the plugin keeps up to date; a row has `id` and `name`, and optionally
  `depth`, `kind` (`item` or `group`), `expanded`, `icon`, `tone`, `badge` and `count`.
  `activate(row_id)` runs when the user clicks an item, or the name of a group row, and returns a
  `TabRequest(kind, ref)` or `None`. The chevron of a group row only folds it: `on_fold(row_id,
  expanded)` is then called on the graphical thread, so that the plugin can remember the state.
  `count()` gives a badge drawn next to the section title (hidden at 0), read with `refresh_ui()`.
  `expanded` is the state of the section the first time it is shown: `True`, `False`, or a function
  read at that moment; after that the user's choice is kept.
- A row with `tone="warning"` is drawn in the warning colour, its icon and its text and count
  included; `secondary` colours only the icon.
- `TabKind(kind, title_fn, content, header=None, backend=None, icon="playlists")`: an editor tab
  kind named `<plugin_id>.<name>`. `title_fn(ref)` gives the tab title. `content` is either a
  function `ref -> [TrackListRow]`, which the core shows with its own track list (search, sort,
  selection, queue, context menu), or the `Path` of a QML file (see below). `header(ref)`
  returns a `TabHeader(title, kind_label, description, creator, meta)` for a track list tab.
  Tabs of a plugin that is absent are not restored.
- `TrackListRow(row_id, title, artist="", album="", duration_seconds=0.0, track_id="", data={})`:
  a row of a plugin track list. An empty `track_id`, or a track whose file is not readable,
  makes an **unavailable row**: greyed out cell by cell, never played, skipped by Play,
  Shuffle and the queue, without "Add to playlist". `data` comes back to the plugin's
  functions with the row.
- `TabAction(action_id, tab_kind, label, run, icon="", kind="neutral", checked=None,
  enabled=None, disabled_reason=None)`: a button beside Play and Shuffle. `tab_kind` is a
  `TabKind.kind` of the plugin or `"playlist"` for local playlists. `label` is a string or a
  function of the ref; `kind` is `primary`, `neutral`, `ghost` or `toggle` (a chip showing
  `checked(ref)`); `run`, `checked`, `enabled` and `disabled_reason` receive the ref.
  `enabled` returning `False` greys the button out. `disabled_reason` returns a sentence while
  the button cannot be used and `""` otherwise: the button is then greyed out and shows the
  sentence as its tooltip, so the user learns why (a missing dependency, a missing login).
- `TrackColumn(column_id, title, value_fn, default_visible_for=(), width=112, run_action=None)`:
  a column of the track lists, listed in the column picker with the plugin name and saved like
  the others (key `<plugin_id>.<column_id>`). `value_fn(row)` returns `None` for an empty cell
  or `CellValue(text, tone="neutral", action="")`: a badge (`tone`: `neutral`, `secondary`,
  `warning`) and optionally the label of one inline row button, which calls
  `run_action(row)`. `default_visible_for` lists the tab kinds (`"playlist"` or a
  `TabKind.kind`) where the column is shown until the user hides it. Plugin columns are not
  offered in Explorer folder lists.
- `TrackAction(action_id, label, group, run, enabled_fn=None)`: an entry of the track context
  menu, in a captioned group named `group`. The groups of plugins sit after the edit group
  (Analyze, Edit info, Convert) and before the file group (Open in Windows Explorer, Rename file,
  Delete file), so a plugin never adds to the file group. `enabled_fn(rows)` decides
  whether it shows for the selected rows; `run(rows)` usually submits a job. A row is a
  dictionary with `id`, `trackId`, `title`, `artist`, `album`, `available`, `data` (a plugin row
  only), `tabKind` and `tabRef` (the list the row is shown in: `"playlist"` and the playlist
  identifier, or the plugin's tab kind and its ref). Columns receive the same row.
- `SettingsPage(page_id, label, content, backend=None)`: an extra in-page tab of Settings,
  after Plugins and before About. `content` is a QML file.
- `StartupTask(task_id, run)`: submitted as a hidden job once the plugin is registered. `run`
  is a job task.
- `WaitingItems(section_id, title, model, run, dismiss)`: a group of the Tasks pane and page for
  work that waits for the user, for example a track to choose a match for. It is drawn like the
  tag conflicts: a heading `title (count)`, then one entry per row of `model`: the item, what is
  needed, a small ghost button with the label of the row and a dismiss cross. The page shows
  each entry on a card, as it does for jobs. `model` is a `PluginRowsModel` the plugin keeps up
  to date; a row has `id`, `title`, `subtitle` and `action` (the button label, `Open` when
  missing). `run(row_id)` answers the button and returns a `TabRequest` or `None`;
  `dismiss(row_id)` answers the cross, and the plugin removes the row. Both run on the graphical
  thread. A group with no row is not drawn, nothing is drawn for a plugin that is off, and the
  rows of all groups count in the badge of the Tasks activity, with the running jobs and the
  tag conflicts.
- `PluginDialog(dialog_id, content, backend=None, width=480)`: a modal dialog, opened with
  `context.open_dialog(dialog_id, ref)`. `content` is a QML file. The core draws the popup
  (surface, border, radius 8, 20 px padding, centred, closed by Escape or a click outside) at
  `width` pixels, from 320 to 640 (480 by default); a width outside that range, or not a whole
  number, refuses the plugin with the reason. The popup is never wider than the window less 16 px
  on each side. The file draws the title, fields and buttons with the components of `Mtee` and
  gives its `implicitHeight`. It receives `workspace`, `backend`, `ref` and `dialog`, whose
  `close()` closes the popup. The sample plugin's `dialog.qml` shows it.
- `PlaylistMeta(text)`: `text(playlist_id)` returns a phrase (for example `linked to Spotify`)
  or `""`. The core joins the phrases of all plugins to the meta line of the header of every
  local playlist with ` · `, and reads them again after `refresh_ui()`. `text` runs on the
  graphical thread while the header is drawn: keep it cheap.
- `LibraryScanned(callback)`: `callback(root)` is called on the graphical thread after the scan
  of a library folder completed (a folder added, a rescan, or the scan at start). `root` is the
  `Path` of that library folder; the scanned tracks are already in the library. A scan that was
  cancelled, replaced by a newer one or interrupted is not announced. Nothing is called for a
  plugin that is off or unloaded. A `callback` that raises is caught, logged and announced once.
- `DeleteChoices(offer, run)`: extra choices in the Recycle Bin confirmation, see "Delete choices".
- `TrackSource(open, cover=None)`: how the player opens, and the interface draws the cover of, the
  tracks stored with `context.track_sources`; at most one per plugin, see "Track sources". `open`
  runs on a job thread and `cover` on an image thread.
- `TrackAvailability(status)`: which tracks are not on this device, for the filter "Hide tracks not
  on this device"; see "Track availability". At most one per plugin.
- `StatusItem(item_id, icon, on_click=None)`: the plugin's item in the status bar, filled with
  `context.status_item`; see "Status item". At most one per plugin.

`TrackListRow` rows, `TabKind` track list functions and `TrackColumn.value_fn` run on a **job
thread** while a list loads. Keep them cheap, read only the plugin's own data (the database
gives each thread its own connection) and call no Qt widget or model. The other functions
(`activate`, `run`, `checked`, `enabled`, `enabled_fn`, `title_fn`, `header`, `run_action`)
run on the graphical thread, so they must return quickly and hand slow work to `jobs`.

### Delete choices

An optional capability (`API_VERSION` stays 1) for a plugin that keeps tracks somewhere else and
must say what a delete means for them. When the user deletes tracks (the track menu, or the
Delete key), the core shows its usual confirmation, "Move to Recycle Bin". A plugin adds choices
to it with `DeleteChoices(offer, run)`:

- `offer(track_ids) -> [DeleteChoice]` receives the identifiers of the selected tracks, on the
  graphical thread, each time the confirmation opens. It returns the choices that apply to that
  selection, or an empty sequence. Keep it cheap and read only the plugin's own data.
- `DeleteChoice(choice_id, label, description="", tone="normal", replaces_recycle=False)`.
  `label` is the button text; `description` is a sentence or two on a card above the buttons, and
  should say what the choice does and what it leaves alone. `tone` is `normal` or `danger`;
  `danger` draws the button with the core's red style, for a choice MTEE cannot undo. A choice
  with an empty id or label, or a second one with the same id, is ignored.
- `run(request) -> str | None` runs when the user presses a choice, on a job thread submitted with
  the job service: it shows in Tasks, and `request.job` can be checked for cancellation (the
  dialog shows the Cancel button while it runs). It returns a short sentence that tells what was
  done (`None` shows "Done."), or raises: an exception with `readable = True` is shown as its
  message alone, any other as `ClassName: message`, and the job ends Failed. The dialog then shows
  the result and a Close button; nothing is retried.
- `DeleteRequest` (frozen, from `mtee.plugins.api`) has `choice_id` (the id the plugin gave),
  `track_ids` (the identifiers that `offer` received), `job`, and
  `recycle(track_ids) -> RecycleOutcome`. `recycle` sends the files of the given tracks to the
  Windows Recycle Bin through the core's own recycle path, with no second dialog: the user has just
  confirmed them. Only identifiers of `track_ids` are accepted, any other raises `ValueError`. It
  runs on the job thread and follows the rules of the core action: only the files the
  confirmation showed, a journal entry per file, never a permanent delete, a file in use is
  reported, and when the Recycle Bin does not confirm a file the rest are not attempted and
  reported as failed. `RecycleOutcome` has `recycled` (identifiers) and `failed`
  (`RecycleFailure(track_id, reason)`, the reason in words the user can read). A cancelled job
  keeps the files it already recycled and raises the cancellation.

What the dialog does:

- Without a plugin choice for the selection, the dialog is exactly the one of the core.
- Each plugin that offers choices has a group: its name as a small heading, then one card per
  choice, and one button per choice next to the core's. Two plugins give two groups, in the order
  the plugins loaded.
- If no choice has `replaces_recycle`, "Move to Recycle Bin" stays and is the default button; the
  plugin buttons are added next to it. If any choice has `replaces_recycle=True`, the core button
  is not drawn for that selection: the first `normal` choice is the default (primary) button, and
  a `danger` choice is drawn red, after the others (farthest from the default). A `danger` choice
  is never the default.
- The core's own action does not change: it moves files to the Windows Recycle Bin only, and never
  deletes permanently. A plugin choice is only what its `run` does: pressing it moves no file to
  the Recycle Bin by itself, unless the choice calls `request.recycle`.
- A plugin whose `offer` raises is logged, announced once, and left out: the confirmation and the
  core action work as without it. A plugin has at most one `DeleteChoices`; declaring two makes
  the plugin Failed.
- The confirmation opens when at least one selected track has a readable file, as before, or when
  a plugin offers a choice for the selection, even if no selected track has a file on this
  computer (for example tracks that a plugin's `TrackSource` provides). In that case the core
  button is not drawn and only the plugin's choices are offered. The plugin receives all the
  selected identifiers.
- Every confirmation has a Cancel button, placed left of the action buttons: it closes the dialog
  and runs nothing, as Escape does.

The sample plugin offers one non-replacing choice, "Sample: log only", whose `run` records the
identifiers (`tests/plugins/sample/__init__.py`, tests in `tests/plugins/test_delete_choices.py`
and `tests/ui/test_trash_dialog_choices_ui.py`).

### Track availability

An optional capability (`API_VERSION` stays 1) for a plugin that knows which tracks are not on this
device, for example the tracks of a server. The core draws nothing of its own for it: the plugin
says where each track is, and draws its badge.

- `TrackAvailability(status)`: `status(track_ids)` receives track identifiers and returns
  `{track_id: availability}`. An availability is `"local"` (the file is on this device), `"synced"`
  (on this device and kept in step with another place) or `"remote"` (not on this device). Only
  `"remote"` is left out by the filter. A track missing from the answer, or with another value,
  counts as `"local"`. `status` runs on the graphical thread each time a track list is drawn or
  refiltered while the filter is on: keep it cheap and read only the plugin's own data.
- `context.availability_changed(track_ids)`, from any thread: the core calls `status` again for
  those tracks, or for every track with `None`. Call it when the answer for some tracks changed.
- The filter: the gear menu of a track list has "Hide tracks not on this device", and Settings >
  Library has the same switch. Both change one stored choice, which applies to every track list.
  It is off at first. While it is on, the meta line of a list shows how many tracks are hidden.
- The item and the switch are shown only while a running plugin provides `TrackAvailability`.
  Without one nothing is asked and no track is hidden; the stored choice is kept.
- The plugin draws its own badge with a `TrackColumn` (see "Contributions"): its `value_fn` returns a
  `CellValue` for the states it shows, and `None` for an empty cell.
- A plugin declares `TrackAvailability` at most once; declaring it twice makes the plugin Failed.
  MTEE accepts one provider in total. When a second running plugin declares it, that plugin is
  marked Failed with a reason that names the first one (`Track availability is already provided by
  <first plugin>`), and the one notice of the start announces it. The first plugin in load order
  keeps the contribution and keeps working, and the core asks only it. A `status` that raises, or
  does not return a mapping, is logged, and every track counts as `"local"`.

### Status item

An optional capability (`API_VERSION` stays 1) for a plugin that shows a short state at the bottom of
the window, for example whether a server is reached, or a sync in progress.

- `StatusItem(item_id, icon, on_click=None)`: the declaration. `item_id` is lowercase snake_case, and
  `icon` is an icon name of the core. A plugin declares at most one; a second one makes it Failed.
- `context.status_item.update(text, tone="neutral", progress=None, tooltip="", icon=None)` shows the
  item or changes it. `tone` is `neutral`, `secondary` or `warning`. `progress` is a number from 0 to
  1, or `None` for no progress line. `tooltip` is the sentence shown on hover. `icon`, when given,
  replaces the declared icon for this update. `context.status_item.clear()` hides the item.
- Both calls may come from any thread; the change is queued to the graphical thread. A bad value (a
  tone that is not one of the three, a progress outside 0 to 1, a text that is not a string) raises
  `ValueError` or `TypeError` in the calling thread, and nothing is shown.
- The item appears at the first `update`. Items are shown in plugin load order. The strip under the
  player bar is drawn only while at least one item is shown; without any, the window keeps its full
  height.
- `on_click()` runs on the graphical thread when the user clicks the item, for example to open a
  plugin activity or dialog. Without `on_click` the item is plain text. A failing `on_click` is
  logged and announced once; the application goes on.

### QML of a plugin

A plugin QML file starts with `import QtQuick` and `import Mtee`. The core adds its QML folder
to the import path, so `Mtee` gives the plugin the singleton `Theme` and the public components
of the interface. The plugin never reads files or runs commands from QML (`AGENTS.md`,
Architecture); it talks to its `backend`, a `QObject` it created, and the core never references
a plugin QML type when it loads. The core loads each file by URL with a `Loader` and sets properties
after loading, so every binding must work while a property is still unset:

- a **tab file** (`TabKind.content` as a `Path`) receives `workspace`, `tab`, `groupIndex`,
  `bottomInset` and `backend`;
- a **dialog file** receives `workspace`, `backend`, `ref` and `dialog` (see `PluginDialog`);
- a **Settings page file** receives `workspace` and `backend`. Its root fills the width of the
  page.

Components of `Mtee` for a Settings page, all taking the width of their parent:

| Component | Properties and signals |
| --- | --- |
| `Group` | `title`: a heading with a rule. |
| `ToggleRow` | `label`, `description`, `checked`, `toggled(bool)`. |
| `ActionRow` | `label`, `description`, `detail`, `actionText`, `actionKind` (`ghost`, `primary`, ...), `code` (a `CodeBadge` left of the button), `enabledAction`, `danger`, `action()`. |
| `StepperRow` | `label`, `description`, `value`, `from`, `to`, `step`, `chosen(int)`. |
| `FieldRow` | `label`, `description`, `value`, `placeholder`, `edited(string)` on Enter or leaving the field. |
| `InfoRow` | `label`, `description`, `value`: a read-only value. |
| `NoticeCard` | `title`, `text`: a warning card. |
| `CodeBadge` | `text`: a short code. |
| `DangerButton` | `text`, `enabledAction`, `clicked()`. |

Components of `Mtee` to draw windows, lists, menus and dialogs (UI rework, plan 130). They use
the tokens of `Theme` (`frameSize`, `windowGap`, `radiusWindow` 8, `radiusControl` 6,
`radiusChip` 4, `radiusCover` 2, `windowSurface`):

| Component | Properties, signals and use |
| --- | --- |
| `WindowSurface` | A rounded window. `focused` (accent outline), `padding`, `cornerColor` (the colour behind the window, `Theme.chrome` by default). Children go into its clipped content area. |
| `SplitHandle` | The hit area across the gap between two windows. `orientation` (`Qt.Horizontal`: windows side by side), `dragged(delta)` (pixels since the press), `released()`, `doubleClicked()`. It draws only on hover or drag. |
| `Popover` | A drop-down under `anchorItem`, closed by Esc or a click outside, kept 8 px inside the window. `alignRight`, `bodyWidth`, `maxHeight`; children are its content. |
| `HeaderButton` | A `Theme.frameSize` square icon button. `icon`, `badge` (a count), `active`, `tip`, `enabledAction`, `clicked()`. |
| `TagChip` | A small label. `text`, `tone` (`neutral`, `primary`, `warning`). |
| `CycleButton` | A ghost icon button stepping through `options` (`[{key, label, icon}]`). `currentKey`, `chosen(key)`. |
| `SearchField` | An icon that unfolds a field; Esc clears and folds. `text`, `placeholder`, `open`, `edited(text)`. |
| `ConfirmDialog` | A modal question. `title`, `text`, `buttons` (`[{key, label, kind}]`, kind `primary`, `ghost` or `danger`), `answered(key)` (`"cancel"` for Esc); children are extra content. |
| `InlineEdit` | A field that replaces a label to rename it. `begin(text)`, `keepExtension`, `committed(text)`, `cancelled()`. |
| `NavItem` | One sidebar row. `size` (`compact` 28 px or `regular` 52 px), `leading` (a cover URL, one letter or an icon name), `title`, `subtitle`, `tag`, `tagTone`, `depth`, `expandable`, `expanded`, `selected`, `renaming`, `dropTarget`; `clicked(modifiers)`, `doubleClicked()`, `contextRequested(x, y)`, `chevronClicked()`, `renamed(text)`. `trailing: [...]` adds items at the right end. |
| `NavList` | A list of `NavItem` rows from an array or `ListModel` of `{id, title, ...}`. Click, Ctrl+click and Shift+click select by row id across depths: `selectedIds`, `anchorId`, `selectionUpdated()`, `activated(rowId)`, `rowContextRequested(rowId, x, y)`, `rowDragStarted(ids)`. |
| `TabStrip` | The tab strip of a center window. `tabs` (`[{id, title, kind, icon, preview}]`), `activeId`, `groupId`, `focused`, `switcher`, `switcherEntries`; `tabClicked`, `tabClosed`, `tabKept`, `tabMoved(tabId, index)`, `tabDropped(payload, index)`, `switcherChosen`. A tab drag carries `{type: "tab", groupId, tabId}` with the drag key `mtee-tab`. `trailing: [...]` adds buttons at the right end. |
| `DropZoneOverlay` | Placed over a center window: draws the left, right, top, bottom or center drop zone while a `mtee-tab` or `mtee-folder` drag is over it and emits `dropped(zone, payload)`. The pure function `zoneAt` is in `dropzones.js`. |
| `ActionMenu` | A menu built from `groups` (`[{id, items: [{id, label, hint, icon, enabled, visible, danger, submenu}]}]`) with one separator between non-empty groups; `triggered(id)`. |

`Mtee` also offers the controls of the core (`TextButton`, `IconButton`, `ToggleSwitch`,
`FilterChip`, `CheckLine`, `Icon`, menus and others, listed in `src/mtee/qml/Mtee/qmldir`).
The sample plugin's `settings.qml` shows the rows in use.

## 8. Files, writes, packaging, tests and documentation

- A plugin changes audio files only through the core's write services (`context.files`). Every
  write follows the Data safety rules of `AGENTS.md`: copies in tests, unknown tags and cover
  art kept, no overwrite, no permanent delete.
- A plugin that produces new files reports them as derived outputs through the core, so they
  are tracked and can be found again.
- Long work runs as a job through `context.jobs`, with a state, a progress value, a way to
  cancel and a readable error. Tasks shows an exception as `ClassName: message`; an exception
  with the class attribute `readable = True` is shown as its message alone, so write that
  message as a sentence that names the cause and where to fix it. An optional `code` attribute
  (a string) is kept as the error code of the job.
- The plugin's UI uses the existing layouts and components. It does not add a new screen layout
  without a review, as the Architecture rules of `AGENTS.md` require.
- Dependencies a plugin needs are pinned and recorded like any other dependency
  (`AGENTS.md`, Dependencies and licences). A package carries the libraries its plugin needs
  (section 11); nothing is fetched at install time.
- Each plugin has tests in `tests/plugins/<id>/` and passes the **contract tests**.
- Each plugin folder has a `README.md` with these headings, in this order:
  1. What it does, for the user.
  2. Requirements and external tools (with their licences).
  3. Data it stores and where.
  4. How to test it.
  5. Known limits.

### Contract tests

`tests/plugins/test_contract.py` runs on the sample plugin and on any plugin you point it at.
For a plugin in another folder:

    MTEE_CONTRACT_PLUGIN_DIRS=path/to/plugin/folder uv run pytest tests/plugins/test_contract.py

Every plugin package with a valid manifest in the folders listed (separated by the operating
system's path separator) is tested next to the sample. A plugin test module may instead define
`pytest_generate_tests` that parametrizes `plugin` with a `ContractPlugin(plugin_id, folder)`
and import the `test_*` functions. The tests run the plugin against fakes of the core services
and a real database. They check that:

- the plugin loads and unloads cleanly, and loads again;
- a failure of the factory or a broken contribution disables only that plugin, with one notice;
- its migrations apply on an empty database and on a copy of a current database, create only
  tables named after the plugin and leave the core history unchanged;
- its UI entries are hidden when it is disabled, and its code is not imported;
- a manifest with an unsupported `api_version` never imports the factory module.

`tests/plugins/test_sample_ui.py` starts the real window with `--plugin-dir tests/plugins` and
checks the Plugins page, the switch across restarts, every contribution of the sample and the
failing sample. Run each test file on its own (`QT_QPA_PLATFORM=offscreen uv run pytest
<file> -q -p no:cacheprovider`).

## 9. Versioning of the contract

- `API_VERSION` is `1`; `SUPPORTED_API_VERSIONS` lists the versions this MTEE accepts.
- Adding an optional capability does not change the version.
- Removing or changing an existing call changes the version. The core keeps the previous version
  working for one minor release, then drops it. The change is noted in `CHANGELOG.md`.

## 10. Decision needed

The Marketplace (section 12) is public, and so is this contract, so that the rules are the same
wherever a plugin lives. The Spotify plugin lives in a private repository and is installed from
its package file only. Before the first plugin is listed in the Marketplace, the maintainer decides
whether every listed plugin follows this contract without exception. This is not decided yet.

## 11. Package files

A plugin ships as a package file, `<id>-<version>.mteeplugin`, which is a zip archive. The format
is in `src/mtee/plugins/package.py`; the packing script writes it:

    uv run python scripts/pack_plugin.py <plugin folder> --out <dir> [--requirements <file>]
        [--wheel <file.whl>] [--allow-source <name>] [--platform win_amd64]
        [--licence <name>] [--author <name>] [--homepage <url>]

The plugin folder is the package itself (`manifest.py` inside, named after the id). The script
refuses to overwrite a package that exists. The installer that reads these files is
`src/mtee/plugins/installer.py` (section 11.1). Bundled libraries are installed for `win_amd64`,
which is the default with `--requirements` or `--wheel`; `--platform any` with libraries is
refused.

Layout, at the root of the archive:

    plugin.json     # static description, read before any code of the package runs
    <id>/           # the plugin package: manifest.py, code, migrations/, QML
    libs/           # the libraries the plugin bundles, unpacked (may be empty)
    README.md       # the plugin's description, when the folder has one
    LICENSES/       # licence texts: the plugin's in <id>/, each library's in <library>/

`plugin.json` is one JSON object with sorted keys:

- `schema` (1), `id`, `title`, `description`, `version`, `api_version`, `author`, `homepage`,
  `licence`, `uses_network`: as `manifest.py` declares them, with the author, homepage and
  licence given to the packing script.
- `python` (`"3.12"`) and `platform` (`"win_amd64"` when the libraries are for Windows, else
  `"any"`).
- `mtee`: the MTEE versions the package was built for, the same minor version, for example
  `">=0.1,<0.2"`.
- `libraries`: each bundled library with `name`, `version` (the one bundled), `accepts` (the
  version range the plugin works with) and `licence`.
- `top_level_modules`: each importable module of `libs/` mapped to the library that provides it.

`accepts` is the range the requirements file writes (`>=2.28,<3`). A pinned line, as a hashed
file has, gives `==x.y.z`. A library that is only a dependency gets `==<bundled version>`.

**Libraries MTEE ships are never bundled.** The packing script reads MTEE's runtime closure, as
`mtee.plugins.package.mtee_runtime_libraries` computes it: the libraries `mtee` requires, and their
requirements in turn, with the markers true for this interpreter and without extras. The
development tools of the environment (pytest, PyInstaller) are not MTEE's libraries. A requirement
MTEE ships is not bundled: the plugin uses MTEE's copy. When
the plugin's range does not accept MTEE's version, the packing stops with one sentence. The
install takes the whole requirements file (hash checking needs every dependency pinned), then the
distributions MTEE ships are removed from `libs/`; their wheels are downloaded and checked, then
dropped. The packing uses `uv pip install` for `win_amd64` and Python 3.12, from binary wheels
only, since `pip` is not installed in the project environment.

A library that is published only as a source archive is named with `--allow-source <name>`
(repeatable). uv builds it on the packing machine, and the packing refuses it when the build left
compiled modules (`.pyd`, `.so`): such a library needs its Windows wheel. Without the option a
source archive is refused, as before. A pure-Python library built this way is bundled like any
other.

A folder that holds a `plugin.json` (an unpacked package) refuses a plugin whose manifest
disagrees with it on `id`, `version` or `api_version`. A folder without one loads as before.

### 11.1 Installer

The plugins folder is `<data-dir>/plugins/`. It holds one folder per installed plugin,
`<data-dir>/plugins/<id>/`. A package is read without running any of its code. Its check
(`inspect`) refuses it with one readable sentence when:

- an entry is absolute, has a drive letter, or contains `..`: `The package has an entry outside
  its folder: <name>.`
- an entry is a link, or the entries unpack to more than 500 MB;
- `plugin.json` is missing or invalid (its own sentence names the field or the line);
- `api_version` is not one this MTEE supports;
- `python` is not `3.12`, or `platform` is neither `any` nor `win_amd64` (on Windows);
- the `mtee` range does not contain the running MTEE version;
- the id is not lowercase snake_case, or is a name MTEE uses itself;
- `<id>/manifest.py` is missing;
- it bundles a library MTEE ships: `<Plugin> bundles requests, which MTEE already provides.
  Rebuild the package.`
- it bundles a library that an installed plugin also bundles, with no version both accept:
  `Spotify and Loudness report need different versions of requests (==2.31.0 and >=2.32).
  Spotify was not installed.` The plugin it replaces (same id) is not compared.

`install` runs the check, extracts the whole package into `<data-dir>/plugins/.staging/<id>/`,
discovers the extracted plugin (its manifest must agree with its `plugin.json`), sends an existing
`plugins/<id>/` to the Recycle Bin, and renames the staging folder into place. A new plugin is
switched on. A plugin that was installed and switched off stays off after an update. A failed
install leaves nothing behind; a leftover `.staging` folder is sent to the Recycle Bin at the next
start, before any plugin is found.

`uninstall` sends `plugins/<id>/` to the Recycle Bin and switches the plugin off. Its
`plugin-data/<id>/` folder and its database tables stay.

Nothing is deleted permanently: folders go through `TrashService.recycle_folder`. A folder unpacked
by hand into `plugins/<id>/` is listed and loaded like an installed plugin.

### 11.2 Shared libraries and the import finder

Python loads a module once per process, so the plugins that load share one copy of each library
they bundle. For each library, `plan_libraries` (`src/mtee/plugins/libraries.py`) chooses the
highest bundled version that every plugin using it accepts. When no bundled version suits every
plugin, the later plugin, by identifier, is shown `Failed` with the same sentence and is not
loaded; the choice is made again without it.

Before any plugin factory is imported, one meta path finder is put first on `sys.meta_path`. It
serves each top-level module of a chosen library from the `libs/` folder of its copy. A `libs/`
folder is never added to `sys.path` as a whole, so the order of the plugins does not decide which
copy is imported. Submodules resolve through their package. `PluginManager.library_locations`
gives the chosen mapping (module to `libs/` folder); a helper process reads it to use the same
copies. The finder is removed when the plugins are unloaded.

## 12. Marketplace

MTEE reads its plugin list from `index.json` in the `foliarn/mtee-plugins` repository
(`INDEX_URL` in `src/mtee/plugins/marketplace.py`). The list is read only when the Marketplace
opens or on "Check again", never in the background. Its format is `schema: 1` with
`plugins: [{id, title, description, author, homepage, licence, uses_network, versions:
[{version, api_version, python, platform, url, sha256, size, released}]}]`. A malformed entry is
skipped and logged; a malformed list is one readable error.

A package is downloaded only when the user asks. Its address must be
`https://github.com/<owner>/<repo>/releases/download/...`. The file is streamed to
`<data-dir>/plugins/.downloads/<id>-<version>.mteeplugin.part`. Its size and SHA-256 must match
the list, and its `plugin.json` must name the same id and version; only then is it renamed. It
then goes through the same check, warning and install as a local file. A failed or cancelled
download removes its partial file.

The compatible version is the highest package whose `api_version` is supported, whose `python`
is 3.12, and whose `platform` is `any` or this platform. An installed plugin offers an update
only when a compatible package is higher. The maintainer's steps are in
`docs/marketplace/README.md`.

## 13. Where the user installs and manages plugins

The Plugins view is the activity of the left bar with the plugin icon. It is always there.

- **Installed** lists each plugin with its status: `Running`, `Disabled`, `Failed` (with the
  reason) or `Restart needed`. The switch saves the choice; a change applies after a restart,
  and the view offers **Restart now**. **Uninstall** sends the plugin folder to the Recycle Bin
  without a prompt; the plugin's data stays in `<data-dir>/plugin-data/<id>/`.
- **Marketplace** lists the plugins of the plugin list. It is read when the view shows it, and
  again on **Check again**. Install and Update download the package, check its SHA-256 against the
  list, and then show the same warning as a local file.
- **Install from file** takes a `.mteeplugin` file. The warning names the plugin, its author,
  version and size, and says that a plugin runs with full access to the computer. Install only
  plugins you trust.
- **Open plugins folder** opens `<data-dir>/plugins/` in Explorer.

A plugin's own Settings page (for example Accounts) stays in Settings. Each plugin's detail page
opens in an editor tab (tab kind `plugin`). Installs, downloads and uninstalls run as jobs in Tasks,
with progress and Cancel.
