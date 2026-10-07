"""Roles, tags and hidden state of an artist, as kept in ``artist_enrichment_reviews``.

The four roles are a closed list; an artist may have several. ``idgaf`` is the tag that
hides an artist from the catalog and always goes with the ``exclude`` decision.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

__all__ = [
    "HIDDEN_TAG",
    "NO_ROLE",
    "ROLES",
    "ArtistProfile",
    "is_hidden",
    "normalize_roles",
    "normalize_tags",
]

ROLES: tuple[str, ...] = ("Producer", "DJ", "Singer", "MC")
NO_ROLE = "No role"
HIDDEN_TAG = "idgaf"

_SPACES = re.compile(r"\s+")
_MAX_TAG_CHARACTERS = 40
_MAX_TAGS = 20


def normalize_roles(roles: Iterable[object]) -> list[str]:
    """Return the known roles of ``roles``, once each, in alphabetical order.

    The order is the one already stored (``["DJ", "MC", "Producer", "Singer"]``).
    """
    wanted = {str(role).strip().casefold() for role in roles}
    return sorted((role for role in ROLES if role.casefold() in wanted), key=str.casefold)


def normalize_tags(tags: Iterable[object]) -> list[str]:
    """Return the free tags: trimmed, without ``idgaf``, once each (case ignored), bounded."""
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        text = _SPACES.sub(" ", str(tag)).strip()[:_MAX_TAG_CHARACTERS].strip()
        key = text.casefold()
        if not text or key == HIDDEN_TAG or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result[:_MAX_TAGS]


def is_hidden(decision: str, tags: Iterable[object]) -> bool:
    return decision == "exclude" or any(str(tag).strip().casefold() == HIDDEN_TAG for tag in tags)


@dataclass(frozen=True, slots=True)
class ArtistProfile:
    """What the catalog shows and lets the user edit about one artist."""

    roles: list[str] = field(default_factory=list)
    bass_related: bool | None = None
    tags: list[str] = field(default_factory=list)
    hidden: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "roles": list(self.roles),
            "bassRelated": self.bass_related,
            "tags": list(self.tags),
            "hidden": self.hidden,
        }
