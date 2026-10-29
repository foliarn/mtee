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

MTEE loads plugins only from folders the user gives:

- `--plugin-dir PATH` on the command line, repeatable. The folders given are saved in the
  setting `plugins.folders` and used again at the next start. A saved folder that no longer
  exists is reported and skipped.
- `Settings > Plugins` adds and removes folders, and switches plugins on and off
  (`plugins.enabled`, a list of ids).

There is no scan of any other place, no download and no install from the internet.

Discovery lists the direct children of each folder that hold a `manifest.py`. It executes the
manifest file alone, never `__init__.py` or the factory module. The code of a plugin is imported
only once the plugin is enabled. A manifest is refused, with a readable reason, when:

- its `plugin_id` differs from the folder name, or is not lowercase snake_case;
- the folder has no `__init__.py`;
- its `api_version` is not one this MTEE supports (the factory module is not imported);
- its `factory` is not written `module:function` or is outside `mtee.plugins.<id>`;
- another plugin folder already provides the same id (the first one found is kept).

A refused plugin is shown `Failed` in `Settings > Plugins` with the reason.

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
   off stays running until then, and `Settings > Plugins` says so.
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
running. `Settings > Plugins` shows `Failed` with the message; the switch stays on, since it is
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
| `library` | `track_ids()`, `tracks(ids)` (`LibraryTrack`: id, path, title, artists, album, `duration_us`, `readable`, `isrc`), `add_watched_folder(path)` and `rescan(path)`. The last two on the graphical thread only. |
| `playlists` | `create(name, track_ids)`, `replace_entries(playlist_id, track_ids)`, `entries(playlist_id)`, `name(playlist_id)` (`None` when it is gone) and `exists(playlist_id)`, through the core playlist service. |
| `jobs` | `submit(task, label=..., visible=...)` and `cancel(job_id)` on the core job service. |
| `files` | The core write services: `move_track(track_id, root_id, relative_folder)`, `import_file(source, folder)` and `recycle(track_ids)` (the user confirms in the usual dialog). Never a file API on a music file. See below. |
| `settings` | A key-value store scoped to the plugin: `get`, `set`, `get_json`, `set_json`, `delete`. Keys live under `plugins.<id>.` in the settings. |
| `base_dir`, `data_dir` | `<data-dir>/plugins/<id>/`. `data_dir` creates the folder when first read; use it for tokens and caches. |
| `notify(text)` | Shows a message on the workspace message line. Any thread. |
| `log` | A logger named `mtee.plugins.<id>`. |
| `refresh_ui()` | Asks the core to read the rows, header buttons and cells of the plugin again after its data changed. Any thread. |
| `run_on_gui(fn)` | Runs `fn()` on the graphical thread, after the current event: a queued call, also when called from the graphical thread. Any thread. A `fn` that raises is logged under the plugin's logger. |
| `open_dialog(dialog_id, ref)` | Opens one of the plugin's `PluginDialog` as a modal popup over the window. Any thread. `ref` is handed to the dialog's QML. |
| `open_tab(kind, ref)` | Opens, or focuses when it is already open, a tab of one of the plugin's own `TabKind` (`kind` starts with `<plugin_id>.`, another is refused and logged). Any thread; the tab opens on the graphical thread. |

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

The factory returns a `PluginService` with two methods: `contributions()`, returning a list of
contributions, and `unload()`, which releases threads and files and leaves the data.

## 7. Contributions

A contribution is data. The core draws it with its own components and colours; a plugin never
names a core QML type in it. Icons are icon names of the core (`music`, `repeat`,
`arrow-down`...). Every identifier is lowercase snake_case and unique within its kind.

- `PluginActivity(activity_id, title, icon, actions=(), foot=None)`: a button in the activity
  bar and a sidebar pane. `actions` are `PaneAction(action_id, tip, icon, run)` buttons in the
  pane header. `foot` is a `PluginRowsModel` of `{"text", "tone"}` rows (`tone`: `secondary`,
  `muted` or `warning`) drawn at the bottom. The id may not be a core activity name.
- `SidebarSection(section_id, title, activity, model, actions=(), activate=None)`: a
  collapsible section. `activity` is `"playlists"` (below the local playlists), `"explorer"`
  or the `activity_id` of a `PluginActivity` of the same plugin. `model` is a
  `PluginRowsModel` the plugin keeps up to date; a row has `id` and `name`, and optionally
  `depth`, `kind` (`item` or `group`), `expanded`, `icon`, `tone`, `badge` and `count`.
  `activate(row_id)` returns a `TabRequest(kind, ref)` or `None`.
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
  menu, in a captioned group named `group` before "File actions". `enabled_fn(rows)` decides
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
- `PluginDialog(dialog_id, content, backend=None)`: a modal dialog, opened with
  `context.open_dialog(dialog_id, ref)`. `content` is a QML file. The core draws the popup
  (surface, border, radius 8, 20 px padding, at most 480 px wide, centred, closed by Escape or a
  click outside) and loads the file in it; the file draws the title, fields and buttons with the
  components of `Mtee` and gives its `implicitHeight`. It receives `workspace`, `backend`, `ref`
  and `dialog`, whose `close()` closes the popup. The sample plugin's `dialog.qml` shows it.
- `PlaylistMeta(text)`: `text(playlist_id)` returns a phrase (for example `linked to Spotify`)
  or `""`. The core joins the phrases of all plugins to the meta line of the header of every
  local playlist with ` · `, and reads them again after `refresh_ui()`. `text` runs on the
  graphical thread while the header is drawn: keep it cheap.
- `LibraryScanned(callback)`: `callback(root)` is called on the graphical thread after the scan
  of a library folder completed (a folder added, a rescan, or the scan at start). `root` is the
  `Path` of that library folder; the scanned tracks are already in the library. A scan that was
  cancelled, replaced by a newer one or interrupted is not announced. Nothing is called for a
  plugin that is off or unloaded. A `callback` that raises is caught, logged and announced once.

`TrackListRow` rows, `TabKind` track list functions and `TrackColumn.value_fn` run on a **job
thread** while a list loads. Keep them cheap, read only the plugin's own data (the database
gives each thread its own connection) and call no Qt widget or model. The other functions
(`activate`, `run`, `checked`, `enabled`, `enabled_fn`, `title_fn`, `header`, `run_action`)
run on the graphical thread, so they must return quickly and hand slow work to `jobs`.

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
  cancel and a readable error.
- The plugin's UI uses the existing layouts and components. It does not add a new screen layout
  without a review, as the Architecture rules of `AGENTS.md` require.
- Dependencies a plugin needs are pinned and recorded like any other dependency
  (`AGENTS.md`, Dependencies and licences). Plugins run from the sources; the frozen Windows
  build carries none.
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

Plugins live in the private repository for now. This contract is public so that the rules are
the same wherever a plugin lives. Before any plugin is shipped publicly, the maintainer decides
whether it follows this contract without exception.
