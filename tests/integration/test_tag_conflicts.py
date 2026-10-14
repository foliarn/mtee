"""A field stored under several tag names is replaced only on request, and only that field."""

from __future__ import annotations

from pathlib import Path

import pytest
from mutagen.flac import FLAC, Picture, VCFLACDict
from tests.helpers.analysis_audio import drum_loop, key_progression, write_wav
from tests.helpers.analysis_library import RATE, AnalysisLibrary, require_ffmpeg

from mtee.domain.analysis import AnalysisSettings
from mtee.domain.metadata_edit import MetadataPatch
from mtee.domain.tracks import sha256_of_file
from mtee.services.analysis_service import bpm_tag_text
from mtee.services.ffmpeg_runtime import FfmpegRuntime
from mtee.services.metadata_adapters.vorbis import VorbisCommentAdapter

_PICTURE = b"\x89PNG\r\n\x1a\n" + b"not a real image, only bytes to preserve"


@pytest.fixture
def library(tmp_path: Path):
    require_ffmpeg()
    fixture = AnalysisLibrary(tmp_path)
    yield fixture
    fixture.close()


def _flac_with_aliases(library: AnalysisLibrary, name: str = "duplicates.flac") -> tuple[str, Path]:
    """Return a catalogued FLAC that stores its key and tempo under two names each."""
    source = library.base / "work" / "source.wav"
    signal = 0.5 * key_progression(9, True, 30, rate=RATE) + 0.6 * drum_loop(126.0, 30, rate=RATE)
    write_wav(source, signal, RATE)
    path = library.base / "music" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = FfmpegRuntime().run("ffmpeg", ["-y", "-i", str(source), str(path)])
    assert encoded.returncode == 0, encoded.stderr
    audio = FLAC(path)
    assert audio.tags is not None or audio.add_tags() is None
    audio["title"] = "Duplicate tags"
    audio["artist"] = "Somebody"
    audio["key"] = "Gm"
    audio["initialkey"] = "1A"
    audio["bpm"] = "100"
    audio["tempo"] = "101"
    audio["mytag"] = "keep me"
    picture = Picture()
    picture.type = 3
    picture.mime = "image/png"
    picture.data = _PICTURE
    audio.add_picture(picture)
    audio.save()
    return library.register(name), path


def _tags(path: Path) -> dict[str, list[str]]:
    tags = FLAC(path).tags
    assert isinstance(tags, VCFLACDict)
    return {key.casefold(): list(values) for key, values in tags.items()}


def test_the_adapter_reports_the_conflicting_fields_and_can_replace_them(
    library: AnalysisLibrary,
) -> None:
    _track_id, path = _flac_with_aliases(library)
    adapter = VorbisCommentAdapter()

    conflicts = adapter.alias_conflicts(path, ("key", "bpm", "title", "date"))

    assert set(conflicts) == {"key", "bpm"}
    assert set(conflicts["key"]) == {"KEY", "INITIALKEY"}
    assert set(conflicts["bpm"]) == {"BPM", "TEMPO"}
    assert adapter.capabilities(path)["key"][0] is False
    assert "multiple tag aliases" in adapter.capabilities(path)["key"][1]
    assert adapter.capabilities(path, replace_aliases=True)["key"][0] is True


def test_a_field_with_several_values_is_also_a_conflict(library: AnalysisLibrary) -> None:
    _track_id, path = _flac_with_aliases(library)
    audio = FLAC(path)
    del audio["key"]
    audio["initialkey"] = ["1A", "2A"]
    audio.save()

    conflicts = VorbisCommentAdapter().alias_conflicts(path, ("key",))

    assert conflicts == {"key": ("INITIALKEY (2 values)",)}


def test_the_writer_refuses_by_default_and_replaces_every_old_value_on_request(
    library: AnalysisLibrary,
) -> None:
    track_id, path = _flac_with_aliases(library)
    revision = library.library.source_record(track_id).revision  # type: ignore[union-attr]
    before_md5 = FLAC(path).info.md5_signature

    refused = library.writer.save(track_id, revision, MetadataPatch.one("key", "8A"), "draft-1")
    assert refused.status == "unsupported"
    assert "multiple tag aliases" in refused.message
    assert _tags(path)["key"] == ["Gm"]

    saved = library.writer.save(
        track_id, revision, MetadataPatch.one("key", "8A", replace_aliases=True), "draft-2"
    )

    assert saved.status == "saved", saved.message
    tags = _tags(path)
    assert tags["initialkey"] == ["8A"]  # the new value, under the first standard name
    assert "key" not in tags  # the old names and values are gone
    assert tags["bpm"] == ["100"] and tags["tempo"] == ["101"]  # other fields are untouched
    assert tags["title"] == ["Duplicate tags"] and tags["artist"] == ["Somebody"]
    assert tags["mytag"] == ["keep me"]  # unknown tags are preserved
    audio = FLAC(path)
    assert [item.data for item in audio.pictures] == [_PICTURE]
    assert audio.info.md5_signature == before_md5  # the audio itself did not change


