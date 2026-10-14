"""Credit rules the tag editor relies on: how a typed credit is cut, and what is remembered.

The tag editor only writes tags. It asks these rules how a credit is cut, whether the user
must answer "One artist or several?", which known artists to suggest, and it reports that
answer. The core implementation is ``ArtistIndexService``: it shares the artist index with
the Artists view. The default implementation has no index and no store: a credit is cut by
the rules alone, and the answer is forgotten.
"""

from __future__ import annotations

from typing import Any, Protocol

from mtee.domain.artist_index import has_separator, split_artist_credit

__all__ = ["ArtistCreditRules", "NoArtistCreditRules"]


class ArtistCreditRules(Protocol):
    """What the tag editor needs to cut, question and suggest artist credits."""

    def split(self, text: str) -> list[str]:
        """Return the artists of a credit, under the rules and the user's choices."""
        ...

    def needs_choice(self, text: str) -> bool:
        """Return whether ``text`` holds a separator that the user has not answered yet."""
        ...

    def suggestions(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Return known artists whose name contains ``query``, as ``{"id", "name"}``."""
        ...

    def record_credit_choice(self, text: str, *, one_artist: bool) -> None:
        """Remember that ``text`` is one artist (``True``) or several (``False``)."""
        ...


class NoArtistCreditRules:
    """Default rules: no index, no suggestion, and no recorded choice."""

    def split(self, text: str) -> list[str]:
        return split_artist_credit(text)

    def needs_choice(self, text: str) -> bool:
        return has_separator(text)

    def suggestions(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        return []

    def record_credit_choice(self, text: str, *, one_artist: bool) -> None:
        return None
