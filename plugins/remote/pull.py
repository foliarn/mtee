"""Auto pull: the long poll that brings the changes of other devices in as they come (plan 126.4).

When *Auto pull* is on and the device is connected, one job loops over ``fetch_once(wait=25)``. The
server holds each request until a change comes or 25 seconds pass, so a change reaches this computer
within seconds, and an idle loop costs one request every 25 seconds.

``stop`` ends the loop at once: it sets the flag, closes the connection in use (the held request
ends with a network error), and cancels the job. The loop never raises out of its job.
"""

from __future__ import annotations

import contextlib
import threading

from mtee.domain.jobs import JobCancelledError
from mtee.plugins.api import JobContext, JobId, PluginContext

from .client import NetworkError, RemoteClient
from .fetch import fetch_once
from .store import RemoteStore

PULL_WAIT_S = 25.0
RETRY_S = 30.0
LABEL = "Pulling changes from MTEE Remote"


class AutoPull:
    """Starts and stops the pull loop. Graphical thread only; the loop itself runs in a job."""

    def __init__(self, context: PluginContext, store: RemoteStore) -> None:
        self._context = context
        self._store = store
        self._guard = threading.Lock()
        self._stop: threading.Event | None = None
        self._client: RemoteClient | None = None
        self._job: JobId | None = None

    @property
    def running(self) -> bool:
        with self._guard:
            return self._job is not None

    def start(self, client: RemoteClient) -> None:
        """Run the loop with ``client`` in a job, unless it runs already."""
        with self._guard:
            if self._job is not None:
                return
            stop = threading.Event()
            self._stop = stop
            self._client = client
            try:
                self._job = self._context.jobs.submit(
                    lambda job: self._loop(client, stop, job), label=LABEL, visible=False
                )
            except RuntimeError:
                # The application is shutting down: no new job is accepted.
                self._stop = None
                self._client = None

    def stop(self) -> None:
        """End the loop now: stop flag, the connection in use closed, the job cancelled."""
        with self._guard:
            stop, client, job = self._stop, self._client, self._job
            self._stop = None
            self._client = None
            self._job = None
        if stop is None:
            return
        stop.set()
        if client is not None:
            client.abort()
        if job is not None:
            with contextlib.suppress(Exception):
                self._context.jobs.cancel(job)

    def _loop(self, client: RemoteClient, stop: threading.Event, job: JobContext) -> None:
        try:
            while not stop.is_set():
                if not self._store.mappings():
                    # Nothing to apply until a folder is mapped; the changes wait on the server.
                    stop.wait(RETRY_S)
                    continue
                try:
                    job.raise_if_cancelled()
                    fetch_once(self._context, self._store, client, job, wait=PULL_WAIT_S)
                except JobCancelledError:
                    return
                except NetworkError:
                    if stop.is_set():
                        return
                    stop.wait(RETRY_S)
                except Exception as error:  # the loop goes on at the next round
                    self._context.log.warning("The automatic pull failed for a round: %s", error)
                    stop.wait(RETRY_S)
        finally:
            with self._guard:
                if self._stop is stop:
                    self._stop = None
                    self._client = None
                    self._job = None
