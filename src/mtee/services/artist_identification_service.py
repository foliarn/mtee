"""Feed the artist review of a track from its tags and its file name.

The phase reads the tags of the file, builds a proposal and records it once. It writes
nothing to the file and never replaces the review of a track that already has one, so a
new analysis, forced or not, keeps every correction. A tag that cannot be read is an
error that can be retried, not an empty proposal.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from mtee.domain.artists import propose
from mtee.domain.tracks import SourceRevision
from mtee.persistence.artist_repository import ArtistRepository
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.metadata_reader import MetadataReader

__all__ = ["ArtistIdentificationService", "IdentificationResult"]


@dataclass(frozen=True, slots=True)
class IdentificationResult:
    """Outcome of the artist phase of one track."""

    track_id: str
    ok: bool
    created: bool = False
    message: str = ""


class ArtistIdentificationService:
    def __init__(
        self,
        library: LibraryRepository,
        repository: ArtistRepository,
        reader: MetadataReader | None = None,
    ) -> None:
        self._library = library
        self._repository = repository
        self._reader = reader or MetadataReader()

    def needs_identification(self, track_ids: Sequence[str]) -> set[str]:
        """Return the tracks that have no review row yet."""
        return set(self._repository.missing_reviews(list(track_ids)))

    def register_collection(self) -> list[str]:
        """Register every readable track of the library as the first cohort."""
        identities = self._repository.readable_track_ids()
        self._repository.workflow()
        self._repository.register_cohort(identities)
        return identities

    def identify_track(self, track_id: str) -> IdentificationResult:
        """Record the proposal of ``track_id`` unless it already has a review."""
        if self._repository.has_review(track_id):
            return IdentificationResult(track_id, True)
        record = self._library.source_record(track_id)
        if record is None:
            return IdentificationResult(
                track_id, False, message="The track is no longer in the library."
            )
        if record.status != "readable":
            return IdentificationResult(
                track_id, False, message="This audio file could not be read."
            )
        try:
            before = SourceRevision.observe(record.path)
            if not record.revision.matches(before):
                return IdentificationResult(
                    track_id, False, message="The file changed since its last scan. Scan it again."
                )
            snapshot = self._reader.read(record.path)
            after = SourceRevision.observe(record.path)
        except OSError as error:
            return IdentificationResult(track_id, False, message=f"{record.path.name}: {error}")
        if snapshot.status != "readable":
            return IdentificationResult(
                track_id, False, message=f"{record.path.name}: its tags could not be read."
            )
        if not before.matches(after):
            return IdentificationResult(
                track_id, False, message=f"{record.path.name}: the file changed while it was read."
            )
        proposal = propose(snapshot.artist, snapshot.title, record.path.stem)
        created = self._repository.ingest(
            track_id,
            proposal,
            revision=record.revision,
            original_artists=snapshot.artist,
            original_title=snapshot.title[0] if snapshot.title else "",
        )
        return IdentificationResult(track_id, True, created=created)
