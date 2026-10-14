# scripts/archive

Scripts kept for reference. They are not part of the application, the build or CI.

- Step-specific review and validation scripts (`review_*`, `validate_*`, `measure_*`, fixture generators for a given plan). Some depend on mock-ups or UI that have since changed and may no longer run.
- Personal-collection tools (artist enrichment pilot, genre and artist clean-up, track genre audit). They read a real music collection and can write to a real catalog database: run them only against copies, or with their dry-run defaults.

Run any of them from the repository root, for example `uv run python scripts/archive/<name>.py --help`.
