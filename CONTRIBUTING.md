# Contributing to MTEE

Thank you for considering a contribution. MTEE is a personal desktop project, so changes are
reviewed carefully and some proposals may be declined to keep the scope small.

The rules for code, data and commits are in [AGENTS.md](AGENTS.md). They apply to human and
agent contributors alike. The plugin contract is in [docs/plugins.md](docs/plugins.md).

## Before you start

- Open an issue to discuss a feature or a large refactoring before writing code.
- Bug reports should say which version you ran, what you did, what you expected and what
  happened. Attach the relevant lines of the log, never a copy of your music library or your
  database.

## Development setup

    uv sync --locked
    uv run python -m mtee --data-dir .local/dev

Use `--data-dir` so that your test sessions never touch a real library. `.local/` is git-ignored;
keep it that way.

Some tests need the pinned libmpv runtime. Run `pwsh -File scripts/fetch_mpv.ps1` once to
install it.

## Checks

Run these before opening a pull request:

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest

## Pull requests

- One topic per pull request.
- Add or update a test for each behaviour change.
- Add a line under `## [Unreleased]` in `CHANGELOG.md` for a user-visible change.
- Describe what you ran and what you did not check.

## Licence

By contributing, you agree that your contribution is licensed under the GNU General Public
License version 3 or later, the licence of the project.
