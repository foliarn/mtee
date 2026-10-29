# Changelog

All notable changes to MTEE are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- MTEE reads the ISRC tag of MP3, FLAC/Ogg and M4A files (not shown yet).
- Plugins load from the folders the user gives (`--plugin-dir`, or Settings > Plugins). A plugin
  is imported only once it is switched on, applies its own database migrations, and adds a
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

### Fixed

- Entries of the track context menu that are hidden no longer leave an empty band in it.

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

- The application runs from source with `uv sync --locked`. A packaged Windows build is
  not part of this release description.
