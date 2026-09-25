"""Metadata writer for AAC and ALAC audio tracks in M4A/MP4 containers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mutagen import File as MutagenFile
from mutagen.mp4 import MP4, AtomDataType, MP4Cover, MP4FreeForm

from mtee.domain.metadata_edit import EDITABLE_METADATA_FIELDS, MetadataPatch

__all__ = ["MP4MetadataAdapter"]

_ATOMS = {
    "title": "\xa9nam",
    "artist": "\xa9ART",
    "album": "\xa9alb",
    "genre": "\xa9gen",
    "date": "\xa9day",
    "comment": "\xa9cmt",
    "track_number": "trkn",
    "bpm": "tmpo",
    "key": "----:com.apple.iTunes:initialkey",
}


@dataclass(frozen=True, slots=True)
class MP4PreservationSnapshot:
    """All MP4 atoms except those explicitly changed by the user's patch."""

    atoms: tuple[tuple[str, Any], ...]
    expected_changes: tuple[tuple[str, str | None], ...]


class MP4MetadataAdapter:
    """Edit one unambiguous value per supported iTunes atom in M4A audio."""

    reason_container = "Only AAC and ALAC audio tracks in M4A/MP4 are enabled for metadata writes."

    def supports_path(self, path: Any) -> bool:
        return Path(path).suffix.casefold() == ".m4a"

    def inspect(self, path: Any) -> tuple[Any, str]:
        audio = MutagenFile(path, easy=False)
        if not isinstance(audio, MP4) or audio.info is None:
            return audio, self.reason_container
        codec = str(getattr(audio.info, "codec", "")).casefold()
        if codec != "alac" and not codec.startswith("mp4a."):
            return audio, self.reason_container
        return audio, ""

    def capabilities(self, path: Any) -> dict[str, tuple[bool, str]]:
        if not self.supports_path(path):
            return self._disabled(self.reason_container)
        try:
            audio, reason = self.inspect(path)
        except Exception as error:
            return self._disabled(f"Could not inspect MP4 atoms: {type(error).__name__}.")
        if reason or audio is None:
            return self._disabled(reason or self.reason_container)
        tags = audio.tags or {}
        return {field: self._field_capability(tags, field) for field in EDITABLE_METADATA_FIELDS}

    def prepare(self, path: Any, patch: MetadataPatch) -> tuple[Any, MP4PreservationSnapshot]:
        audio, reason = self.inspect(path)
        if reason or audio is None:
            raise ValueError(reason or self.reason_container)
        if audio.tags is None:
            audio.add_tags()
        tags = audio.tags
        if tags is None:
            raise ValueError("Could not create the MP4 metadata atom table.")
        for field, _value in patch.changes:
            editable, reason = self._field_capability(tags, field)
            if not editable:
                raise ValueError(reason)
        expected_changes = tuple(
            (field, self._preserved_track_total(value, tags.get(_ATOMS[field])))
            if field == "track_number" and value is not None
            else (field, value)
            for field, value in patch.changes
        )
        preserved = self._snapshot(
            tags, {_ATOMS[field] for field, _ in patch.changes}, expected_changes
        )
        for field, value in expected_changes:
            atom = _ATOMS[field]
            if value is None:
                tags.pop(atom, None)
            elif field in {"title", "artist", "album", "genre", "date", "comment"}:
                tags[atom] = [value]
            elif field == "track_number":
                number, _, total = value.partition("/")
                tags[atom] = [(int(number), int(total) if total else 0)]
            elif field == "bpm":
                try:
                    bpm = int(value)
                except ValueError as error:
                    raise ValueError("M4A BPM must be a whole number.") from error
                if not 1 <= bpm <= 1000:
                    raise ValueError("M4A BPM must be between 1 and 1000.")
                tags[atom] = [bpm]
            elif field == "key":
                tags[atom] = [MP4FreeForm(value.encode("utf-8"), dataformat=AtomDataType.UTF8)]
        return audio, preserved

    @staticmethod
    def save(audio: Any, path: Any) -> None:
        audio.save()

    def verify(self, path: Any, expected: MP4PreservationSnapshot, patch: MetadataPatch) -> None:
        audio, reason = self.inspect(path)
        if reason or audio is None:
            raise ValueError(reason or "The saved MP4 atoms could not be read back.")
        tags = audio.tags or {}
        actual = self._snapshot(
            tags,
            {_ATOMS[field] for field, _value in patch.changes},
            expected.expected_changes,
        )
        if actual.atoms != expected.atoms:
            raise ValueError("An MP4 atom or cover outside the edited field changed during save.")
        for field, value in expected.expected_changes:
            values = self._field_values(tags, field)
            if value is None:
                if values:
                    raise ValueError(f"The {field} tag was not removed.")
            elif values != (value,):
                raise ValueError(f"The {field} tag did not match the requested value.")

    @classmethod
    def _field_capability(cls, tags: Any, field: str) -> tuple[bool, str]:
        values = tags.get(_ATOMS[field])
        if values is None or len(values) <= 1:
            return True, ""
        return False, f"{field.replace('_', ' ').title()} has multiple values; editing is disabled."

    @classmethod
    def _field_values(cls, tags: Any, field: str) -> tuple[str, ...]:
        values = tags.get(_ATOMS[field]) or []
        if field == "track_number":
            return tuple(
                f"{int(number)}/{int(total)}" if total else str(int(number))
                for number, total in values
            )
        if field == "bpm":
            return tuple(str(int(value)) for value in values)
        if field == "key":
            return tuple(_text(value) for value in values)
        return tuple(_text(value) for value in values)

    @staticmethod
    def _snapshot(
        tags: Any,
        excluded_atoms: set[str],
        expected_changes: tuple[tuple[str, str | None], ...],
    ) -> MP4PreservationSnapshot:
        atoms = tuple(
            sorted(
                (str(key), _freeze(value))
                for key, value in tags.items()
                if str(key) not in excluded_atoms
            )
        )
        return MP4PreservationSnapshot(atoms, expected_changes)

    @staticmethod
    def _preserved_track_total(value: str, previous: Any) -> str:
        if "/" in value or not previous:
            return value
        values = previous[0]
        if not isinstance(values, tuple) or len(values) < 2 or not values[1]:
            return value
        return f"{value}/{int(values[1])}"

    @staticmethod
    def _disabled(reason: str) -> dict[str, tuple[bool, str]]:
        return {field: (False, reason) for field in EDITABLE_METADATA_FIELDS}


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return str(value).strip()


def _freeze(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, MP4Cover):
        return "MP4Cover", bytes(value), int(value.imageformat)
    if isinstance(value, MP4FreeForm):
        return "MP4FreeForm", bytes(value), int(value.dataformat)
    if isinstance(value, dict):
        return tuple(sorted((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value
