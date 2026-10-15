"""Pure decision logic and effects for artist index rebuilds and artist pages."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mtee.domain.artist_index import album_track_order
from mtee.domain.artists import normalize_key

if TYPE_CHECKING:
    from mtee.domain.artist_index import ArtistIndex

__all__ = [
    "ArtistIndexEffects",
    "decide_artist_index_effects",
    "format_artist_decision_message",
    "prepare_artist_playback_rows",
    "sort_artist_tracks",
]


@dataclass(frozen=True)
class ArtistIndexEffects:
    """Outcome of an artist index rebuild on currently open workspace tabs."""

    opened_artist: tuple[str, str] | None
    stale_tabs: list[tuple[int, str]]
    retitled_tabs: list[tuple[str, str]]
    reloaded_tab_ids: list[str]


def decide_artist_index_effects(
    *,
    previous_index: ArtistIndex | None,
    new_index: ArtistIndex,
    pending_choice: tuple[str, frozenset[str]] | None,
    groups: list[dict[str, Any]],
    tab_states: dict[str, dict[str, Any]],
    is_plugin_artist: Callable[[str], bool],
) -> ArtistIndexEffects:
    """Compute UI reactions to an artist index change without side effects.

    Determines:
    - If a pending artist split/keep produced a new artist that should be opened.
    - Which open artist tabs are now stale (artist deleted) and should be closed.
    - Which open artist tabs need a title refresh.
    - Which open artist tabs have modified track lists and must be reloaded.
    """
    opened: tuple[str, str] | None = None
    if pending_choice is not None and new_index.entry(pending_choice[0]) is None:
        target_origins = pending_choice[1]
        for entry in new_index.artists:
            if target_origins & {normalize_key(origin) for origin in entry.origins}:
                opened = (entry.key, entry.name)
                break

    stale: list[tuple[int, str]] = []
    retitled: list[tuple[str, str]] = []
    reloaded: list[str] = []

    for group_index, group in enumerate(groups):
        for tab_id in group.get("tabs", []):
            if not tab_id.startswith("artist:"):
                continue
            key = tab_id.removeprefix("artist:")
            entry = new_index.entry(key)
            if entry is None:
                if not is_plugin_artist(key):
                    stale.append((group_index, tab_id))
                continue
            state = tab_states.get(tab_id, {})
            if state.get("title") != entry.name:
                retitled.append((tab_id, entry.name))
            tracks_now = new_index.tracks_by_artist.get(key)
            if previous_index is None or previous_index.tracks_by_artist.get(key) != tracks_now:
                reloaded.append(tab_id)

    return ArtistIndexEffects(
        opened_artist=opened,
        stale_tabs=stale,
        retitled_tabs=retitled,
        reloaded_tab_ids=reloaded,
    )


def format_artist_decision_message(
    credits: list[str],
    *,
    one_artist: bool,
) -> tuple[frozenset[str], str]:
    """Format confirmation message and normalized origin keys for an artist decision."""
    origins = frozenset(normalize_key(credit) for credit in credits)
    quoted = ", ".join("“" + credit + "”" for credit in credits)
    message = (
        f"Kept {quoted} as one artist." if one_artist else f"Split {quoted} into separate artists."
    )
    return origins, message


def sort_artist_tracks(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort tracks of an artist page: album, then track number, then title."""
    return sorted(tracks, key=album_track_order)


def prepare_artist_playback_rows(
    rows: list[Any],
    *,
    shuffled: bool,
) -> list[dict[str, Any]]:
    """Filter valid available tracks and optionally shuffle them for artist playback."""
    available = [dict(row) for row in rows if isinstance(row, dict) and row.get("id")]
    if shuffled:
        random.shuffle(available)
    return available
