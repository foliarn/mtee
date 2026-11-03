"""Background services of the server.

`start` runs when the application starts and `stop` when it shuts down.
"""

from __future__ import annotations

from pathlib import Path

from starlette.applications import Starlette

from mtee_remote.library.service import LibraryService
from mtee_remote.streaming import settings as streaming_settings
from mtee_remote.streaming.cache import TranscodeCache

GIGABYTE = 1024**3


def start(app: Starlette) -> None:
    """Start the library service (scan and hash threads) and the transcode cache.

    The streaming settings are read here, once: a changed setting applies at the next start.
    The results are `app.state.streaming_settings` and `app.state.transcodes`.
    """
    settings = app.state.settings
    service = LibraryService(app.state.db, settings)
    app.state.library = service
    service.start()

    streaming = streaming_settings.server_streaming_settings(app.state.db.conn())
    app.state.streaming_settings = streaming
    cache_dir: Path = settings.data_dir / "cache" / "transcodes"
    cache = TranscodeCache(
        cache_dir,
        max_concurrent=int(streaming["max_transcodes"]),
        limit_bytes=int(streaming["cache_limit_gb"]) * GIGABYTE,
        music_dir=settings.music_dir,
    )
    cache.clear_stale_parts()
    app.state.transcodes = cache


async def stop(app: Starlette) -> None:
    """Stop the background services: the library threads, then running transcodes."""
    service: LibraryService | None = getattr(app.state, "library", None)
    if service is not None:
        service.stop()
    cache: TranscodeCache | None = getattr(app.state, "transcodes", None)
    if cache is not None:
        await cache.close()
