"""Preserving writer for FLAC, Ogg/Vorbis, and Ogg/Opus comments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mutagen import File as MutagenFile
from mutagen.flac import FLAC
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis

from mtee.domain.metadata_edit import EDITABLE_METADATA_FIELDS, MetadataPatch

__all__ = ["VorbisCommentAdapter"]

_ALIASES = {
    "title": ("title",),
    "artist": ("artist",),
    "album": ("album",),
    "genre": ("genre",),
    "date": ("date", "year"),
    "comment": ("comment", "description"),
    "track_number": ("tracknumber", "track"),
    "bpm": ("bpm", "tempo"),
    "key": ("initialkey", "key", "musickey"),
}


@dataclass(frozen=True, slots=True)
class VorbisPreservationSnapshot:
    """All comments and picture payloads outside the fields being changed."""

    comments: tuple[tuple[str, Any], ...]
    pictures: tuple[Any, ...]
    expected_changes: tuple[tuple[str, str | None], ...]


class VorbisCommentAdapter:
    """Enable fields whose comments have a single safe slot in these containers."""

    reason_container = (
        "The inspected codec/container is not a supported FLAC, Vorbis, or Opus stream."
    )

    def supports_path(self, path: Any) -> bool:
        return Path(path).suffix.casefold() in {".flac", ".ogg", ".opus"}

    def inspect(self, path: Any) -> tuple[Any, str]:
        source = Path(path)
        audio = MutagenFile(source, easy=False)
        if audio is None or audio.info is None:
            return audio, self.reason_container
        expected = {
            ".flac": FLAC,
            ".ogg": OggVorbis,
            ".opus": OggOpus,
        }.get(source.suffix.casefold())
        if expected is None or not isinstance(audio, expected):
            return audio, self.reason_container
        return audio, ""

    def alias_conflicts(self, path: Any, fields: Any) -> dict[str, tuple[str, ...]]:
        """Return, per field, the tag names that make it unsafe to edit in place.

        A field is in conflict when it exists under several names (``KEY`` and
        ``INITIALKEY``) or holds several values under one name.
        """
        try:
            audio, reason = self.inspect(path)
        except Exception:
            return {}
        if reason or audio is None:
            return {}
        tags = audio.tags or {}
        found: dict[str, tuple[str, ...]] = {}
        for field in fields:
            if field not in _ALIASES:
                continue
            keys = self._matching_keys(tags, field)
            if len(keys) > 1:
                found[field] = tuple(key.upper() for key in keys)
            elif keys:
                values = _as_values(tags[keys[0]])
                if len(values) > 1:
                    found[field] = (f"{keys[0].upper()} ({len(values)} values)",)
        return found

    def capabilities(
        self, path: Any, *, replace_aliases: bool = False
    ) -> dict[str, tuple[bool, str]]:
        if not self.supports_path(path):
            return self._disabled(self.reason_container)
        try:
            audio, reason = self.inspect(path)
        except Exception as error:
            return self._disabled(f"Could not inspect source comments: {type(error).__name__}.")
        if reason or audio is None:
            return self._disabled(reason or self.reason_container)
        tags = audio.tags or {}
        return {
            field: self._field_capability(tags, field, replace_aliases)
            for field in EDITABLE_METADATA_FIELDS
        }

    def prepare(self, path: Any, patch: MetadataPatch) -> tuple[Any, VorbisPreservationSnapshot]:
        audio, reason = self.inspect(path)
        if reason or audio is None:
            raise ValueError(reason or self.reason_container)
        if audio.tags is None:
            audio.add_tags()
        tags = audio.tags
        if tags is None:
            raise ValueError("Could not create the Vorbis comment table.")
        target_keys: dict[str, str] = {}
        old_keys: dict[str, list[str]] = {}
        for field, _value in patch.changes:
            editable, reason = self._field_capability(tags, field, patch.replace_aliases)
            if not editable:
                raise ValueError(reason)
            old_keys[field] = self._matching_keys(tags, field)
            # Replacing aliases stores the value under the first standard name.
            target_keys[field] = (
                _ALIASES[field][0] if patch.replace_aliases else self._resolve_key(tags, field)
            )
        expected_changes = tuple(
            (
                field,
                _preserve_track_total(
                    value,
                    tags.get(old_keys[field][0] if old_keys[field] else target_keys[field]),
                ),
            )
            if field == "track_number" and value is not None
            else (field, value)
            for field, value in patch.changes
        )
        touched = set(target_keys.values()).union(*old_keys.values())
        preserved = self._snapshot(audio, touched, expected_changes)
        if patch.replace_aliases:
            for keys in old_keys.values():
                for key in keys:
                    if key in tags:
                        del tags[key]
        for field, value in patch.changes:
            key = target_keys[field]
            if value is None:
                if key in tags:
                    del tags[key]
            elif field == "track_number":
                tags[key] = [dict(expected_changes)[field]]
            else:
                tags[key] = [value]
        return audio, preserved

    @staticmethod
    def save(audio: Any, path: Any) -> None:
        audio.save()

    def verify(self, path: Any, expected: VorbisPreservationSnapshot, patch: MetadataPatch) -> None:
        audio, reason = self.inspect(path)
        if reason or audio is None:
            raise ValueError(reason or "The saved audio comments could not be read back.")
        actual = self._snapshot(
            audio,
            {self._resolve_key(audio.tags or {}, field) for field, _value in patch.changes},
            expected.expected_changes,
        )
        if actual.comments != expected.comments or actual.pictures != expected.pictures:
            raise ValueError("A comment, unknown tag, or picture outside the edited field changed.")
        tags = audio.tags or {}
        for field, value in expected.expected_changes:
            values = self._field_values(tags, field)
            if value is None:
                if values:
                    raise ValueError(f"The {field} tag was not removed.")
            elif values != (value,):
                raise ValueError(f"The {field} tag did not match the requested value.")

    @classmethod
    def _field_capability(
        cls, tags: Any, field: str, replace_aliases: bool = False
    ) -> tuple[bool, str]:
        if replace_aliases:
            return True, ""
        keys = cls._matching_keys(tags, field)
        if len(keys) > 1:
            return (
                False,
                f"{field.replace('_', ' ').title()} has multiple tag aliases; editing is disabled.",
            )
        if keys and len(_as_values(tags[keys[0]])) > 1:
            return (
                False,
                f"{field.replace('_', ' ').title()} has multiple values; editing is disabled.",
            )
        return True, ""

    @staticmethod
    def _matching_keys(tags: Any, field: str) -> list[str]:
        aliases = {value.casefold() for value in _ALIASES[field]}
        # Mutagen VorbisComment iterates (key, value) pairs, so .keys() is required here.
        return [str(key) for key in tags.keys() if str(key).casefold() in aliases]  # noqa: SIM118

    @classmethod
    def _resolve_key(cls, tags: Any, field: str) -> str:
        matches = cls._matching_keys(tags, field)
        return matches[0] if matches else _ALIASES[field][0]

    @classmethod
    def _field_values(cls, tags: Any, field: str) -> tuple[str, ...]:
        keys = cls._matching_keys(tags, field)
        if not keys:
            return ()
        return tuple(
            str(value).strip() for value in _as_values(tags[keys[0]]) if str(value).strip()
        )

    @classmethod
    def _snapshot(
        cls,
        audio: Any,
        excluded_keys: set[str],
        expected_changes: tuple[tuple[str, str | None], ...],
    ) -> VorbisPreservationSnapshot:
        tags = audio.tags or {}
        excluded = {key.casefold() for key in excluded_keys}
        comments = tuple(
            sorted(
                (str(key), _freeze(value))
                for key, value in tags.items()
                if str(key).casefold() not in excluded
            )
        )
        pictures = tuple(_picture_data(item) for item in getattr(audio, "pictures", ()))
        return VorbisPreservationSnapshot(comments, pictures, expected_changes)

    @staticmethod
    def _disabled(reason: str) -> dict[str, tuple[bool, str]]:
        return {field: (False, reason) for field in EDITABLE_METADATA_FIELDS}


def _as_values(value: Any) -> tuple[Any, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return (value,)


def _preserve_track_total(value: str, previous: Any) -> str:
    if "/" in value or previous is None:
        return value
    values = _as_values(previous)
    if not values or "/" not in str(values[0]):
        return value
    _number, total = str(values[0]).split("/", maxsplit=1)
    return f"{value}/{total}"


def _freeze(value: Any) -> Any:
    if isinstance(value, bytes):
        return value
    if isinstance(value, dict):
        return tuple(sorted((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if hasattr(value, "data") and isinstance(value.data, bytes):
        return type(value).__name__, bytes(value.data)
    return value


def _picture_data(picture: Any) -> tuple[Any, ...]:
    return (
        int(picture.type),
        str(picture.mime),
        str(picture.desc),
        int(picture.width),
        int(picture.height),
        int(picture.depth),
        bytes(picture.data),
    )
