"""Identifier generation."""

from __future__ import annotations

import uuid


def new_id() -> str:
    """Return a new random identifier: a UUID4 as 32 lowercase hex characters."""
    return uuid.uuid4().hex
