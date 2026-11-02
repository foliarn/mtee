"""In-memory limit on failed login attempts, per user name and per client address.

The limiter lives in the server process and is lost on restart. That is acceptable for a
self-hosted server with a single worker.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable

from starlette.applications import Starlette

FREE_FAILURES = 5
BASE_WAIT_S = 30.0
MAX_WAIT_S = 3600.0
# 2 ** 20 already exceeds the cap; a bound keeps the arithmetic small.
_MAX_EXPONENT = 20


class LoginLimiter:
    """Counts failed logins per key and tells how long a key must wait.

    Failures 1 to 4 of a key have no wait. From the 5th failure on, the key is locked for
    `30 * 2 ** (failures - 5)` seconds, capped at 3600. A successful login resets the keys.
    """

    def __init__(self, now: Callable[[], float] = time.monotonic) -> None:
        self._now = now
        self._lock = threading.Lock()
        self._failures: dict[str, int] = {}
        self._locked_until: dict[str, float] = {}

    def retry_after(self, keys: Iterable[str]) -> float | None:
        """Return the seconds left on the longest lock among `keys`, or None if none is locked."""
        with self._lock:
            now = self._now()
            waits = [
                self._locked_until[key] - now
                for key in keys
                if key in self._locked_until and self._locked_until[key] > now
            ]
        return max(waits) if waits else None

    def failure(self, keys: Iterable[str]) -> None:
        """Record one failed attempt for each of `keys`."""
        with self._lock:
            now = self._now()
            for key in keys:
                count = self._failures.get(key, 0) + 1
                self._failures[key] = count
                if count >= FREE_FAILURES:
                    exponent = min(count - FREE_FAILURES, _MAX_EXPONENT)
                    wait = min(BASE_WAIT_S * 2**exponent, MAX_WAIT_S)
                    self._locked_until[key] = now + wait

    def success(self, keys: Iterable[str]) -> None:
        """Forget the failures and locks of `keys`."""
        with self._lock:
            for key in keys:
                self._failures.pop(key, None)
                self._locked_until.pop(key, None)


_CREATE_LOCK = threading.Lock()


def get_limiter(app: Starlette) -> LoginLimiter:
    """Return the application's limiter, creating it on first use."""
    with _CREATE_LOCK:
        limiter: LoginLimiter | None = getattr(app.state, "login_limiter", None)
        if limiter is None:
            limiter = LoginLimiter()
            app.state.login_limiter = limiter
        return limiter
