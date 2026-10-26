# Changelog

All notable changes to MTEE are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-10-15

First public release. Windows is the supported platform.

### Added

- Library explorer with folders, tracks, sorting, column choice and search.
- Playback through libmpv: queue, shuffle and repeat, full-screen player, waveform view.
- Windows media controls: media keys, headsets and the system media panel.
- Metadata editing with history; unknown tags and cover art are preserved.
- File moves by drag and drop; removed files go to the Recycle Bin.
- Audio conversion through FFmpeg with a visible job queue.
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

### Notes

- The application runs from source with `uv sync --locked`. A packaged Windows build is
  not part of this release description.
