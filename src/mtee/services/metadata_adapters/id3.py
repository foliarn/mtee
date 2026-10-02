"""Conservative ID3 writer for verified WAV, MP3, and AIFF containers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mutagen import File as MutagenFile
from mutagen.aiff import AIFF
from mutagen.id3 import COMM, ID3, TALB, TBPM, TCON, TDRC, TIT2, TKEY, TPE1, TRCK, TYER
from mutagen.mp3 import MP3
from mutagen.wave import WAVE

from mtee.domain.metadata_edit import EDITABLE_METADATA_FIELDS, MetadataPatch

__all__ = ["Id3WaveAdapter"]

_LABELS = {
    "title": "Title",
    "artist": "Artist",
    "album": "Album",
    "genre": "Genre",
    "date": "Date",
    "comment": "Comment",
    "track_number": "Track number",
    "bpm": "BPM",
    "key": "Key",
}
_FRAME_TYPES = {
    "title": TIT2,
    "artist": TPE1,
    "album": TALB,
    "genre": TCON,
    "bpm": TBPM,
    "key": TKEY,
    "track_number": TRCK,
}
_FIELD_FRAMES = {
    "title": frozenset({"TIT2"}),
    "artist": frozenset({"TPE1"}),
    "album": frozenset({"TALB"}),
    "genre": frozenset({"TCON"}),
    "date": frozenset({"TDRC"}),
    "bpm": frozenset({"TBPM"}),
    "key": frozenset({"TKEY"}),
    "track_number": frozenset({"TRCK"}),
}


@dataclass(frozen=True, slots=True)
class Id3PreservationSnapshot:
    """Serialized untouched frames and parser-unknown ID3 frames."""

    frames: tuple[tuple[str, bytes], ...]
    unknown_frames: tuple[bytes, ...]
    expected_changes: tuple[tuple[str, str | None], ...]


class Id3WaveAdapter:
    """ID3 adapter for PCM WAV v2.4, MP3 v2.3/v2.4, and PCM AIFF."""

    reason_unverified = "Writing has not been verified for this audio format."
    reason_wave_encoding = "Only PCM WAV files have been verified for metadata writes."
    reason_aiff_encoding = (
        "Only uncompressed AIFF PCM files have been verified for metadata writes."
    )
    reason_container = "This file's inspected audio container does not match its extension."
    reason_id3_version = "Only ID3v2.3 and ID3v2.4 tags are enabled for this container."
    reason_v23_date = "ID3v2.3 Date editing is disabled; the Mutagen round-trip is ambiguous."

    def supports_path(self, path: Any) -> bool:
        return str(path).casefold().endswith((".wav", ".mp3", ".aif", ".aiff"))

    def inspect(self, path: Any) -> tuple[Any, str]:
        source = str(path).casefold()
        audio = MutagenFile(path, easy=False)
        if audio is None or audio.info is None:
            return audio, self.reason_container
        if source.endswith(".wav") and isinstance(audio, WAVE):
            if audio.info.audio_format != 1:
                return audio, self.reason_wave_encoding
        elif not (
            (source.endswith(".mp3") and isinstance(audio, MP3))
            or (source.endswith((".aif", ".aiff")) and isinstance(audio, AIFF))
        ):
            return audio, self.reason_container
        elif source.endswith((".aif", ".aiff")):
            with open(path, "rb") as stream:
                header = stream.read(12)
            if len(header) != 12 or header[:4] != b"FORM" or header[8:12] != b"AIFF":
                return audio, self.reason_aiff_encoding
        if audio.tags is None:
            return audio, ""
        if not isinstance(audio.tags, ID3):
            return audio, "This container uses tags that are not safe to replace."
        version = audio.tags.version
        if len(version) < 2 or version[0] != 2 or version[1] not in {3, 4}:
            return audio, self.reason_id3_version
        if isinstance(audio, WAVE) and version[1] != 4:
            return audio, self.reason_id3_version
        return audio, ""

    def save(self, audio: Any, path: Any) -> None:
        """Save using the source ID3 version; WAV keeps its established v1 policy."""
        version = 4
        if isinstance(audio.tags, ID3) and len(audio.tags.version) > 1:
            version = audio.tags.version[1]
        if isinstance(audio, WAVE):
            audio.save(v2_version=4, v1=1)
        else:
            audio.save(v2_version=version)

    def capabilities(
        self, path: Any, *, replace_aliases: bool = False
    ) -> dict[str, tuple[bool, str]]:
        if not self.supports_path(path):
            return {field: (False, self.reason_unverified) for field in EDITABLE_METADATA_FIELDS}
        audio: WAVE | None = None
        try:
            audio, reason = self.inspect(path)
        except Exception as error:
            reason = f"Could not inspect the source tags: {type(error).__name__}."
        if reason:
            return {field: (False, reason) for field in EDITABLE_METADATA_FIELDS}
        if audio is None:
            return {field: (False, self.reason_unverified) for field in EDITABLE_METADATA_FIELDS}
        tags = audio.tags
        version = audio.tags.version[1] if audio.tags is not None else 4
        capabilities = {
            field: self._field_capability(tags, field, version, replace_aliases)
            for field in EDITABLE_METADATA_FIELDS
        }
        return capabilities

    def prepare(self, path: Any, patch: MetadataPatch) -> tuple[Any, Id3PreservationSnapshot]:
        audio, reason = self.inspect(path)
        if reason:
            raise ValueError(reason)
        if audio.tags is None:
            audio.add_tags()
        assert isinstance(audio.tags, ID3)
        tags = audio.tags
        for field, _value in patch.changes:
            editable, reason = self._field_capability(
                tags, field, tags.version[1], patch.replace_aliases
            )
            if not editable:
                raise ValueError(reason)
        preserved = self._preserved_snapshot(tags, patch)
        self._apply(tags, patch)
        return audio, preserved

    @staticmethod
    def _field_capability(
        tags: ID3 | None, field: str, version: int | None = None, replace: bool = False
    ) -> tuple[bool, str]:
        if tags is None or (replace and field in {"artist", "title"}):
            return True, ""
        if field == "date" and version == 3:
            return False, Id3WaveAdapter.reason_v23_date
        if field == "comment":
            comments = tags.getall("COMM")
            default = [
                frame
                for frame in comments
                if frame.lang.casefold() in {"eng", "xxx"} and frame.desc == ""
            ]
            if not comments or (len(comments) == 1 and len(default) == 1):
                return True, ""
        elif field == "date" and "TDRC" in tags and "TYER" in tags:
            pass
        else:
            frame_ids = _FIELD_FRAMES[field]
            frames = [frame for frame_id in frame_ids for frame in tags.getall(frame_id)]
            if len(frames) <= 1 and (not frames or len(frames[0].text) <= 1):
                return True, ""
        return (
            False,
            "This tag has multiple values or slots; editing is disabled to preserve them.",
        )

    def verify(self, path: Any, expected: Id3PreservationSnapshot, patch: MetadataPatch) -> None:
        audio, reason = self.inspect(path)
        if reason or not isinstance(audio.tags, ID3):
            raise ValueError(reason or "The saved ID3 tag could not be read back.")
        actual = self._preserved_snapshot(audio.tags, patch)
        if actual.frames != expected.frames or actual.unknown_frames != expected.unknown_frames:
            raise ValueError("An ID3 frame outside the edited field changed during save.")
        self._verify_changed_fields(audio.tags, expected.expected_changes)

    @staticmethod
    def _validate_patch(tags: ID3, patch: MetadataPatch) -> None:
        for field, _value in patch.changes:
            if field == "date" and "TDRC" in tags and "TYER" in tags:
                raise ValueError("Both TDRC and TYER exist; Date editing is ambiguous.")
            if field == "comment":
                matching = [
                    frame
                    for frame in tags.getall("COMM")
                    if frame.lang.casefold() in {"eng", "xxx"} and frame.desc == ""
                ]
                if len(matching) > 1:
                    raise ValueError(
                        "Multiple default comments exist; Comment editing is ambiguous."
                    )

    @staticmethod
    def _apply(tags: ID3, patch: MetadataPatch) -> None:
        for field, value in patch.changes:
            if field == "date":
                version = tags.version[1] if len(tags.version) > 1 else 4
                frame_id = "TDRC" if version >= 4 else "TYER"
                frame_type = TDRC if frame_id == "TDRC" else TYER
            elif field == "comment":
                existing = [
                    frame
                    for frame in tags.getall("COMM")
                    if frame.lang.casefold() in {"eng", "xxx"} and frame.desc == ""
                ]
                if value is None:
                    if existing:
                        del tags[existing[0].HashKey]
                    continue
                if existing:
                    existing[0].text = [value]
                    continue
                tags.add(COMM(encoding=3, lang="eng", desc="", text=[value]))
                continue
            else:
                frame_ids = _FIELD_FRAMES[field]
                frame_id = next(
                    (candidate for candidate in frame_ids if candidate in tags),
                    next(iter(frame_ids)),
                )
                frame_type = _FRAME_TYPES[field]
            if value is None:
                if frame_id in tags:
                    del tags[frame_id]
                continue
            if field == "track_number":
                value = _preserve_track_total(value, tags.get("TRCK"))
            tags.add(frame_type(encoding=3, text=[value]))

    @staticmethod
    def _preserved_snapshot(tags: ID3, patch: MetadataPatch) -> Id3PreservationSnapshot:
        excluded: set[str] = set()
        for field, _value in patch.changes:
            if field == "comment":
                excluded.add("COMM::eng")
                excluded.add("COMM::xxx")
            elif field == "date":
                version = tags.version[1] if len(tags.version) > 1 else 4
                excluded.add("TDRC" if version >= 4 else "TYER")
            else:
                excluded.update(_FIELD_FRAMES[field])
        frames = tuple(
            sorted(
                (str(frame.HashKey), bytes(frame._writeData()))
                for frame in tags.values()
                if not any(
                    str(frame.HashKey) == key or str(frame.HashKey).startswith(f"{key}:")
                    for key in excluded
                )
            )
        )
        unknown = tuple(sorted(bytes(frame) for frame in tags.unknown_frames))
        expected_changes = tuple(
            (
                field,
                _preserve_track_total(value, tags.get("TRCK"))
                if field == "track_number" and value is not None
                else value,
            )
            for field, value in patch.changes
        )
        return Id3PreservationSnapshot(
            frames=frames,
            unknown_frames=unknown,
            expected_changes=expected_changes,
        )

    @staticmethod
    def _verify_changed_fields(
        tags: ID3, expected_changes: tuple[tuple[str, str | None], ...]
    ) -> None:
        for field, value in expected_changes:
            if field == "comment":
                current = [
                    frame
                    for frame in tags.getall("COMM")
                    if frame.lang.casefold() in {"eng", "xxx"} and frame.desc == ""
                ]
                values = [str(item) for item in current[0].text] if current else []
            else:
                frame_ids = _FIELD_FRAMES[field]
                values = [
                    str(item)
                    for frame_id in frame_ids
                    for frame in tags.getall(frame_id)
                    for item in frame.text
                ]
                if field == "date" and not values:
                    values = [str(item) for frame in tags.getall("TYER") for item in frame.text]
            if value is None:
                if values:
                    raise ValueError(f"The {field} tag was not removed.")
            elif values != [value]:
                raise ValueError(f"The {field} tag did not match the requested value.")


def _preserve_track_total(value: str, existing: object) -> str:
    if "/" in value or existing is None:
        return value
    values = getattr(existing, "text", [])
    if not values:
        return value
    previous = str(values[0])
    if "/" not in previous:
        return value
    _number, total = previous.split("/", maxsplit=1)
    return f"{value}/{total}"
