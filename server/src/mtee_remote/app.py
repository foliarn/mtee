"""The application factory."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from mtee_remote import __version__, services
from mtee_remote.config import Settings
from mtee_remote.db import Database
from mtee_remote.errors import ApiError, api_error_handler, http_exception_handler
from mtee_remote.journal import ChangeNotifier
from mtee_remote.routes import (
    admin,
    auth,
    backups,
    changes,
    devices,
    items,
    roots,
    trash,
    uploads,
)
from mtee_remote.security import AuthMiddleware

DATA_SUBDIRS = ("db-backups", "uploads", "trash", "backups")


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "version": __version__})


def create_app(settings: Settings) -> Starlette:
    for name in DATA_SUBDIRS:
        (settings.data_dir / name).mkdir(parents=True, exist_ok=True)
    db = Database(settings.data_dir / "mtee-remote.db", settings.data_dir / "db-backups")
    db.migrate()
    notifier = ChangeNotifier()
    db.on_commit = notifier.notify

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        notifier.attach_loop(asyncio.get_running_loop())
        services.start(app)
        try:
            yield
        finally:
            services.stop(app)

    routes: list[BaseRoute] = [Route("/health", health)]
    for module in (auth, devices, admin, roots, items, uploads, trash, changes, backups):
        routes.extend(module.ROUTES)

    app = Starlette(
        routes=routes,
        middleware=[Middleware(AuthMiddleware)],
        exception_handlers={ApiError: api_error_handler, HTTPException: http_exception_handler},
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db = db
    app.state.notifier = notifier
    return app
