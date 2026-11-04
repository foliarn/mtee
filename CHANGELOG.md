# Changelog

All notable changes to MTEE are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.3.0] - 2026-11-04 - GUI Update

### Added
- Playlists "New folder" no longer asks for a name: the folder is made at once as "Untitled folder
  NN" and its row is in inline rename, like a new folder of the Explorer.
- Songs can move between windows: drag a selection from a list onto a playlist list (it adds them)
  or onto a folder list (it moves the files; hold Ctrl to copy them). Ctrl+C, Ctrl+X and Ctrl+V
  on a list do the same with the keyboard: a playlist takes the tracks (a cut leaves its source
  playlist), a folder list copies or moves the files. Files are never overwritten: a name already
  taken is refused and reported.
- The playing song in the player bar can be dragged onto a playlist (the sidebar row or an open
  playlist), and a right click on its title opens the same menu as a track row.
- A right click on a tab opens Close, Close others, Close all, Close tabs to the left / right and
  Split right / left / up / down.
- MTEE comes back as you left it: the windows and their split sizes, the tabs of each window
  (folders, playlists, Settings, Profile, Tasks), the active tab and window, both docks
  with their tool windows and sizes, and the position and size of the window. A tab whose folder
  source or playlist is gone is dropped silently.
- Finished background tasks each end with one sentence that says what they did (for example
  "123 songs analysed, 0 errors"); the sentences reach the header and the bell in the next steps
  of the UI rework.
- The header shows the running task (label, count, bar, `+N` for the others) while a job runs;
  a click lists the running tasks with Cancel. A bell in the header lists what waits for you (tag
  conflicts, plugin items) and the notifications of the session; a balloon under the bell shows a
  new notification or a message for 5 seconds, so no toast covers the player.
- Tasks window: a center tab with the session's tasks on the left (unfinished first, then the
  finished ones) and the selected task's record on the right: summary, start, end or elapsed time,
  counts, the items that failed (with Show in folder for a file path) and Cancel while it runs.
  Opened from the hamburger menu, or by Details in a notification.
- Folder lists have the playlist search control (folded into an icon, Esc clears it).
- Playlists scroll as one page: the playlist header scrolls away with the rows, and the column
  header sticks to the top of the list once the header has gone. Artwork view keeps the header.
- Playlist and folder menus: the column menu lists only columns; "Custom order", "Show artwork"
  and "Reset columns" are in a separate "More" menu next to it.
- Explorer tree: Ctrl-click and Shift-click select songs across folders; `Del`, the track menu and
  the drag to a folder act on the whole selection. Tree rows use the sidebar list look.
- Track menu: the same menu everywhere a track can be right-clicked (folder lists, playlists,
  the Explorer tree, the Queue, the History and the Fullscreen player), regrouped, with Go to
  artist, Show in folder and Rename file. The file actions (Open in Windows Explorer, Rename
  file, Delete file) are a separate group at the bottom. Play, Move up and Move down are gone
  from the menu.
- Reusable interface components for windows, lists, menus and dialogs (see `docs/plugins.md`).
- Window frame: a header with the menu, Back and Forward, and the plugin status icons; a left and a
  right tool bar; the player along the foot. Windows are rounded and 5 px apart.
- Tool windows in two docks. The left dock is Explorer, Playlists, Artists and the plugin windows;
  the right dock is Info, Queue and History. A dock shows two windows stacked: Shift+click a bar
  button, or use its "Open below" menu entry.
- Centre windows split in any direction: drag a tab, or an Explorer folder, to an edge of a window.
  The split button is gone; Ctrl+\ and Ctrl+Shift+\ split the focused window.
- Keyboard shortcuts: Ctrl+B and Ctrl+Alt+B for the docks, Alt+1 to Alt+5 for the left windows,
  Alt+Q and Alt+H for the Queue and the History, Ctrl+1 to Ctrl+9 to focus a window, Ctrl+Tab and
  Ctrl+Shift+Tab for the tabs, Ctrl+Alt+Arrow to move a tab, Ctrl+Shift+W to close a window,
  Alt+Left and Alt+Right for the history, Ctrl+Shift+Left and Ctrl+Shift+Right to resize a dock,
  and Esc to close a floating dock. Settings > Keyboard shortcuts lists them by group.
