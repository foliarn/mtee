# Changelog

All notable changes to MTEE are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
- The Plugins activity of the left bar lists the installed plugins and the Marketplace, installs
  from a package file or the Marketplace, uninstalls to the Recycle Bin and offers a restart
  (plan 123.6). Settings > Plugins is removed; a plugin's own Settings page stays.
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
