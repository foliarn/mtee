# Agent instructions

These rules apply to every coding agent and every human contributor. `CONTRIBUTING.md` covers
the public process; this file covers how to change the code safely. Where a rule here and a
user's instruction conflict, the user's instruction wins for that task.

## 1. Project

MTEE is a local music player and library manager.

- Language and stack: Python 3.12, PySide6 (Qt Essentials), QML. No Electron, no WebView.
- Platform: Windows first. The app runs on the user's own machine and reads the user's own files.
- Interface and documentation: English.

## 2. Before you change anything

1. Read this file, then `docs/plugins.md` if the task touches a plugin.
2. Run `git status`. Changes you did not make are someone else's work. Leave them alone, and
   do not include them in your commit.
3. Find the existing layout, component, service or test that already does the job, and reuse it.
4. For anything larger than a small fix, state the plan in two or three sentences before editing.

## 3. Architecture

- QML talks only to Qt models and Python services. QML never reads the file system and never
  runs a system command.
- Long operations (scans, analysis, writes, conversions) run off the graphical thread and
  report progress through jobs.
- Keep these stores separate. Do not merge them:
  - audio sources;
  - metadata written to files;
  - analysis computed by MTEE;
  - manual corrections;
  - derived files.
- Use the existing interface patterns (editor tabs, sidebar, in-page tab strip, list rows).
  A new layout pattern needs a short justification and a review before it is built.

## 4. Data safety

- Test every write operation on copies of audio files, never on the user's originals.
- Preserve unknown tags and cover art on every write.
- Never overwrite a file. Choose a new name.
- Never fall back to a permanent delete. If the Recycle Bin is unavailable, stop and report it.
- Never commit personal collections, databases, settings, credentials, logs with personal paths,
  or downloaded binaries.
- Use `.local/` for local runs, test data and scratch output. It is git-ignored.

## 5. Plugins

Plugins follow one contract, written in [docs/plugins.md](docs/plugins.md). In short:

- The core never imports a plugin. A plugin imports only the core's public plugin interface.
- A plugin owns its tables and migrations. It writes audio files only through the core's write
  services and follows section 4.
- A plugin that fails to load is disabled alone. The application keeps running.
- A plugin's UI uses the existing components and layouts.

## 6. Working loop

1. Make one focused change.
2. Add or update a test that fails before the change and passes after it.
3. Run the quality gates (section 7).
4. For a user-visible change, run the app from the sources and check the behaviour directly:
   `uv run python -m mtee --data-dir .local/dev`.
5. Add a line under `## [Unreleased]` in `CHANGELOG.md` for any user-visible change.
6. Report what you ran and what it showed. Say plainly what you did not check.

Do not run `scripts/build_windows.ps1` or `scripts/smoke_packaged.ps1` unless the task is about
packaging or distribution.

## 7. Quality gates

All four must pass before a change is ready:

    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run pytest

Some tests need the pinned libmpv runtime. Run `pwsh -File scripts/fetch_mpv.ps1` once to
install it. If a gate fails before your change (a pre-existing failure), say so and list it.
Do not hide it.

## 8. Commits, branches and versions

- Commit messages use the conventional form: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`,
  `chore:`. The subject is short. The body explains why.
- One commit does one thing. Do not mix a fix and a refactor.
- Agents do not commit, push or tag unless the user asks. When asked, use a branch, not `main`.
- Never rewrite published history or force-push to `main`.
- Versions follow [Semantic Versioning](https://semver.org/) while the major version is 0:
  - patch (`0.1.1`): bug fixes only, no new feature, no database change;
  - minor (`0.2.0`): new features, behaviour changes or database migrations;
  - major (`1.0.0`): reserved for a stable public promise.
- Only the maintainer decides a version number and creates a release.

## 9. Dependencies and licences

- Pin every dependency in `uv.lock`. After a dependency change, run `uv sync --locked`.
- A newly distributed component needs its licence text under `LICENSES/` and an entry in
  `THIRD_PARTY_NOTICES.md`, with the version actually observed.
- Check the licence before adding a dependency. Record any doubt in `THIRD_PARTY_NOTICES.md`.

## 10. Never, without explicit approval

- Delete user data, or any file outside `.local/` and the build output.
- Change `dist/`, the installer or the packaging spec for an ordinary change.
- Add a network call, telemetry or an account requirement.
- Change the licence of the project.
- Publish a release, a tag or a package.
- Commit anything listed in section 4 as private.

## 11. When to stop and ask

Ask the user before you proceed when:

- the change would alter stored data, a migration or a file format;
- two rules in this file conflict;
- the task needs a decision that only the user can make, such as a product choice or a licence;
- a step is destructive or cannot be undone.

Otherwise, make the reasonable choice, state it in your report, and continue.