def test_replacing_a_field_that_is_not_ambiguous_behaves_like_a_normal_edit(
    library: AnalysisLibrary,
) -> None:
    track_id, path = _flac_with_aliases(library)
    revision = library.library.source_record(track_id).revision  # type: ignore[union-attr]

    saved = library.writer.save(
        track_id, revision, MetadataPatch.one("title", "New title", replace_aliases=True), "draft"
    )

    assert saved.status == "saved", saved.message
    assert _tags(path)["title"] == ["New title"]
    assert set(_tags(path)) >= {"key", "initialkey", "bpm", "tempo"}  # ambiguity elsewhere stays


def test_analysis_keeps_ambiguous_fields_as_a_conflict_instead_of_failing(
    library: AnalysisLibrary,
) -> None:
    track_id, path = _flac_with_aliases(library)
    digest = sha256_of_file(path)
    settings = AnalysisSettings(write_tags=True)
    found = []

    reports = library.service(write_tags=True).run_batch(
        [track_id],
        settings,
        is_cancelled=lambda: False,
        report_progress=lambda _value: None,
        on_conflict=found.append,
    )

    assert [report.ok for report in reports] == [True]  # no AnalysisBatchError
    assert len(found) == 1
    conflict = found[0]
    assert conflict.track_id == track_id and conflict.file_name == "duplicates.flac"
    assert {entry.field for entry in conflict.entries} == {"key", "bpm"}
    stored = library.repository.get(track_id)
    assert stored is not None and stored.key is not None and stored.bpm is not None
    values = {entry.field: entry.value for entry in conflict.entries}
    assert values["key"] == stored.key.text(settings.notation)
    assert values["bpm"] == bpm_tag_text(stored.bpm, path)
    assert sha256_of_file(path) == digest  # nothing was written yet


def test_resolving_a_conflict_writes_the_waiting_values(library: AnalysisLibrary) -> None:
    track_id, path = _flac_with_aliases(library)
    service = library.service(write_tags=True)
    conflict = service.analyze_track(track_id, AnalysisSettings(write_tags=True)).conflict
    assert conflict is not None
    stored = library.repository.get(track_id)
    assert stored is not None and stored.key is not None and stored.bpm is not None

    assert service.resolve_tag_conflict(conflict) == ""

    tags = _tags(path)
    assert tags["initialkey"] == [stored.key.text("camelot")]
    assert tags["bpm"] == [bpm_tag_text(stored.bpm, path)]
    assert "key" not in tags and "tempo" not in tags
    assert tags["mytag"] == ["keep me"]
    assert library.writer.tag_conflicts(track_id, ("key", "bpm")) == {}


def test_a_value_the_user_edited_since_is_not_replaced(library: AnalysisLibrary) -> None:
    track_id, path = _flac_with_aliases(library)
    service = library.service(write_tags=True)
    conflict = service.analyze_track(track_id, AnalysisSettings(write_tags=True)).conflict
    assert conflict is not None

    library.repository.mark_user_edited([track_id], "key")

    assert service.resolve_tag_conflict(conflict) == ""
    tags = _tags(path)
    assert tags["key"] == ["Gm"] and tags["initialkey"] == ["1A"]  # the edited field is left alone
    assert "tempo" not in tags  # the tempo conflict was still resolved


def test_a_conflict_on_a_file_that_disappeared_is_reported(library: AnalysisLibrary) -> None:
    track_id, _path = _flac_with_aliases(library)
    service = library.service(write_tags=True)
    conflict = service.analyze_track(track_id, AnalysisSettings(write_tags=True)).conflict
    assert conflict is not None
    with library.database.transaction() as connection:
        connection.execute("DELETE FROM track_locations WHERE track_id = ?", (track_id,))

    assert "no longer in the library" in service.resolve_tag_conflict(conflict)