- Explorer: "Remove from library…" on a source. Its files stay on disk; its analysis, edits and
  play stats are kept, so adding the folder again brings the same tracks back.
- Explorer: "New folder" (made at once as "Unnamed folder NN"), "Rename…" and "Delete folder…" (to the Recycle Bin, with a count of the
  tracks and sub-folders) on a folder, and "Open in Windows Explorer" on a folder or a source.
- Playlists window: playlists and folders are rows of the same height with 2 px covers; folders
  have a folder tile. Liked tracks has a heart cover that "Change cover…" replaces. The playlist,
  Liked tracks and folder menus are rebuilt; a folder is renamed in place and deleted either with
  its playlists moved up one level or with everything inside it.
- Artists window: a button on the count line cycles A–Z, Z–A, Most tracks and Fewest tracks. The
  order is kept with the workspace.
- A new folder in the Explorer is created at once as "Unnamed folder 01" (the first free number),
  with no name asked; rename stays a separate action.
- A liked-tracks row without a cover of its own shows the covers of its first tracks as a 2x2
  mosaic, or the heart when there are none.

### Fixed
- Liked tracks shows its heart again, in the sidebar and on the big cover of its page, instead of a
  mosaic of four placeholder covers.
- A header button closes its open popover (notifications, menu, tasks, volume) instead of closing
  and reopening it.
- The hamburger menu and the other menus opened by a button (More, Add) close when the button is
  clicked again, instead of closing and reopening at once.
- Column borders of a playlist list can be dragged: the drag saves all the widths it moved in one
  write, so the column next to the border takes the change.
- The column header of a track list has a solid background, so rows do not show through it.

### Changed
- A folder page scrolls its heading away with the rows and keeps only the column row in place, like a
  playlist; on a playlist the search, columns and More controls sit on the Play row.
- The chevron of a folder row sits to the right of its label, so folder icons line up with the
  playlist icons.
- The Tasks tool window is gone from the left bar: tasks live in the header strip, the bell and the
  Tasks window. A saved layout that held it drops it on load.
- Track list: columns that do not fit the window leave from the right for that width (they stay
  checked in the column menu, marked "not enough room"); the table never scrolls sideways, and
  the heart and add buttons sit in their own cell, after Artist when only Title and Artist fit.
- Plugins window: the installed and the Marketplace plugins are one list, each plugin once. Under
  an installed plugin a tag shows Running, Failed or Installed; a plugin that is not installed has
  no tag. The order is installed plugins listed by a marketplace, other installed plugins, then the
  Marketplace plugins not installed, each by name.
- Buttons, fields, menus, dialogs and tabs have rounded corners.
- The mouse wheel scrolls three times further in every list and page.
- The player is a full-width bar at the foot of the window, always shown and greyed out when
  nothing plays. The floating player island and its "Show player island" setting are gone.
- Ctrl+\ on a window with one tab opens that tab in a new window on the right; the tab stays
  in the first window too.
- Below 1100 px an open dock floats over the centre and closes on a click outside or on Esc. Below
  760 px the centre shows only its focused window; its tab strip lists the others. The window
  opens at least 560 × 420 px. Below 760 px the header hides Back and Forward, and below 640 px
  the status icons move into the menu.
- The saved window layout is version 2, converted once from version 1 at the first start. The
  version 1 text is kept as `workspace.v1.json` next to `mtee.sqlite3` in the data folder, so an
  older build can be restored by hand.
- The menu bar is one hamburger menu in the header.
- Track list columns: a column that does not fit leaves from the right (Title and Artist stay with
  the heart and (+) buttons), nothing runs past the window edge, and the widths can be dragged on
  the border between two columns (the columns on the right give way, down to their minimum).
  Double-click a border to reset its column. Text is left-aligned and numbers right-aligned.
- Playlist header: the play time reads "1 h 32 min" instead of "1 hr 32 min"; Liked tracks has no
  description line.
- Settings: the "Preferences" label is gone, and the first tab lines up with the "Settings" heading.

## [0.2.0] - 2026-11-03

### Added

