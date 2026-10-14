"""Credit rules the tag editor relies on, without any artist database behind them.

The tag editor only writes tags. It asks these rules which names hold a comma or ``&`` and
must never be cut, which known artists to suggest, and it reports the user's "One artist"
or "Several artists" choice. The default implementation keeps nothing: names are split as
typed and the choice is forgotten. A later store can provide the rules without changing
the tag editor.
"""

from __future__ import annotations

from typing import Any, Protocol

__all__ = ["ArtistCreditRules", "NoArtistCreditRules"]


class ArtistCreditRules(Protocol):
    """What the tag editor needs to split and suggest artist credits."""

    def protected_names(self) -> list[str]:
        """Return the names that hold a comma or ``&`` and are kept whole."""
        ...

    def suggestions(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Return known artists whose name contains ``query``, as ``{"id", "name"}``."""
        ...

    def record_credit_choice(self, text: str, *, one_artist: bool) -> None:
        """Remember that ``text`` is one artist (``True``) or several (``False``)."""
        ...


class NoArtistCreditRules:
    """Default rules: no protected name, no suggestion, and no recorded choice."""

    def protected_names(self) -> list[str]:
        return []

    def suggestions(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        return []

    def record_credit_choice(self, text: str, *, one_artist: bool) -> None:
        return None
