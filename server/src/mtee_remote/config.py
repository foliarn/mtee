"""Server settings, read from environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Everything the server needs to start; immutable once built."""

    data_dir: Path
    music_dir: Path
    public_url: str | None = None
    scan_interval_s: int = 0
    trusted_proxies: str = "127.0.0.1"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ

        def required(name: str) -> str:
            value = env.get(name, "").strip()
            if not value:
                raise ValueError(f"The environment variable {name} is required.")
            return value

        scan_raw = env.get("MTEE_REMOTE_SCAN_INTERVAL", "").strip()
        scan_interval = 0
        if scan_raw:
            try:
                scan_interval = int(scan_raw)
            except ValueError:
                raise ValueError(
                    "MTEE_REMOTE_SCAN_INTERVAL must be a whole number of seconds, "
                    f"got {scan_raw!r}."
                ) from None
            if scan_interval < 0:
                raise ValueError("MTEE_REMOTE_SCAN_INTERVAL must not be negative.")
        return cls(
            data_dir=Path(required("MTEE_REMOTE_DATA")),
            music_dir=Path(required("MTEE_REMOTE_MUSIC")),
            public_url=env.get("MTEE_REMOTE_PUBLIC_URL", "").strip() or None,
            scan_interval_s=scan_interval,
            trusted_proxies=env.get("MTEE_REMOTE_TRUSTED_PROXIES", "").strip() or "127.0.0.1",
        )
