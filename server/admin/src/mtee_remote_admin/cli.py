"""`mtee-remote-admin`: the terminal interface, or a one-line status for scripts."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .compose import Compose, ComposeError, health
from .envfile import EnvFile
from .paths import layout

INSTALL = "curl -fsSL https://raw.githubusercontent.com/foliarn/mtee-remote/main/install.sh | sh"


def print_status() -> int:
    """The state of the container and of `/health`, without the interface (for scripts)."""
    where = layout()
    if not where.installed:
        print(f"Not installed: no source in {where.source}. Run the install script.")
        return 1
    if not where.configured:
        print(f"Not set up: no {where.env_file}. Run mtee-remote-admin.")
        return 1
    values = EnvFile.read(where.env_file).values()
    try:
        state = Compose(where).state()
    except ComposeError as error:
        print(f"Docker: {error}")
        return 1
    reached, version = health(values.get("BIND_ADDRESS", ""), values.get("PORT", "8080"))
    answer = f"answers (version {version})" if reached else "does not answer"
    print(
        f"Container {state}; {values.get('BIND_ADDRESS', '127.0.0.1')}:"
        f"{values.get('PORT', '8080')} {answer}."
    )
    return 0 if state == "running" and reached else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mtee-remote-admin", description="Set up and run a MTEE Remote server."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--status", action="store_true", help="print the state and exit")
    args = parser.parse_args(argv)
    if args.status:
        return print_status()
    where = layout()
    if not where.installed:
        print(
            f"No server source in {where.source}. Run the install script first:\n  {INSTALL}",
            file=sys.stderr,
        )
        return 1
    from .app import AdminApp  # Textual is imported only for the interface

    AdminApp(where).run()
    return 0
