"""Pure transitions for ordered, explicit track genres."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


class GenreConflictError(ValueError):
    """A requested genre would make the track's explicit choices ambiguous."""


def ancestor_of(ancestor: str, descendant: str, parents: Mapping[str, str | None]) -> bool:
    """Return whether ``ancestor`` is above ``descendant`` in a valid tree."""
    seen: set[str] = set()
    current = parents.get(descendant)
    while current is not None:
        if current in seen:
            raise GenreConflictError("Genre hierarchy contains a cycle")
        if current == ancestor:
            return True
        seen.add(current)
        current = parents.get(current)
    return False


def add_genre(
    current: Sequence[str], genre_id: str, parents: Mapping[str, str | None]
) -> tuple[str, ...]:
    """Append a genre, or replace an explicit ancestor in the same position."""
    if genre_id not in parents:
        raise GenreConflictError("Unknown genre")
    ordered = tuple(current)
    if genre_id in ordered:
        return ordered
    for assigned in ordered:
        if ancestor_of(genre_id, assigned, parents):
            return ordered  # An explicit descendant already says more.
    ancestors = [
        index for index, assigned in enumerate(ordered) if ancestor_of(assigned, genre_id, parents)
    ]
    if len(ancestors) > 1:
        raise GenreConflictError("Track has redundant ancestor assignments")
    if ancestors:
        index = ancestors[0]
        return (*ordered[:index], genre_id, *ordered[index + 1 :])
    return (*ordered, genre_id)


def remove_genre(current: Sequence[str], genre_id: str) -> tuple[str, ...]:
    """Remove only an explicit assignment; the next secondary becomes primary."""
    return tuple(assigned for assigned in current if assigned != genre_id)


def make_primary(current: Sequence[str], genre_id: str) -> tuple[str, ...]:
    """Promote an existing assignment without changing the other order."""
    ordered = tuple(current)
    if genre_id not in ordered:
        raise GenreConflictError("Genre is not assigned to this track")
    return (genre_id, *(item for item in ordered if item != genre_id))


def validate_order(current: Sequence[str], parents: Mapping[str, str | None]) -> tuple[str, ...]:
    """Refuse duplicates and explicit ancestor/descendant pairs."""
    ordered = tuple(current)
    if len(ordered) != len(set(ordered)):
        raise GenreConflictError("Duplicate genre assignment")
    for index, genre_id in enumerate(ordered):
        if genre_id not in parents:
            raise GenreConflictError("Unknown genre")
        for other in ordered[index + 1 :]:
            if ancestor_of(genre_id, other, parents) or ancestor_of(other, genre_id, parents):
                raise GenreConflictError("A genre and its ancestor cannot both be assigned")
    return ordered
