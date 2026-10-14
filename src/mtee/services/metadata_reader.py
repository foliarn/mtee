"""Read common source tags and technical properties through Mutagen."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from mutagen import File as MutagenFile

from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo

__all__ = ["MetadataReader"]

_TAG_ALIASES = {
    "title": ("title", "TIT2"),
    "artist": ("artist", "TPE1"),
    "album": ("album", "TALB"),
    "genre": ("genre", "TCON"),
    "date": ("date", "year", "TDRC", "TYER"),
    "bpm": ("bpm", "tempo", "TBPM"),
    "key": ("initialkey", "key", "musickey", "TKEY"),
    "track_number": ("tracknumber", "track", "TRCK"),
    "comment": ("comment", "description", "COMM"),
}


class MetadataReader:
    """Read-only adapter; never calls a Mutagen save method."""

    def read(self, path: Path | str) -> MetadataSnapshot:
        source = Path(path)
        try:
            stat = source.stat()
            audio = MutagenFile(source, easy=True)
            if audio is None or audio.info is None:
                raise ValueError("Mutagen could not identify a supported audio stream.")
            tags = audio.tags or {}
            fields: dict[str, tuple[str, ...]] = {
                name: _read_values(tags, aliases) for name, aliases in _TAG_ALIASES.items()
            }
            if source.suffix.casefold() == ".m4a" and not fields["key"]:
                raw_tags = _read_raw_tags(source)
                fields["key"] = _read_mp4_initial_key(raw_tags)
            elif source.suffix.casefold() in {".wav", ".mp3", ".aif", ".aiff"}:
                if not fields["comment"] or not fields["key"]:
                    raw_tags = _read_raw_tags(source)
                    if not fields["comment"]:
                        fields["comment"] = _read_id3_comments(raw_tags)
                    if not fields["key"]:
                        fields["key"] = _read_id3_frame_text(raw_tags, "TKEY")
            info = audio.info
            duration = getattr(info, "length", None)
            technical = TechnicalInfo(
                duration_us=round(float(duration) * 1_000_000) if duration is not None else None,
                container=source.suffix.removeprefix(".").upper(),
                codec=type(audio).__name__,
                bitrate=_optional_int(getattr(info, "bitrate", None)),
                sample_rate=_optional_int(getattr(info, "sample_rate", None)),
                bits_per_sample=_optional_int(getattr(info, "bits_per_sample", None)),
                size_bytes=stat.st_size,
            )
            return MetadataSnapshot(
                title=fields["title"],
                artist=fields["artist"],
                album=fields["album"],
                genre=fields["genre"],
                date=fields["date"],
                bpm=fields["bpm"],
                key=fields["key"],
                track_number=fields["track_number"],
                comment=fields["comment"],
                technical=technical,
            )
        except Exception as error:
            # Mutagen raises many unrelated types on malformed files.
            try:
                size = source.stat().st_size
            except OSError:
                size = 0
            return MetadataSnapshot(
                technical=TechnicalInfo(
                    container=source.suffix.removeprefix(".").upper(), size_bytes=size
                ),
                status="unreadable",
                error=f"{type(error).__name__}: {error}",
            )


def _read_values(tags: Any, aliases: tuple[str, ...]) -> tuple[str, ...]:
    for key in aliases:
        try:
            value = tags.get(key)
        except (AttributeError, TypeError):
            return ()
        if value is None:
            continue
        text = getattr(value, "text", value)
        values = text if isinstance(text, (list, tuple)) else (text,)
        result = tuple(str(item).strip() for item in values if str(item).strip())
        if result:
            return result
    return ()


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        result = int(str(value))
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result > 0 else None


def _read_raw_tags(path: Path) -> Any:
    audio = MutagenFile(path, easy=False)
    return getattr(audio, "tags", None)


def _read_mp4_initial_key(tags: Any) -> tuple[str, ...]:
    """Read iTunes' freeform initialkey atom, which Mutagen's EasyMP4 omits."""
    if tags is None:
        return ()
    values = tags.get("----:com.apple.iTunes:initialkey", ())
    return tuple(text for value in values if (text := _decode_tag_value(value)).strip())


def _read_id3_comments(tags: Any) -> tuple[str, ...]:
    """Read COMM frames where Mutagen's easy reader does not expose the alias."""
    getall = getattr(tags, "getall", None)
    if not callable(getall):
        return ()
    frames = cast(Any, getall("COMM"))
    return tuple(
        str(item).strip()
        for frame in frames
        for item in getattr(frame, "text", ())
        if str(item).strip()
    )


def _read_id3_frame_text(tags: Any, frame_id: str) -> tuple[str, ...]:
    getall = getattr(tags, "getall", None)
    if not callable(getall):
        return ()
    frames = cast(Any, getall(frame_id))
    return tuple(
        str(item).strip()
        for frame in frames
        for item in getattr(frame, "text", ())
        if str(item).strip()
    )


def _decode_tag_value(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    data = getattr(value, "data", None)
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(value)
