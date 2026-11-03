"""What a recycle request made by a plugin (plan 125.4) reports back."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["RecycleFailure", "RecycleOutcome"]


@dataclass(frozen=True, slots=True)
class RecycleFailure:
    """A track whose file stayed where it is, and the reason, in words the user can read."""

    track_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class RecycleOutcome:
    """The tracks that went to the Windows Recycle Bin and the ones that did not."""

    recycled: tuple[str, ...] = ()
    failed: tuple[RecycleFailure, ...] = ()