- Gapless playback: consecutive tracks play with no silence between them, and each track keeps
  its own loudness normalization from its first sample. A manual skip behaves as before.
- MTEE reads the ISRC tag of MP3, FLAC/Ogg and M4A files (not shown yet).
- A plugin can provide tracks that have no file on this computer (`context.track_sources` and the
  `TrackSource` contribution). They get a normal track identity, appear in the Artists view,
  playlists, the queue and the history, and play from a local file or an `http(s)` URL with
  request headers, gapless like a file. A failing source shows an error that names the plugin
  and playback goes on with the next track. File operations refuse such a track with a clear
  message. The database gains the table `plugin_source_tracks` (migration 030, backed up
  first). See `docs/plugins.md`, Track sources.
- Plugins load from the plugins folder `<data-dir>/plugins/` and from `--plugin-dir` (one run,
  not saved). A plugin is imported only once it is switched on, applies its own database migrations, and adds a
  sidebar section or activity, editor tabs, track list columns, track menu actions, a Settings
  page and startup tasks. A plugin that fails to start is disabled alone and shown as Failed.
  The contract is in `docs/plugins.md`; `tests/plugins/` holds a sample plugin and the contract
  tests every plugin passes.
- Settings rows (group, switch, action, stepper, text field, read-only value, notice and code
  badge) are shared components of the `Mtee` QML module, so plugin pages look like the core.
- A plugin can open a modal dialog (`open_dialog`), open or focus one of its tabs from any
  thread (`open_tab`), list work that waits for the user in the Tasks pane (`WaitingItems`),
  explain why a header button is disabled (`TabAction.disabled_reason`) and add a phrase to the
  meta line of local playlists (`PlaylistMeta`).
- A job error whose exception says `readable = True` is shown in Tasks as its sentence alone.
- A plugin can add choices to the Recycle Bin confirmation (`DeleteChoices`, plan 125.4). Without
  one the dialog is unchanged, and MTEE itself still only uses the Recycle Bin. A choice can send
  its files to the Recycle Bin without a second dialog (`request.recycle`), and a selection with no
  file on this computer shows the plugin's choices alone.
- The Recycle Bin confirmation has a Cancel button, which closes it and runs nothing.
- A plugin is packed into a `.mteeplugin` file by `scripts/pack_plugin.py`: `plugin.json` lists
  the bundled libraries and licences, MTEE's own libraries are never bundled (`docs/plugins.md`,
  section 11).
- Settings > Plugins lists the marketplaces: add a GitHub repository (`owner/repo`) or an https
  `index.json`, and switch any of them off. The official list cannot be removed, and a plugin
  offered by two lists shows twice, each row with its source.
- The Plugins activity of the left bar lists the installed plugins and the Marketplace, installs
  from a package file or the Marketplace, uninstalls to the Recycle Bin and offers a restart
  (plan 123.6). The plugin switches moved there from Settings > Plugins; a plugin's own Settings
  page stays.
- A plugin package is installed from its file into the plugins folder: MTEE checks it before
  anything is extracted (a path outside the package, a link, a Python, platform or MTEE version
  that does not fit, a library MTEE ships, a library version conflict). An update or uninstall
  sends the old folder to the Recycle Bin and keeps the plugin's data (plan 123.2).
- Plugins that bundle the same library share one copy: the highest version every one accepts.
  A plugin that cannot share one is shown Failed with the reason (plan 123.2).
- A plugin runs Python code in a helper process with `context.python_command` and
  `context.python_environment`, from the sources and from the packaged exe (`docs/plugins.md`,
  section 6; plan 123.3).
- Plugins can be listed in a Marketplace: MTEE reads the list from GitHub when asked and
  downloads a package only on request, checked against the list (`docs/plugins.md`, section 12;
  plan 123.4).
- A plugin can say which tracks are not on this device. Track lists then offer "Hide tracks not
  on this device" in their settings menu, with the number of hidden tracks in the meta line, and
  Settings > Library has the same choice (plan 125.3).
- The status bar under the player shows what a plugin reports, such as the state of a server,
  and a click runs the plugin's action. It is shown only while a plugin uses it (plan 125.5).
