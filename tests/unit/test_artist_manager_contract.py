"""Backend contract of the artist manager: proposals, review, lots and file application.

One parametrized test runs each family of cases of plan 104 on a small synthetic
library in a temporary folder. Every write to a file happens on those copies; the audio
decoder of the analysis is replaced by a stub, the database and the services are real.
"""

from __future__ import annotations

import base64
import functools
import os
import shutil
import tempfile
import wave
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from mutagen import File as MutagenFile
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, TIT2, TPE1, TXXX
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm

from mtee.domain.analysis import AnalysisSettings
from mtee.domain.artists import build_stem, propose, safe_file_name
from mtee.domain.jobs import JobCancelledError
from mtee.domain.tracks import SourceRevision, TrackId, sha256_of_file
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.metadata_history_repository import MetadataHistoryRepository
from mtee.plugins.artist_manager import file_service as artist_file_service
from mtee.plugins.artist_manager.file_service import ArtistFileService
from mtee.plugins.artist_manager.identification import ArtistIdentificationService
from mtee.plugins.artist_manager.repository import ArtistRepository
from mtee.plugins.artist_manager.service import ArtistManagerError, ArtistManagerService
from mtee.services.analysis_service import AnalysisService
from mtee.services.ffmpeg_runtime import FfmpegRuntime, FfmpegRuntimeError
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.metadata_reader import MetadataReader
from mtee.services.metadata_writer import MetadataEditService

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
_ENCODERS: dict[str, tuple[str, list[str]]] = {
    "mp3": ("mp3", ["-c:a", "libmp3lame", "-q:a", "6"]),
    "flac": ("flac", ["-c:a", "flac"]),
    "aiff": ("aiff", ["-c:a", "pcm_s16be"]),
    "aif": ("aif", ["-c:a", "pcm_s16be"]),
    "m4a": ("m4a", ["-c:a", "aac", "-b:a", "96k"]),
    "ogg": ("ogg", ["-c:a", "libvorbis", "-q:a", "2"]),
    "opus": ("opus", ["-c:a", "libopus", "-b:a", "48k"]),
}
_FORMATS = ("wav", "mp3", "flac", "aiff", "aif", "m4a", "ogg", "opus")


@functools.cache
def _blank_audio(kind: str) -> bytes:
    """Return a short silent file of a format, created once with the pinned FFmpeg."""
    folder = Path(tempfile.mkdtemp(prefix="mtee-artist-fixture-"))
    target = folder / f"blank.{kind}"
    if kind == "wav":
        with wave.open(str(target), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8_000)
            handle.writeframes(b"\x00\x00" * 1_600)
    else:
        runtime = FfmpegRuntime()
        extension, encoding = _ENCODERS[kind]
        result = runtime.run(
            "ffmpeg",
            [
                "-hide_banner",
                "-nostdin",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=44100:duration=0.5",
                "-ac",
                "1",
                "-map_metadata",
                "-1",
                *encoding,
                str(folder / f"blank.{extension}"),
            ],
            timeout_seconds=60,
        )
        assert result.returncode == 0, result.stderr
    data = target.read_bytes()
    shutil.rmtree(folder, ignore_errors=True)
    return data


def _set_tags(path: Path, kind: str, artist: str | list[str] | None, title: str | None) -> None:
    """Write the artist/title tags of a fixture with Mutagen, in the container's own way."""
    artists = [artist] if isinstance(artist, str) else list(artist or [])
    if artist is None and title is None:
        return
    if kind in {"wav", "mp3", "aiff", "aif"}:
        audio = MutagenFile(path)
        if audio.tags is None:
            audio.add_tags()
        if artists:
            audio.tags.add(TPE1(encoding=3, text=artists))
        if title:
            audio.tags.add(TIT2(encoding=3, text=[title]))
        audio.save()
    elif kind == "m4a":
        audio = MP4(path)
        if audio.tags is None:
            audio.add_tags()
        if artists:
            audio.tags["\xa9ART"] = artists
        if title:
            audio.tags["\xa9nam"] = [title]
        audio.save()
    else:
        audio = MutagenFile(path)
        if audio.tags is None:
            audio.add_tags()
        if artists:
            audio.tags["artist"] = artists
        if title:
            audio.tags["title"] = [title]
        audio.save()


