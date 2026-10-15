# Contributing to MTEE

Thank you for considering a contribution. MTEE is a personal desktop project, so changes are
reviewed carefully and some proposals may be declined to keep the scope small.

## Before you start

- Open an issue to discuss a feature or a large refactoring before writing code.
- Bug reports should say which version you ran, what you did, what you expected and what
  happened. Attach the relevant lines of the log, never a copy of your music library or your
  database.

## Development setup

    uv sync --locked
    uv run python -m mtee --data-dir .local/dev

Use `--data-dir` so that your test sessions never touch a real library. Keep `.local/` out of
commits.

## Checks

Run these before opening a pull request:

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest

Tests that need the pinned libmpv runtime fail when it is missing. Run
`pwsh -File scripts/fetch_mpv.ps1` once to install it.

## Guidelines

- The interface is in English. Code comments and documentation are in English.
- Keep the layers separate: QML talks to Python through Qt models and services only, never to the
  file system or to system commands directly. Long operations run off the graphical thread.
- Writes to audio files are tested on copies. Unknown tags and cover art must be preserved, and
  files must never be overwritten silently.
- Add or update a test for each behaviour change. Prefer small, focused tests.
- Write commit messages in the conventional style (`feat:`, `fix:`, `refactor:`, `docs:`,
  `test:`), with a body that explains the reason of the change.

## Licence

By contributing, you agree that your contribution is licensed under the GNU General Public
License version 3 or later, the licence of the project.