- For plugin developers (`API_VERSION` stays 1): the optional capabilities `TrackAvailability`,
  `StatusItem` and the store access for sync (`play_log`, playlist revisions, `track_data`,
  `synced_settings`, `database_snapshot`). `docs/plugins.md` describes each one, and the sample
  plugin uses it (plans 125.2 to 125.6).
- A plugin dialog can ask for a width from 320 to 640 pixels (`PluginDialog(width=...)`, 480 by
  default).
- For plugin developers (`API_VERSION` stays 1): the optional capability
  `files.replace_content(track_id, source)` puts a file in place of a track's file, keeping the
  track's identifier. The old file goes to the Recycle Bin through the trash path and journal
  (plan 126.4). See `docs/plugins.md`, section 6.
- For plugin developers (`API_VERSION` stays 1): the optional capabilities
  `track_sources.adopt(track_id, entry)`, which makes a library track without a file a source
  track under the same identifier, and `files.attach_file(track_id, source, folder)`, which gives a
  source track its local file under the same identifier. The views read the track again after
  `replace_content`, `adopt` and `attach_file` (plan 126.5). See `docs/plugins.md`, section 6 and
  "Track sources".
- For plugin developers (`API_VERSION` stays 1): the optional capabilities
  `playlists.list()` (every local playlist with its revision and size), `playlists.rename(id,
  name, expected_revision)` (the interface's rename, with the revision check) and
  `track_data.changed_since(cursor, limit)` (the tracks whose analysis, loudness or corrections
  changed). The last one reads a change log that the database gains with migration 031, written by
  triggers and backed up first. See `docs/plugins.md`, section 6.
- Developers: the sidebar contract gains optional fields, `API_VERSION` stays 1. `PaneAction` takes
  `label` (a text button) and `visible`; `SidebarSection` takes `on_fold`, `count` and `expanded`;
  `PluginActivity` takes `badge`. A click on the name of a group row calls `activate`, and a
  `tone="warning"` row is drawn in the warning colour. See `docs/plugins.md`, section 7.

### Changed

- A plugin's own data folder is `<data-dir>/plugin-data/<id>/`, outside the plugins folder.
- `--plugin-dir` folders are used for the run only; the saved plugin folder list and its rows
  in Settings > Plugins are removed.

### Fixed

- Entries of the track context menu that are hidden no longer leave an empty band in it.
- The Recycle Bin confirmation is centred over the window, and it names a track that a plugin
  provides without a file by its artist and title, not by its identifier.
- The column picker shows a plugin named "... plugin" once ("Sample plugin", not "Sample plugin
  plugin").
- The detail tab of a plugin shows its version, its details and the switch that turns it on;
  it showed an empty page, so a plugin could not be switched on.
- MTEE no longer crashes now and then while closing: a cover still being loaded could read the
  database after it was closed.
- MTEE starts with about 490 MB less private memory on a large library. The numerical library
  reserved one buffer per CPU core when it was imported; MTEE now lets it use one thread, which
  costs no speed for its small calculations.

## [0.1.0] - 2026-10-15

First public release. Windows is the supported platform.

### Added

- Library explorer with folders, tracks, sorting, column choice and search.
- Playback through libmpv: queue, shuffle and repeat, full-screen player, waveform view.
- Windows media controls: media keys, headsets and the system media panel.
- Metadata editing with history; unknown tags and cover art are preserved.
- File moves by drag and drop; removed files go to the Recycle Bin.
- Analysis of tempo, musical key and loudness, stored apart from the tags.
- Volume normalization from the measured loudness, with a peak ceiling.
- Local playlists with export and import as archives.
- Artists view built from the Artist tags, with links from tracks and top artists.
- Listening journal, profile statistics by period, and data backup, restore and erasure.
- Demo mode with fictitious data kept apart from the library.
- `--data-dir`, `--demo` and `--smoke-test` command-line options.

### Changed

- The artist and genre management tools were removed from the core and are not part of this
  release. The database keeps the history of their migrations, so an older database opens
  without error.
- Audio conversion is a plugin and is not part of this release. FFmpeg remains in use for
  analysis and waveforms.

### Notes

- The application runs from source with `uv sync --locked`. A Windows executable,
  `MTEE.exe`, is attached to the release.
