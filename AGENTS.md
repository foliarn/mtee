# Rules for contributors and coding agents

MTEE is a desktop application in Python 3.12, PySide6 and QML, without Electron or WebView.
Windows comes first and the application runs locally, on the user's own machine.

## Architecture

- QML talks only to Qt models and Python services. Never read the file system or run system
  commands from QML.
- Long operations (file scans, audio analysis, writes, conversions) leave the graphical thread
  and report through jobs.
- Keep the layers separate: audio sources, written metadata, computed analysis, manual
  corrections and derived files are distinct stores. Do not merge them.
- Use the existing layouts and components of the interface before creating new ones.

## Data safety

- Test every write operation on copies of audio files.
- Preserve unknown tags and cover art.
- Avoid overwrites: pick a new name rather than replacing an existing file.
- Never fall back to a permanent delete when the Recycle Bin is unavailable.
- Never commit personal collections, local databases, settings, credentials or downloaded
  binaries. Use `.local/` for local runs and test data.

## Quality gates

Before a commit is ready:

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest

Add tests for each behaviour change. Verify a user-facing change by running the application
from the sources (`uv run python -m mtee --data-dir .local/dev`) and by checking the behaviour
directly.

Do not run the Windows packaging scripts (`scripts/build_windows.ps1`,
`scripts/smoke_packaged.ps1`) as part of an ordinary change. Run them only when the task is a
packaging or distribution task.

## Commits

- Use conventional messages (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`).
- Keep each commit focused. Explain the reason in the body.
- Do not rewrite the history of a shared branch, and never force-push over another person's
  work.

## Dependencies and licences

- Pin dependencies in `uv.lock`, and run `uv sync --locked` after a change of dependency.
- A new distributed component needs its licence text under `LICENSES/` and an entry in
  `THIRD_PARTY_NOTICES.md`, with the version actually observed.
