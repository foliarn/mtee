"""Prepare every local track and established artist; preserve audited pilot choices."""

import argparse
import shutil
from pathlib import Path

from artist_enrichment_pilot import dossiers, motifs, read_json, snapshot, write_json
from artist_pilot_server import ReviewStore


def prepare_full(database: Path, pilot: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError("Use a new output directory; existing decisions are never overwritten")
    catalog = snapshot(database, include_unreviewed=True)
    tracks = [{**t, "selection_categories": sorted(motifs(t))} for t in catalog["tracks"]]
    artists = dossiers(catalog, tracks)
    # Established profiles with no current credits still belong to the artist catalog.
    included = {a["artist_id"] for a in artists}
    artists.extend(
        {**a, "collection_tracks": 0, "representative_titles": [], "sample_tracks": []}
        for a in catalog["artists"]
        if a["artist_id"] not in included
    )
    output.mkdir(parents=True)
    write_json(output / "catalog.json", catalog)
    write_json(output / "sample.json", tracks)
    write_json(output / "artists.json", artists)
    for filename in ("observations.json", "musicbrainz.json", "review.json", "genre-rules.json"):
        source = pilot / filename
        if source.exists():
            shutil.copy2(source, output / filename)
    summary = read_json(pilot / "summary.json")
    summary.update(tracks=len(tracks), artists=len(artists), scope="full_collection")
    write_json(output / "summary.json", summary)
    return {
        "tracks": len(tracks),
        "artists": len(artists),
        "tracks_without_confirmed_credits": sum(not t["credits"] for t in tracks),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--import-validated-pilot", action="store_true")
    args = parser.parse_args()
    print(prepare_full(args.database, args.pilot, args.output))
    if args.import_validated_pilot:
        print(
            {"imported_validations": import_validated_pilot(args.database, args.pilot, args.output)}
        )


def import_validated_pilot(database: Path, pilot: Path, output: Path) -> int:
    store = ReviewStore(output, database)
    original = ReviewStore(pilot).effective_reviews()
    if set(original) - store.ids:
        raise ValueError("Pilot artist IDs are missing from the current catalog")
    saved = store.database.reviews()
    changes = {
        aid: {
            **r,
            "decision": "exclude" if r["decision"] == "exclude" else "keep",
            "bass_related": r["bass_related"] is True,
        }
        for aid, r in original.items()
        if aid not in saved
    }
    if changes:
        store.save_page(changes)
    return len(changes)


if __name__ == "__main__":
    main()