def _add_markers(path: Path, kind: str) -> None:
    """Add an unknown tag and a cover that a tag write must leave untouched."""
    if kind in {"wav", "mp3", "aiff", "aif"}:
        audio = MutagenFile(path)
        if audio.tags is None:
            audio.add_tags()
        audio.tags.add(TXXX(encoding=3, desc="MTEE-PRESERVE", text=["keep-this-frame"]))
        audio.tags.add(APIC(encoding=3, mime="image/png", type=3, desc="cover", data=_PNG))
        audio.save()
    elif kind == "flac":
        flac = FLAC(path)
        flac["MTEE_FIXTURE_MARKER"] = ["keep-this-comment"]
        picture = Picture()
        picture.type = 3
        picture.mime = "image/png"
        picture.data = _PNG
        flac.add_picture(picture)
        flac.save()
    elif kind in {"ogg", "opus"}:
        audio = MutagenFile(path)
        if audio.tags is None:
            audio.add_tags()
        audio.tags["MTEE_FIXTURE_MARKER"] = ["keep-this-comment"]
        audio.tags["COVERART"] = [base64.b64encode(_PNG).decode("ascii")]
        audio.save()
    elif kind == "m4a":
        mp4 = MP4(path)
        if mp4.tags is None:
            mp4.add_tags()
        mp4.tags["----:com.apple.iTunes:mtee_fixture_marker"] = [MP4FreeForm(b"keep-this-atom")]
        mp4.tags["covr"] = [MP4Cover(_PNG, imageformat=MP4Cover.FORMAT_PNG)]
        mp4.save()


def _markers_present(path: Path, kind: str) -> bool:
    audio = MutagenFile(path)
    tags = audio.tags
    if kind in {"wav", "mp3", "aiff", "aif"}:
        assert isinstance(tags, ID3)
        return bool(tags.getall("TXXX:MTEE-PRESERVE")) and bool(tags.getall("APIC"))
    if kind == "flac":
        return bool(audio.tags.get("MTEE_FIXTURE_MARKER")) and bool(audio.pictures)
    if kind in {"ogg", "opus"}:
        return bool(tags.get("MTEE_FIXTURE_MARKER")) and bool(tags.get("COVERART"))
    return "----:com.apple.iTunes:mtee_fixture_marker" in tags and bool(tags.get("covr"))


