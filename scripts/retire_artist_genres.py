"""Preview, apply or undo the narrowly proven artist genre retirement from plan 107."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from contextlib import closing

from mtee.services.artist_genre_cleanup_service import ArtistGenreCleanupService
from mtee.services.genre_seed_service import protect_destination, readonly


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--witness", type=Path)
    parser.add_argument("--seed-start", default="")
    parser.add_argument("--seed-end", default="")
    parser.add_argument("--report-dir", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply-plan", type=Path)
    modes.add_argument("--undo-operation")
    args = parser.parse_args()
    service = ArtistGenreCleanupService(args.database)
    if args.apply_plan:
        result = service.apply(json.loads(args.apply_plan.read_text(encoding="utf-8")))
    elif args.undo_operation:
        result = {"inverse": service.undo(args.undo_operation)}
    else:
        if not args.report_dir:
            parser.error("--report-dir is required for preview")
        with closing(readonly(args.database)) as connection:
            roots = [str(r[0]) for r in connection.execute("SELECT path FROM library_roots")]
        protect_destination(args.report_dir, roots)
        plan = service.preview(args.witness, args.seed_start, args.seed_end)
        args.report_dir.mkdir(parents=True, exist_ok=False)
        (args.report_dir / "plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (args.report_dir / "summary.md").write_text(
            "# Retrait des genres artistes 107\n\n"
            + str(plan["summary"])
            + "\n\nLes cas ambigus restent inchangés. Aucun fichier audio n'est modifié.\n",
            encoding="utf-8",
        )
        result = plan["summary"]
    print(json.dumps(result))


if __name__ == "__main__":
    main()
