"""Command line of MTEE.

The interface is in English. An unknown argument is refused with the usage
text instead of being ignored.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from mtee.demo.scenarios import DEFAULT_SCENARIO, SCENARIO_NAMES

__all__ = ["AppOptions", "build_parser", "parse_arguments"]

PROGRAM_NAME = "mtee"
_DESCRIPTION = "MTEE — explore, listen to and organise a local audio collection."


@dataclass(frozen=True, slots=True)
class AppOptions:
    """Options of one run."""

    data_dir: Path | None = None
    demo: bool = False
    smoke_test: bool = False
    scenario: str = DEFAULT_SCENARIO
    diagnostic_no_native_frame: bool = False
    plugin_dirs: tuple[Path, ...] = ()


def build_parser() -> argparse.ArgumentParser:
    """Return the parser of the supported arguments."""
    parser = argparse.ArgumentParser(prog=PROGRAM_NAME, description=_DESCRIPTION)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        metavar="PATH",
        help="Store settings, cache and logs under PATH instead of the system location.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Show invented data with an isolated storage; no user file is read.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Load the window, then quit with a success or failure exit code.",
    )
    parser.add_argument(
        "--scenario",
        choices=SCENARIO_NAMES,
        default=DEFAULT_SCENARIO,
        help="Open a deterministic demo review scenario.",
    )
    parser.add_argument(
        "--plugin-dir",
        type=Path,
        action="append",
        default=None,
        metavar="PATH",
        help=(
            "Load the plugin packages in PATH for this run only. Repeat for several folders. "
            "The folders are not saved; installed plugins are always loaded."
        ),
    )
    parser.add_argument(
        "--diagnostic-no-native-frame",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def parse_arguments(argv: Sequence[str] | None = None) -> AppOptions:
    """Return the options of ``argv``.

    ``argparse`` prints the usage and exits with code 2 for an unknown argument.
    """
    parsed = build_parser().parse_args(argv)
    return AppOptions(
        data_dir=parsed.data_dir,
        demo=bool(parsed.demo),
        smoke_test=bool(parsed.smoke_test),
        scenario=str(parsed.scenario),
        diagnostic_no_native_frame=bool(parsed.diagnostic_no_native_frame),
        plugin_dirs=tuple(parsed.plugin_dir or ()),
    )
