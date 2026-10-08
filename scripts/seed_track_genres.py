"""Preview, apply or recover a reviewed local track genre seed (no audio writes)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mtee.services.genre_seed_service import GenreSeedService, verified_copy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--root-id")
    parser.add_argument("--report-dir", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true")
    mode.add_argument("--apply-plan", type=Path)
    mode.add_argument("--undo-operation")
    mode.add_argument(
        "--copy-to", type=Path, help="Make a verified coherent copy without migration"
    )
    args = parser.parse_args()
    if args.copy_to:
        print(verified_copy(args.database, args.copy_to))
    elif args.apply_plan:
        service = GenreSeedService(args.database)
        plan = json.loads(args.apply_plan.read_text(encoding="utf-8"))
        print(json.dumps(service.apply(plan)))
    elif args.undo_operation:
        print(GenreSeedService(args.database).undo(args.undo_operation))
    else:
        if not args.root_id or not args.report_dir:
            parser.error("Preview requires --root-id and --report-dir")
        service = GenreSeedService(args.database)
        plan = service.preview(args.root_id)
        service.write_report(plan, args.report_dir)
        print(json.dumps(plan["summary"], ensure_ascii=False))
        print(args.report_dir / "summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
