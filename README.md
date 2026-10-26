<p align="center"><img src="src/mtee/resources/brand/mtee-512.png" width="128" alt="MTEE logo"></p>

# MTEE: Music Tagging and Editing Explorer

MTEE is a desktop application for exploring, listening to, tagging and preparing a local
collection of audio files. It is written in Python 3.12 with PySide6 and QML, has no
Electron or WebView, and targets Windows first. Everything runs locally: the library is
read from your own folders, and your data stays in a local database.

> **Status:** version 0.1.0, first public release. Windows is the supported platform.

## Screenshots

_Screenshots to be added: explorer, player with waveform, metadata editor, artists view,
listening statistics._

## Features in 0.1.0

- **Library explorer.** Browse folders and tracks, sort and choose columns, search, and
  follow the artists and albums of your collection.
- **Playback.** Play with libmpv, with a queue, shuffle and repeat, a full-screen player and a
  waveform view. Volume normalization uses loudness measured by the analysis.
- **Windows media controls.** Keyboard media keys, headsets and the Windows media panel
  control playback.
- **Metadata editing.** Edit tags of one or many tracks. Changes are written with a history,
  unknown tags and cover art are preserved, and no file is overwritten silently.
- **File operations.** Move files by drag and drop, rename from tags, and send removed files to
  the Recycle Bin. A permanent delete never replaces an unavailable Recycle Bin.
- **Audio conversion.** Convert files through FFmpeg, with a visible job queue.
- **Analysis without machine learning.** Tempo, musical key and loudness are computed from the
  audio and stored separately from the tags you wrote.
- **Playlists.** Local playlists, drag and drop, and export and import as archives.
- **Artists.** A read-only artist index built from the Artist tags, with links from tracks and
  top artists.
- **Listening journal and profile.** A local record of what you play, with statistics by
  period. Everything can be reviewed, backed up, restored or erased from the Settings.

Demo data is available with `--demo`. It is kept in a storage separate from your library.

## Build and run from source

Requirements: Windows 10 or 11, [uv](https://docs.astral.sh/uv/), and PowerShell 7 for the
helper scripts.

    uv sync --locked
    uv run python -m mtee

Useful options:

- `--data-dir PATH` keeps the database, settings and caches of a session in a separate folder.
- `--demo` starts with fictitious data in a separate storage.
- `--smoke-test` loads the window, then exits with a success or failure code.

The audio runtimes are not stored in the repository. To use the playback and conversion
features from source, fetch the pinned runtimes first:

    pwsh -File scripts/fetch_mpv.ps1
    pwsh -File scripts/fetch_ffmpeg.ps1

Each script checks the size and SHA-256 hash of the downloaded archive against its manifest in
`resources/native/` before installing anything into the git-ignored `vendor/` folder.

## Checks

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest

Some tests need the pinned libmpv runtime. Without it they fail rather than skip.

## Licence

MTEE is free software, distributed under the GNU General Public License version 3 or later
(`GPL-3.0-or-later`). See [LICENSE](LICENSE). Third-party components and their licences are
listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and their licence texts are in
[LICENSES/](LICENSES/).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and the rules for developers and coding agents in
[AGENTS.md](AGENTS.md).
