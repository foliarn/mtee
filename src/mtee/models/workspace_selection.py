"""Pure selection arithmetic, track resolution and info field formatting."""

from __future__ import annotations

from typing import Any

__all__ = [
    "calculate_selection",
    "format_info_fields_read_only",
    "format_info_file_fields",
    "resolve_local_track_ids",
]

_INFO_READ_ONLY_FIELDS = (
    ("Title", "title"),
    ("Artist", "artist"),
    ("Album", "album"),
    ("Genre", "genre"),
    ("Date", "year"),
    ("BPM", "bpmText"),
    ("Key", "key"),
    ("Track number", "trackNumber"),
    ("Comment", "comment"),
)

_INFO_FILE_FIELDS = (
    ("Duration", "duration"),
    ("Format", "format"),
    ("Codec", "codec"),
    ("Bitrate", "bitrateText"),
    ("Sample rate", "sampleRate"),
    ("Size", "size"),
    ("Date created", "fileCreatedAtText"),
    ("Date modified", "fileModifiedAtText"),
    ("Filename", "filename"),
    ("Path", "path"),
)


def calculate_selection(
    current_selected: list[str],
    current_anchor: str,
    track_id: str,
    mode: str = "single",
    ordered: list[Any] | None = None,
) -> tuple[list[str], str]:
    """Calculate the new selection list and anchor based on selection mode.

    Returns:
        (new_selected, new_anchor)
    """
    selected = list(current_selected)
    anchor = current_anchor
    if mode == "toggle":
        if track_id in selected:
            selected.remove(track_id)
        else:
            selected.append(track_id)
            anchor = track_id
    elif mode == "range" and ordered:
        start = anchor if anchor in ordered else (selected[-1] if selected else track_id)
        try:
            start_index = ordered.index(start)
            target_index = ordered.index(track_id)
            first, last = sorted((start_index, target_index))
            selected = [str(item) for item in ordered[first : last + 1]]
            anchor = start
        except ValueError:
            selected = [track_id]
            anchor = track_id
    else:
        selected = [track_id]
        anchor = track_id
    return selected, anchor


def resolve_local_track_ids(
    identities: list[Any],
    track_rows: list[dict[str, Any]] | None,
) -> list[str]:
    """Resolve selection identities to track IDs, handling playlist entry IDs."""
    lookup = (
        {r["id"]: r.get("trackId", r["id"]) for r in track_rows}
        if track_rows
        else {}
    )
    playlist = bool(track_rows and any("entryId" in r for r in track_rows))
    lookup.update({identity: identity for identity in lookup.values() if identity})
    return list(
        dict.fromkeys(
            str(lookup.get(i, "" if playlist else i))
            for i in identities
            if lookup.get(i, "" if playlist else i)
        )
    )


def format_info_fields_read_only(track: dict[str, Any]) -> list[dict[str, str]]:
    """Format single track metadata fields for the read-only inspection panel."""
    return [
        {"label": label, "value": str(track.get(key, "") or "—")}
        for label, key in _INFO_READ_ONLY_FIELDS
        if track.get(key, "")
    ]


def format_info_file_fields(track: dict[str, Any]) -> list[dict[str, str]]:
    """Format single track file technical details for the inspection panel."""
    return [
        {"label": label, "value": str(track.get(key, "") or "—")}
        for label, key in _INFO_FILE_FIELDS
    ]
