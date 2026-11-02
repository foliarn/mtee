"""The `mtee-remote` command line."""

from __future__ import annotations

import argparse
import sys

from mtee_remote import commands_library, commands_users
from mtee_remote.app import create_app
from mtee_remote.config import Settings


def serve(args: argparse.Namespace) -> int:
    import uvicorn

    try:
        settings = Settings.from_env()
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    uvicorn.run(
        create_app(settings),
        host=args.host,
        port=args.port,
        proxy_headers=True,
        forwarded_allow_ips=settings.trusted_proxies,
        workers=1,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mtee-remote", description="MTEE Remote server")
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("serve", help="run the HTTP server")
    p.add_argument("--host", default="0.0.0.0")  # the container binds all addresses
    p.add_argument("--port", type=int, default=8080)
    p.set_defaults(func=serve)

    p = commands.add_parser("create-admin", help="create the first administrator")
    p.add_argument("--username", required=True, metavar="NAME")
    p.set_defaults(func=commands_users.create_admin)

    p = commands.add_parser("reset-password", help="set a new password for an account")
    p.add_argument("--username", required=True, metavar="NAME")
    p.set_defaults(func=commands_users.reset_password)

    p = commands.add_parser("create-user", help="create an account")
    p.add_argument("--username", required=True, metavar="NAME")
    p.add_argument("--admin", action="store_true", help="make the account an administrator")
    p.add_argument("--quota-gb", type=float, default=None, metavar="N", help="storage quota in GB")
    p.set_defaults(func=commands_users.create_user)

    p = commands.add_parser("adopt-root", help="adopt an existing folder as a library root")
    p.add_argument("--user", required=True, metavar="NAME")
    p.add_argument("--path", required=True, metavar="PATH")
    p.add_argument("--name", required=True, metavar="NAME")
    p.set_defaults(func=commands_library.adopt_root)

    p = commands.add_parser("scan", help="scan a user's library")
    p.add_argument("--user", required=True, metavar="NAME")
    p.add_argument("--root", default=None, metavar="NAME")
    p.set_defaults(func=commands_library.scan)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
