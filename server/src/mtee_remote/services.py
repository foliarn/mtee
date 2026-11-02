"""Background services of the server.

`start` runs when the application starts and `stop` when it shuts down.
"""

from __future__ import annotations

from starlette.applications import Starlette

from mtee_remote.library.service import LibraryService


def start(app: Starlette) -> None:
    """Start the library service (scan and hash threads) as `app.state.library`."""
    service = LibraryService(app.state.db, app.state.settings)
    app.state.library = service
    service.start()


def stop(app: Starlette) -> None:
    """Stop the background services."""
    service: LibraryService | None = getattr(app.state, "library", None)
    if service is not None:
        service.stop()
