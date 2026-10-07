"""Give the artists of a library root the genres of the folders their tracks sit in.

The default run only writes a report. ``--apply`` backs the database up first, then adds
the genres as tags of the artists (a remix gives its genre to the remixer only). Tags typed
by hand are kept; the tags of an earlier run are replaced. Close nothing: SQLite handles it.

    python scripts/genres_from_folders.py --database mtee.sqlite3 --report-dir report
    python scripts/genres_from_folders.py --database mtee.sqlite3 --apply
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mtee.domain.folder_genres import IGNORED_FOLDERS
from mtee.persistence.artist_repository import ArtistRepository
from mtee.persistence.database import Database
from mtee.services.folder_genre_service import FolderGenreService, GenrePlan


def backup(path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = path.with_name(f"{path.name}.before-folder-genres-{stamp}.bak")
    with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(target)) as copy:
        source.backup(copy)
    return target


def write_report(plan: GenrePlan, folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    markdown = folder / "genres.md"
    artists = folder / "artist-genres.csv"
    unresolved = folder / "unresolved-remixes.csv"
    tagged = len(plan.artist_genres)
    lines = [
        f"# Genres from the folders of `{plan.root}`",
        "",
        f"- Tracks in the root: {plan.tracks}",
        f"- Artists that receive at least one genre: {tagged}",
        f"- Tracks without credits (skipped): {plan.uncredited}",
        "- Tracks by rule: "
        + ", ".join(f"{name} {count}" for name, count in sorted(plan.statuses.items())),
        "",
        "Rules: `plain` = every credited artist; `remix`/`remixer-credit` = the remixer only;",
        "`unresolved` = a remixer is named but is not among the credits, nobody is tagged.",
        "",
        "## Genres",
        "",
        "| Genre | Tracks | Artists |",
        "|---|---|---|",
    ]
    counts = plan.genre_artists
    for genre, tracks in plan.genre_tracks.most_common():
        lines.append(f"| {genre} | {tracks} | {counts[genre]} |")
    lines += ["", "## Folders ignored", "", "| Folder | Tracks |", "|---|---|"]
    lines += [f"| {name} | {count} |" for name, count in plan.ignored_folders.most_common()]
    lines += [
        "",
        f"## Remixes whose remixer is not among the credits ({len(plan.unresolved)})",
        "",
        "Nobody is tagged for these tracks. Details in `unresolved-remixes.csv`.",
        "",
        f"## Markers found in the file name or the original title only ({len(plan.lost_markers)})",
        "",
        "The final title has lost the `(X Remix)` marker; it was recovered from the other sources.",
        "",
        "| File | Remixer named | Rule |",
        "|---|---|---|",
    ]
    for item in plan.lost_markers:
        lines.append(f"| {item['path']} | {', '.join(item['names'])} | {item['status']} |")
    markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with artists.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["artist", "genres", "tracks"])
        for artist_id, genres in sorted(
            plan.artist_genres.items(), key=lambda item: plan.artist_names[item[0]].casefold()
        ):
            writer.writerow(
                [
                    plan.artist_names[artist_id],
                    "; ".join(f"{name} ({count})" for name, count in genres.most_common()),
                    sum(genres.values()),
                ]
            )
    with unresolved.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["file", "folder genres", "remixer named", "credits"])
        for item in plan.unresolved:
            writer.writerow(
                [
                    item["path"],
                    "; ".join(item["genres"]),
                    "; ".join(item["names"]),
                    "; ".join(item["credits"]),
                ]
            )
    return [markdown, artists, unresolved]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--root", default="foliarn", help="name of the library root to read")
    parser.add_argument("--ignore", action="append", help="top folder to skip (repeatable)")
    parser.add_argument("--report-dir", type=Path, help="where to write the report")
    parser.add_argument("--apply", action="store_true", help="write the tags (backup first)")
    args = parser.parse_args(argv)
    if not args.database.is_file():
        print(f"No database at {args.database}", file=sys.stderr)
        return 2

    database = Database(args.database)
    try:
        service = FolderGenreService(database, ArtistRepository(database))
        plan = service.plan(args.root, args.ignore or IGNORED_FOLDERS)
        print(
            f"{plan.tracks} tracks, {len(plan.artist_genres)} artists get a genre, "
            f"{len(plan.genre_tracks)} genres, {len(plan.unresolved)} remixes unresolved."
        )
        if args.report_dir:
            for path in write_report(plan, args.report_dir):
                print(f"Wrote {path}")
        if not args.apply:
            print("Nothing written to the database. Run again with --apply.")
            return 0
        print(f"Backup: {backup(args.database)}")
        print(f"Applied: {service.apply(plan)}")
    finally:
        database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
