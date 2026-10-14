"""Decisions of the artist manager: lists, corrections, lots and artist operations.

The service decides what a confirmation covers and freezes it; the files are written
afterwards by ``ArtistFileService``. Nothing here touches a file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mtee.domain.artists import CATEGORIES, normalize_key
from mtee.plugins.artist_manager.file_service import ArtistFileService
from mtee.plugins.artist_manager.profile import ArtistProfile
from mtee.plugins.artist_manager.repository import ArtistRepository, StageResult

__all__ = ["ArtistManagerError", "ArtistManagerService", "ConfirmationPreview"]


class ArtistManagerError(ValueError):
    """A request the manager refuses, with a sentence for the user."""


@dataclass(slots=True)
class ConfirmationPreview:
    """The frozen scope of a lot, as shown by the confirmation dialog."""

    category: str
    scope: str
    track_count: int = 0
    artist_count: int = 0
    items: list[tuple[str, int]] = field(default_factory=list)
    incomplete: list[str] = field(default_factory=list)
    examples: list[dict[str, str]] = field(default_factory=list)
    blocked: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "scope": self.scope,
            "trackCount": self.track_count,
            "artistCount": self.artist_count,
            "items": [[track_id, version] for track_id, version in self.items],
            "incompleteCount": len(self.incomplete),
            "incompleteIds": list(self.incomplete),
            "examples": self.examples,
            "blocked": self.blocked,
        }


class ArtistManagerService:
    def __init__(self, repository: ArtistRepository, files: ArtistFileService) -> None:
        self._repository = repository
        self._files = files

    @property
    def repository(self) -> ArtistRepository:
        return self._repository

    @property
    def files(self) -> ArtistFileService:
        return self._files

    # -------------------------------------------------------------------- state

    def state(self) -> dict[str, Any]:
        return self._repository.steps()

    # -------------------------------------------------------------------- lists

    def track_rows(self, category: str, search: str = "") -> list[dict[str, Any]]:
        rows = self._repository.review_rows(category=category)
        needle = normalize_key(search)
        if not needle:
            return rows
        return [row for row in rows if _matches(row, needle)]

    def artist_rows(self, category: str, search: str = "") -> list[dict[str, Any]]:
        artists = self._repository.category_artists(category)
        needle = normalize_key(search)
        if not needle:
            return artists
        return [artist for artist in artists if needle in normalize_key(artist["name"])]

    def suggestions(self, query: str) -> list[dict[str, Any]]:
        return self._repository.artist_names(query)

    # ----------------------------------------------------------------- the edit

    def edit_info(self, track_id: str) -> dict[str, Any]:
        row = self._repository.review(track_id)
        if row is None:
            return {}
        preview = self._files.preview_name(
            track_id, [credit["name"] for credit in row["credits"]], row["title"]
        )
        return {**row, "preview": preview}

    def preview_name(self, track_id: str, names: list[str], title: str) -> dict[str, Any]:
        return self._files.preview_name(track_id, names, title)

    def save_edit(
        self,
        track_id: str,
        title: str,
        entries: list[tuple[str, str]],
        *,
        to_needs_input: bool = False,
    ) -> dict[str, Any]:
        if self._repository.review(track_id) is None:
            raise ArtistManagerError("This track is not in the artist review.")
        version = self._repository.save_draft(
            track_id, title, entries, category="needs_input" if to_needs_input else ""
        )
        self._repository.reconsider_spellings()
        return {"version": version, **(self._repository.review(track_id) or {})}

    # ------------------------------------------------------------ confirmations

    def preview_confirmation(
        self, category: str, scope: str, search: str = ""
    ) -> ConfirmationPreview:
        """Freeze the tracks of the current filter: UUIDs and decision versions."""
        if category not in CATEGORIES:
            raise ArtistManagerError("Unknown category.")
        preview = ConfirmationPreview(category, scope)
        steps = self._repository.steps()
        info = steps["categories"][category]
        if not info["accessible"]:
            preview.blocked = "Finish the previous category first."
            return preview
        if steps["mode"] == "guided" and not steps["cohortReady"]:
            preview.blocked = (
                "The analysis of the collection is not finished."
                if steps["cohortRegistered"]
                else "Analyze the collection first."
            )
            return preview
        rows = {row["trackId"]: row for row in self.track_rows(category, "")}
        if scope == "artists":
            chosen: list[str] = []
            artists = self.artist_rows(category, search)
            preview.artist_count = len(artists)
            for artist in artists:
                chosen.extend(artist["trackIds"])
            track_ids = [track_id for track_id in dict.fromkeys(chosen) if track_id in rows]
        else:
            needle = normalize_key(search)
            track_ids = [
                track_id for track_id, row in rows.items() if not needle or _matches(row, needle)
            ]
        track_ids.sort(key=lambda track_id: rows[track_id]["filename"].casefold())
        for track_id in track_ids:
            row = rows[track_id]
            if row["incomplete"]:
                preview.incomplete.append(track_id)
            preview.items.append((track_id, row["version"]))
        preview.track_count = len(preview.items)
        for track_id in track_ids[:3]:
            row = rows[track_id]
            if not row["incomplete"]:
                name = self._files.preview_name(
                    track_id, [credit["name"] for credit in row["credits"]], row["title"]
                )
                preview.examples.append({"from": row["filename"], "to": name["name"]})
        return preview

    def stage(self, items: list[tuple[str, int]], *, write_tags: bool, label: str) -> StageResult:
        if not items:
            raise ArtistManagerError("There is nothing to confirm.")
        result = self._repository.stage_confirmation(items, write_tags=write_tags, label=label)
        if result.stale:
            raise ArtistManagerError(
                f"{len(result.stale)} tracks changed while the window was open. "
                "Open the confirmation again."
            )
        if result.incomplete:
            raise ArtistManagerError(
                f"{len(result.incomplete)} tracks still need an artist or a title. "
                "Edit them or move them to Needs input."
            )
        return result

    # --------------------------------------------------------- artist operations

    def impact(self, artist_id: str) -> dict[str, Any]:
        artist = self._repository.artist(artist_id)
        if artist is None:
            raise ArtistManagerError("This artist no longer exists.")
        return {
            "name": artist["name"],
            "confirmedTracks": len(self._repository.tracks_of_artist_confirmed(artist_id)),
        }

    def rename_artist(self, artist_id: str, name: str, *, write_tags: bool) -> dict[str, Any]:
        try:
            affected = self._repository.rename_artist(artist_id, name)
        except ValueError as error:
            raise ArtistManagerError(str(error)) from error
        operation_id = self._repository.queue_operation(
            "rename", f"Rename artist to {name}", affected, write_tags=write_tags
        )
        return {"operationId": operation_id, "tracks": len(affected)}

    def merge_artist(
        self, artist_id: str, destination_id: str, *, write_tags: bool
    ) -> dict[str, Any]:
        try:
            affected = self._repository.merge_artists(artist_id, destination_id)
        except ValueError as error:
            raise ArtistManagerError(str(error)) from error
        destination = self._repository.artist(destination_id)
        label = f"Merge into {destination['name']}" if destination else "Merge artists"
        operation_id = self._repository.queue_operation(
            "merge", label, affected, write_tags=write_tags
        )
        return {"operationId": operation_id, "tracks": len(affected)}

    def delete_artist(self, artist_id: str, *, remove_from_tags: bool) -> dict[str, Any]:
        artist = self._repository.artist(artist_id)
        try:
            affected = self._repository.delete_artist(artist_id)
        except ValueError as error:
            raise ArtistManagerError(str(error)) from error
        tags_only: list[str] = []
        queued: list[str] = []
        for track_id in affected:
            state = self._repository.confirmed_state(track_id)
            if state is not None and state["credits"] and state["reviewState"] == "confirmed":
                queued.append(track_id)
            elif remove_from_tags:
                tags_only.append(track_id)
                queued.append(track_id)
        operation_id = self._repository.queue_operation(
            "delete",
            f"Delete {artist['name']}" if artist else "Delete artist",
            queued,
            write_tags=remove_from_tags,
            tags_only=tags_only,
        )
        return {"operationId": operation_id, "tracks": len(affected)}

    # ------------------------------------------------------------------ catalog

    def catalog(self, search: str = "") -> list[dict[str, Any]]:
        needle = normalize_key(search)
        rows = self._repository.catalog()
        if not needle:
            return rows
        return [row for row in rows if needle in normalize_key(row["name"])]

    def artist_profile(self, artist_id: str) -> ArtistProfile:
        return self._repository.artist_profile(artist_id)

    def save_artist_profile(
        self,
        artist_id: str,
        *,
        roles: list[str],
        bass_related: bool | None,
        tags: list[str],
        hidden: bool,
    ) -> ArtistProfile:
        try:
            return self._repository.save_artist_profile(
                artist_id, roles=roles, bass_related=bass_related, tags=tags, hidden=hidden
            )
        except ValueError as error:
            raise ArtistManagerError(str(error)) from error


def _matches(row: dict[str, Any], needle: str) -> bool:
    haystack = normalize_key(f"{row['filename']} {row['title']} {row['artists']}")
    return needle in haystack