class Lab:
    """A temporary library with the real repositories and services of the manager."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.music = base / "music"
        self.music.mkdir(parents=True)
        self.database = Database(base / "data" / "mtee.sqlite3")
        self.database.migrate()
        self.library = LibraryRepository(self.database)
        self.artists = ArtistRepository(self.database)
        self.access = FileAccessCoordinator(default_timeout_seconds=0.05)
        self.writer = MetadataEditService(
            self.library, MetadataHistoryRepository(self.database), self.access
        )
        self.save_calls: list[str] = []
        real_save = self.writer.save

        def counting_save(*args: Any, **kwargs: Any) -> Any:
            self.save_calls.append(str(args[0]))
            return real_save(*args, **kwargs)

        self.writer.save = counting_save  # type: ignore[method-assign]
        self.files = ArtistFileService(
            self.database, self.library, self.artists, self.writer, self.access
        )
        self.identification = ArtistIdentificationService(self.library, self.artists)
        self.manager = ArtistManagerService(self.artists, self.files)
        self.root_id = str(self.library.add_root(self.music)["id"])

    def make(
        self,
        relative: str,
        *,
        artist: str | list[str] | None = None,
        title: str | None = None,
        markers: bool = False,
    ) -> Path:
        path = self.music / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        kind = path.suffix.lstrip(".").lower()
        try:
            path.write_bytes(_blank_audio(kind))
        except FfmpegRuntimeError:
            pytest.skip("The bundled FFmpeg runtime is unavailable.")
        _set_tags(path, kind, artist, title)
        if markers:
            _add_markers(path, kind)
        return path

    def scan(self) -> dict[str, str]:
        """Catalog every audio file of the library folder; returns ``{relative: track_id}``."""
        generation = self.library.begin_scan(self.root_id)
        reader = MetadataReader()
        entries = []
        for path in sorted(self.music.rglob("*")):
            if path.is_file() and not path.name.startswith("."):
                relative = path.relative_to(self.music).as_posix()
                entries.append((relative, path, SourceRevision.observe(path), reader.read(path)))
        self.library.upsert_locations(self.root_id, entries, generation)
        self.library.finish_scan(self.root_id, generation, complete=True)
        return self.ids()

    def ids(self) -> dict[str, str]:
        found: dict[str, str] = {}
        for path in sorted(self.music.rglob("*")):
            owner = self.library.path_owner(path) if path.is_file() else None
            if owner:
                found[path.relative_to(self.music).as_posix()] = owner
        return found

    def identify_all(self) -> list[str]:
        ids = self.identification.register_collection()
        for track_id in ids:
            assert self.identification.identify_track(track_id).ok
        return ids

    def row(self, track_id: str) -> dict[str, Any]:
        row = self.artists.review(track_id)
        assert row is not None
        return row

    def names(self, track_id: str) -> list[str]:
        return [credit["name"] for credit in self.row(track_id)["credits"]]

    def confirm(
        self,
        category: str,
        *,
        scope: str = "tracks",
        search: str = "",
        write_tags: bool = False,
    ) -> str:
        preview = self.manager.preview_confirmation(category, scope, search)
        assert not preview.blocked, preview.blocked
        return self.manager.stage(preview.items, write_tags=write_tags, label="test").operation_id

    def apply(self, operation_id: str) -> artist_file_service.ApplySummary:
        return self.files.apply_operation(operation_id)

    def location(self, track_id: str) -> Path:
        record = self.library.source_record(track_id)
        assert record is not None
        return record.path

    def close(self) -> None:
        self.database.close()


@pytest.fixture
def lab(tmp_path: Path) -> Any:
    instance = Lab(tmp_path)
    yield instance
    instance.close()


# --------------------------------------------------------------------- scenarios


def scenario_tags_multiple(lab: Lab) -> None:
    first = lab.make("multi.mp3", artist=["A+", "Ev & MPH"], title="Song")
    lab.make("other.mp3", artist="A+", title="Other")
    before = sha256_of_file(first)
    ids = lab.scan()
    lab.identify_all()
    row = lab.row(ids["multi.mp3"])
    assert [credit["name"] for credit in row["credits"]] == ["A+", "Ev", "MPH"]
    assert row["category"] == "from_tags"
    assert row["reviewState"] == "pending"
    assert lab.names(ids["other.mp3"]) == ["A+"]
    assert lab.row(ids["other.mp3"])["credits"][0]["id"] == row["credits"][0]["id"]
    assert len({credit["id"] for credit in row["credits"]}) == 3
    assert sha256_of_file(first) == before
    assert lab.artists.catalog() == []  # a proposal is not an established artist


def scenario_no_extra_separators(lab: Lab) -> None:
    lab.make("X x Y - Song.wav")
    lab.make("Jay-Z feat. Kid - Tune.wav")
    lab.make("Dj A - Foo.wav")
    ids = lab.scan()
    lab.identify_all()
    assert lab.names(ids["X x Y - Song.wav"]) == ["X x Y"]
    assert lab.names(ids["Jay-Z feat. Kid - Tune.wav"]) == ["Jay-Z feat. Kid"]
    track = ids["Dj A - Foo.wav"]
    entries = [("", "Smith, John")]
    lab.manager.save_edit(track, "Foo", entries)
    assert lab.names(track) == ["Smith, John"]
    lab.identification.identify_track(track)
    lab.identify_all()
    assert lab.names(track) == ["Smith, John"]
    assert lab.row(track)["version"] == 2


def scenario_spellings(lab: Lab) -> None:
    for name in ("mph - One", "MPH - Two", "Mph - Three"):
        lab.make(f"{name}.wav")
    for name in ("Skream - A", "skream - B", "Skream - C", "Skrem - E"):
        lab.make(f"{name}.wav")
    ids = lab.scan()
    lab.identify_all()
    mph = {lab.row(ids[f"{name}.wav"])["credits"][0]["id"] for name in ("mph - One", "MPH - Two")}
    assert len(mph) == 1
    assert lab.names(ids["mph - One.wav"]) == ["MPH"]
    assert lab.names(ids["skream - B.wav"]) == ["Skream"]
    skream = lab.row(ids["Skream - A.wav"])["credits"][0]["id"]
    assert lab.row(ids["Skrem - E.wav"])["credits"][0]["id"] != skream  # no fuzzy merge
    lab.artists.rename_artist(skream, "Skream (UK)")
    lab.make("skream - F.wav")
    ids = lab.scan()
    lab.identify_all()
    again = lab.row(ids["skream - F.wav"])["credits"][0]
    assert again["id"] == skream
    assert again["name"] == "Skream (UK)"
    lab.artists.reconsider_spellings()
    assert lab.artists.artist(skream)["name"] == "Skream (UK)"  # the manual name wins


def scenario_prefix_and_absence(lab: Lab) -> None:
    lab.make("Dj Unknown - Tune.wav")
    lab.make("01 - Tune.wav")
    lab.make("justtitle.wav")
    lab.make("Real Artist - !!!.wav")
    ids = lab.scan()
    lab.identify_all()
    unknown = lab.row(ids["Dj Unknown - Tune.wav"])
    assert (unknown["category"], unknown["artists"], unknown["title"]) == (
        "suggested",
        "Dj Unknown",
        "Tune",
    )
    numeric = lab.row(ids["01 - Tune.wav"])
    assert numeric["category"] == "needs_input"
    assert numeric["incomplete"]
    assert lab.row(ids["justtitle.wav"])["category"] == "needs_input"
    assert lab.row(ids["Real Artist - !!!.wav"])["incomplete"]  # a title is required
    with pytest.raises(ArtistManagerError, match="still need"):
        lab.manager.stage(
            [(ids["Real Artist - !!!.wav"], lab.row(ids["Real Artist - !!!.wav"])["version"])],
            write_tags=False,
            label="x",
        )
    assert propose([], [], "A - Title").category == "suggested"


def scenario_remix(lab: Lab) -> None:
    lab.make("Artist - Song (Remixer Remix).wav")
    lab.make("Song (Other Flip).wav")
    lab.make("Artist - Song2 (Artist Bootleg).wav")
    lab.make("Artist - Song3 (Remix).wav")
    lab.make("Artist - Song4 [Z & Y Flip].wav")
    ids = lab.scan()
    lab.identify_all()
    remix = lab.row(ids["Artist - Song (Remixer Remix).wav"])
    assert [(item["name"], item["role"]) for item in remix["credits"]] == [
        ("Artist", "artist"),
        ("Remixer", "remixer"),
    ]
    assert remix["title"] == "Song (Remixer Remix)"
    flip = lab.row(ids["Song (Other Flip).wav"])
    assert (flip["category"], flip["artists"]) == ("suggested", "Other")
    assert lab.names(ids["Artist - Song2 (Artist Bootleg).wav"]) == ["Artist"]
    assert lab.names(ids["Artist - Song3 (Remix).wav"]) == ["Artist"]
    assert lab.names(ids["Artist - Song4 [Z & Y Flip].wav"]) == ["Artist", "Z", "Y"]


class _FakeAnalysisRepository:
    """Audio results that are always current, so only the artist phase is missing."""

    def __init__(self) -> None:
        self.saved: list[str] = []

    def get(self, _track_id: str) -> None:
        return None

    def get_many(self, _ids: Any) -> dict[str, Any]:
        return {}

    def is_current(self, _stored: Any, _duration: Any) -> bool:
        return True

    def has_current_waveform(self, _track_id: str, _duration: Any) -> bool:
        return True

    def loudness_is_current(self, _stored: Any, _duration: Any) -> bool:
        return True

    def save_waveform(self, track_id: str, *_args: Any) -> None:
        self.saved.append(f"waveform:{track_id}")

    def save_loudness(self, track_id: str, *_args: Any) -> None:
        self.saved.append(f"loudness:{track_id}")

    def save_result(self, track_id: str, **_kwargs: Any) -> Any:
        self.saved.append(f"result:{track_id}")
        return SimpleNamespace(bpm=None, key=None, bpm_user_edited=False, key_user_edited=False)


class _FakeAnalyzer:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, *_args: Any, **_kwargs: Any) -> Any:
        self.calls += 1
        return SimpleNamespace(bpm=120.0, key=None, waveform=None, loudness=None)


def scenario_analysis_and_reanalysis(lab: Lab) -> None:
    for name in ("One", "Two", "Three", "Four"):
        lab.make(f"Band - {name}.wav")
    ids = lab.scan()
    analyzer = _FakeAnalyzer()
    repository = _FakeAnalysisRepository()
    service = AnalysisService(
        lab.library,
        repository,  # type: ignore[arg-type]
        analyzer,  # type: ignore[arg-type]
        None,
        lab.identification,
    )
    track_ids = list(ids.values())
    assert service.pending(track_ids, force=False) == track_ids  # audio is current, reviews absent
    settings = AnalysisSettings(parallel_jobs=1)
    seen: list[str] = []

    def cancel_after_first() -> bool:
        return len(seen) >= 1

    with pytest.raises(JobCancelledError):
        service.run_batch(
            track_ids,
            settings,
            is_cancelled=cancel_after_first,
            report_progress=lambda _value: None,
            on_track_done=seen.append,
        )
    assert analyzer.calls == 0  # no audio was decoded for a current analysis
    resumed = service.pending(track_ids, force=False)
    assert 0 < len(resumed) < len(track_ids)  # the interruption kept the finished tracks
    service.run_batch(
        resumed, settings, is_cancelled=lambda: False, report_progress=lambda _value: None
    )
    assert service.pending(track_ids, force=False) == []
    track = track_ids[0]
    lab.manager.save_edit(track, "Edited", [("", "Corrected Artist")])
    version = lab.row(track)["version"]
    report = service.analyze_track(track, settings, force=True)
    assert report.ok and analyzer.calls == 1  # force redoes the audio...
    assert service.pending(track_ids, force=True) == track_ids
    assert lab.names(track) == ["Corrected Artist"]  # ...and keeps the correction
    assert lab.row(track)["version"] == version
    assert lab.row(track)["title"] == "Edited"


def scenario_navigation(lab: Lab) -> None:
    lab.make("Tagged.mp3", artist="Tagged Artist", title="Tagged")
    lab.make("Suggest - Song.wav")
    ids = lab.scan()
    assert lab.artists.workflow()["mode"] == "guided"
    before = lab.manager.state()
    assert not before["cohortReady"]
    assert before["categories"]["from_tags"]["accessible"]
    assert not before["categories"]["suggested"]["accessible"]
    assert lab.manager.preview_confirmation("from_tags", "tracks").blocked
    lab.identify_all()
    state = lab.manager.state()
    assert state["cohortReady"] and state["mode"] == "guided"
    assert not state["categories"]["suggested"]["accessible"]
    # a filter that hides the remaining rows never finishes a category
    hidden = lab.manager.preview_confirmation("from_tags", "tracks", "no such row")
    assert hidden.track_count == 0
    assert not lab.manager.state()["categories"]["from_tags"]["complete"]
    assert lab.manager.preview_confirmation("suggested", "tracks").blocked
    lab.apply(lab.confirm("from_tags"))
    state = lab.manager.state()
    assert state["categories"]["from_tags"]["complete"]
    assert state["categories"]["suggested"]["accessible"]
    assert not state["categories"]["needs_input"]["accessible"]
    lab.apply(lab.confirm("suggested"))
    state = lab.manager.state()
    assert state["categories"]["needs_input"]["complete"]  # an empty category is finished
    assert state["completed"] and state["mode"] == "free"
    for artist in lab.artists.catalog():
        lab.artists.delete_artist(artist["id"])
    assert lab.artists.catalog() == []
    assert lab.manager.state()["mode"] == "free"  # no return to the guided run
    assert set(ids) == {"Tagged.mp3", "Suggest - Song.wav"}


def scenario_populated_base(lab: Lab) -> None:
    lab.make("Someone - Track.wav")
    lab.scan()
    with lab.database.transaction() as connection:
        connection.execute(
            "INSERT INTO artists(artist_id,display_name,name_key,name_origin,state,"
            "created_at_utc,updated_at_utc) VALUES('a1','Known','known','manual',"
            "'established','2026-01-01','2026-01-01')"
        )
    assert lab.artists.workflow()["mode"] == "free"
    lab.identify_all()
    state = lab.manager.state()
    assert all(item["accessible"] for item in state["categories"].values())
    assert not lab.manager.preview_confirmation("suggested", "tracks").blocked


def scenario_filtered_confirmation(lab: Lab) -> None:
    for name in ("Alpha - One", "Alpha, Beta - Two", "Gamma - Three", "Delta - Four"):
        lab.make(f"{name}.wav")
    ids = lab.scan()
    lab.identify_all()
    assert lab.manager.state()["categories"]["from_tags"]["complete"]  # nothing is tagged
    state = lab.manager.state()
    assert state["categories"]["suggested"]["accessible"]
    preview = lab.manager.preview_confirmation("suggested", "tracks", "alpha")
    frozen = {track_id for track_id, _version in preview.items}
    assert frozen == {ids["Alpha - One.wav"], ids["Alpha, Beta - Two.wav"]}
    by_artist = lab.manager.preview_confirmation("suggested", "artists", "alp")
    assert (by_artist.artist_count, by_artist.track_count) == (1, 2)  # Two counted once
    beta = lab.manager.preview_confirmation("suggested", "artists", "beta")
    assert {track_id for track_id, _ in beta.items} == {ids["Alpha, Beta - Two.wav"]}
    lab.manager.save_edit(ids["Alpha - One.wav"], "One!", [("", "Alpha")])
    with pytest.raises(ArtistManagerError, match="changed"):
        lab.manager.stage(preview.items, write_tags=False, label="stale")
    fresh = lab.manager.preview_confirmation("suggested", "tracks", "alpha")
    lab.apply(lab.manager.stage(fresh.items, write_tags=False, label="ok").operation_id)
    assert lab.names(ids["Alpha, Beta - Two.wav"]) == ["Alpha", "Beta"]  # the whole credit
    assert (lab.music / "Alpha, Beta - Two.wav").is_file()
    assert (lab.music / "Alpha - One!.wav").is_file()
    for hidden in ("Gamma - Three.wav", "Delta - Four.wav"):
        assert lab.row(ids[hidden])["reviewState"] == "pending"
        assert (lab.music / hidden).is_file()


def scenario_rename_formats(lab: Lab) -> None:
    expected: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for kind in _FORMATS:
        path = lab.make(f"src-{kind}.{kind}", artist="Tagged Artist", title="Tagged Title")
        hashes[kind] = sha256_of_file(path)
    lab.make("Zed - Same.wav")
    ids = lab.scan()
    lab.identify_all()
    for kind in _FORMATS:
        track = ids[f"src-{kind}.{kind}"]
        lab.manager.save_edit(track, "Song: Live?", [("", "Alpha"), ("", "Beta")])
        expected[kind] = f"Alpha, Beta - Song- Live_.{kind}"
    lab.apply(lab.confirm("from_tags"))
    lab.apply(lab.confirm("suggested"))
    for kind in _FORMATS:
        track = ids[f"src-{kind}.{kind}"]
        assert lab.location(track).name == expected[kind]
        assert lab.location(track).is_file()
        assert not (lab.music / f"src-{kind}.{kind}").exists()
        assert sha256_of_file(lab.location(track)) == hashes[kind]  # tags box left empty
        assert lab.row(track)["applyState"] == "succeeded"
        assert lab.library.track(track)["path"].endswith(expected[kind])
    same = ids["Zed - Same.wav"]
    assert lab.location(same).name == "Zed - Same.wav"  # already conforming: no move
    noop = lab.artists.operation_items(lab.artists.last_confirmation()["operation_id"])
    assert any(entry["rename_phase"] == "noop" for entry in noop)
    assert safe_file_name(build_stem(["CON"], "x"), ".wav")[0].startswith("CON")
    name, shortened = safe_file_name("T" * 400, ".mp3")
    assert shortened and len(name) < 260


def scenario_collisions(lab: Lab) -> None:
    lab.make("First - Dup.wav")
    for index in (1, 2, 3):
        lab.make(f"x{index}.wav")
    ids = lab.scan()
    lab.identify_all()
    (lab.music / "First - Dup (4).wav").write_bytes(b"not in the catalog")
    for index in (1, 2, 3):
        lab.manager.save_edit(ids[f"x{index}.wav"], "Dup", [("", "First")])
    lab.apply(lab.confirm("suggested"))  # "First - Dup" is already conforming
    lab.apply(lab.confirm("needs_input"))  # the edited rows were moved here by their file names
    names = sorted(lab.location(ids[f"x{index}.wav"]).name for index in (1, 2, 3))
    assert names == ["First - Dup (2).wav", "First - Dup (3).wav", "First - Dup (5).wav"]
    assert (lab.music / "First - Dup (4).wav").read_bytes() == b"not in the catalog"
    assert lab.location(ids["First - Dup.wav"]).name == "First - Dup.wav"


def scenario_tags_written(lab: Lab) -> None:
    # one library, one track per format: the tags box is ticked for the whole lot
    for kind in _FORMATS:
        lab.make(f"{kind}/t.{kind}", artist="Old Artist", title="Old Title", markers=True)
    ids = lab.scan()
    lab.identify_all()
    for kind in _FORMATS:
        track = ids[f"{kind}/t.{kind}"]
        lab.manager.save_edit(track, "New Title", [("", "Alpha"), ("", "Beta & Co")])
    lab.apply(lab.confirm("from_tags", write_tags=True))
    for kind in _FORMATS:
        track = ids[f"{kind}/t.{kind}"]
        final = lab.location(track)
        assert final.name == f"Alpha, Beta & Co - New Title.{kind}", kind
        snapshot = MetadataReader().read(final)
        assert snapshot.title == ("New Title",), kind
        assert snapshot.artist == ("Alpha, Beta & Co",), kind
        assert _markers_present(final, kind), kind
        assert lab.row(track)["applyState"] == "succeeded", kind
        assert lab.library.track(track)["title"] == "New Title", kind


def scenario_artist_operations(lab: Lab) -> None:
    lab.make("Alpha, Beta - T1.wav")
    lab.make("Alpha - T2.wav")
    lab.make("Beta, Gamma - T3.wav")
    ids = lab.scan()
    lab.identify_all()
    lab.apply(lab.confirm("suggested"))
    t1, t2, t3 = ids["Alpha, Beta - T1.wav"], ids["Alpha - T2.wav"], ids["Beta, Gamma - T3.wav"]
    catalog = {entry["name"]: entry for entry in lab.artists.catalog()}
    assert set(catalog) == {"Alpha", "Beta", "Gamma"}
    assert catalog["Beta"]["tracks"] == 2
    result = lab.manager.rename_artist(catalog["Alpha"]["id"], "Alpha Prime", write_tags=False)
    assert result["tracks"] == 2
    lab.apply(result["operationId"])
    assert lab.location(t1).name == "Alpha Prime, Beta - T1.wav"
    assert lab.location(t2).name == "Alpha Prime - T2.wav"
    merged = lab.manager.merge_artist(
        catalog["Gamma"]["id"], catalog["Beta"]["id"], write_tags=False
    )
    lab.apply(merged["operationId"])
    assert lab.names(t3) == ["Beta"]  # duplicated credit removed, order kept
    assert lab.location(t3).name == "Beta - T3.wav"
    deleted = lab.manager.delete_artist(catalog["Beta"]["id"], remove_from_tags=False)
    lab.apply(deleted["operationId"])
    assert lab.names(t1) == ["Alpha Prime"]  # the co-artist stays
    assert lab.location(t1).name == "Alpha Prime - T1.wav"
    last = lab.row(t3)
    assert last["category"] == "needs_input" and last["reviewState"] == "pending"
    assert lab.location(t3).name == "Beta - T3.wav"  # no " - Title" file name
    assert {entry["name"] for entry in lab.artists.catalog()} == {"Alpha Prime"}
    with pytest.raises(ArtistManagerError):
        lab.manager.merge_artist(catalog["Alpha"]["id"], catalog["Alpha"]["id"], write_tags=False)


def scenario_catalog_and_artist_pages(lab: Lab) -> None:
    for name in ("Alpha - One", "Alpha, Beta - Two", "Alpha - Three (Beta Remix)"):
        lab.make(f"{name}.wav")
    ids = lab.scan()
    lab.identify_all()
    assert lab.manager.catalog() == []  # a proposal is not in the catalog
    lab.apply(lab.confirm("suggested"))
    catalog = {entry["name"]: entry for entry in lab.manager.catalog()}
    assert (catalog["Alpha"]["tracks"], catalog["Beta"]["tracks"]) == (3, 2)
    # a track counts once per artist, whatever the number of roles it holds
    assert sorted(entry["tracks"] for entry in lab.manager.catalog("alp")) == [3]
    track_ids = lab.artists.catalog_track_ids(catalog["Alpha"]["id"])
    assert track_ids == [ids[name] for name in sorted(ids, key=str.casefold)]
    rows = lab.library.tracks_by_ids([*track_ids, "no-such-track"])
    assert [row["id"] for row in rows] == track_ids
    result = lab.manager.rename_artist(catalog["Beta"]["id"], "Beta Prime", write_tags=False)
    lab.apply(result["operationId"])
    assert {row["filename"] for row in lab.library.tracks_by_ids(track_ids)} >= {
        "Alpha, Beta Prime - Two.wav"
    }
    assert lab.artists.artist(catalog["Beta"]["id"])["name"] == "Beta Prime"


def scenario_undo(lab: Lab) -> None:
    lab.make("Alpha - Undo.wav", artist="Alpha", title="Undo")
    lab.make("Beta - Keep.wav", artist="Beta", title="Keep")
    ids = lab.scan()
    lab.identify_all()
    undo_id, keep_id = ids["Alpha - Undo.wav"], ids["Beta - Keep.wav"]
    lab.manager.save_edit(undo_id, "Undo", [("", "Alpha Two")])
    lab.manager.save_edit(keep_id, "Keep", [("", "Beta Two")])
    preview = lab.manager.preview_confirmation("from_tags", "tracks", "undo")
    operation = lab.manager.stage(preview.items, write_tags=True, label="undo me").operation_id
    lab.apply(operation)
    assert lab.location(undo_id).name == "Alpha Two - Undo.wav"
    outcome = lab.files.undo_operation(operation)
    assert outcome["conflicts"] == []
    assert lab.location(undo_id).name == "Alpha - Undo.wav"
    assert MetadataReader().read(lab.location(undo_id)).artist == ("Alpha",)
    assert lab.row(undo_id)["reviewState"] == "pending"
    other = lab.manager.stage(
        [(keep_id, lab.row(keep_id)["version"])], write_tags=False, label="keep"
    ).operation_id
    lab.apply(other)
    changed = lab.location(keep_id)
    with changed.open("ab") as handle:
        handle.write(b"\x00\x00")
    result = lab.files.undo_operation(other)
    assert result["undone"] == [] and result["conflicts"]
    assert changed.is_file() and lab.row(keep_id)["reviewState"] == "confirmed"


def scenario_failures_and_resume(lab: Lab, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("changed", "busy", "aftertags", "afterrename"):
        lab.make(f"{name}.wav", artist="Seed", title=name)
    lab.make("Win - afterrename.wav")  # occupies the plain destination of the last track
    ids = lab.scan()
    lab.identify_all()
    for name in ("changed", "busy", "aftertags", "afterrename"):
        lab.manager.save_edit(ids[f"{name}.wav"], name, [("", "Win")])
    # a source modified after the scan is refused, then accepted after a new scan
    changed = lab.music / "changed.wav"
    preview = lab.manager.preview_confirmation("from_tags", "tracks", "changed")
    operation = lab.manager.stage(preview.items, write_tags=False, label="a").operation_id
    with changed.open("ab") as handle:
        handle.write(b"\x00\x00")
    summary = lab.apply(operation)
    assert summary.failed == 1 and changed.is_file()
    assert lab.row(ids["changed.wav"])["applyState"] == "failed"
    lab.scan()
    assert lab.apply(operation).succeeded == 1
    assert (lab.music / "Win - changed.wav").is_file()
    # a file in use is reported and applied once released
    preview = lab.manager.preview_confirmation("from_tags", "tracks", "busy")
    operation = lab.manager.stage(preview.items, write_tags=False, label="b").operation_id
    with lab.access.acquire_read(TrackId.parse(ids["busy.wav"]), "playback"):
        assert lab.apply(operation).failed == 1
    assert (lab.music / "busy.wav").is_file()
    assert lab.apply(operation).succeeded == 1
    # an error after the tags: the resume does not write them again
    preview = lab.manager.preview_confirmation("from_tags", "tracks", "aftertags")
    operation = lab.manager.stage(preview.items, write_tags=True, label="c").operation_id
    real_rename = os.rename
    calls = {"count": 0}

    def flaky_rename(source: Any, destination: Any) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("disk went away")
        real_rename(source, destination)

    monkeypatch.setattr(artist_file_service.os, "rename", flaky_rename)
    assert lab.apply(operation).failed == 1
    saves = len(lab.save_calls)
    assert lab.apply(operation).succeeded == 1
    assert len(lab.save_calls) == saves  # tags phase was already done
    assert (lab.music / "Win - aftertags.wav").is_file()
    monkeypatch.setattr(artist_file_service.os, "rename", real_rename)
    # an error after the rename: the resume finds the file and keeps the same suffix
    preview = lab.manager.preview_confirmation("from_tags", "tracks", "afterrename")
    operation = lab.manager.stage(preview.items, write_tags=False, label="d").operation_id
    real_finish = ArtistRepository.finish_item
    failures = {"left": 1}

    def flaky_finish(*args: Any, **kwargs: Any) -> None:
        if failures["left"]:
            failures["left"] -= 1
            raise RuntimeError("database went away")
        real_finish(*args, **kwargs)

    monkeypatch.setattr(ArtistRepository, "finish_item", staticmethod(flaky_finish))
    assert lab.apply(operation).failed == 1
    target = next(lab.music.glob("Win - afterrename (*).wav"))
    assert target.name == "Win - afterrename (2).wav"
    assert lab.apply(operation).succeeded == 1
    assert lab.location(ids["afterrename.wav"]) == target
    assert not list(lab.music.glob("*(2) (2)*"))


_SCENARIOS: dict[str, Callable[..., None]] = {
    "tags-multiple-comma-ampersand": scenario_tags_multiple,
    "no-extra-separators-and-literal-edit": scenario_no_extra_separators,
    "spellings-and-no-fuzzy-merge": scenario_spellings,
    "prefix-and-missing-data": scenario_prefix_and_absence,
    "remix-flip-bootleg": scenario_remix,
    "analysis-reanalysis-resume": scenario_analysis_and_reanalysis,
    "navigation-guided-run": scenario_navigation,
    "navigation-populated-base": scenario_populated_base,
    "filtered-confirmation": scenario_filtered_confirmation,
    "rename-every-format": scenario_rename_formats,
    "rename-collisions": scenario_collisions,
    "optional-tags-every-format": scenario_tags_written,
    "artist-operations": scenario_artist_operations,
    "catalog-and-artist-pages": scenario_catalog_and_artist_pages,
    "undo-and-conflict": scenario_undo,
    "failures-and-resume": scenario_failures_and_resume,
}


@pytest.mark.parametrize("scenario", list(_SCENARIOS), ids=list(_SCENARIOS))
def test_artist_manager_contract(scenario: str, lab: Lab, monkeypatch: pytest.MonkeyPatch) -> None:
    function = _SCENARIOS[scenario]
    if scenario == "failures-and-resume":
        function(lab, monkeypatch)
    else:
        function(lab)
