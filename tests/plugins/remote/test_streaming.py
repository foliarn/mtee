"""Desktop playback of server-only tracks (plan 127.5), against a real MTEE Remote server.

The server is the one of the conftest (a session fixture). A track is uploaded by a second device
and fetched by the computer under test, so it is a server-only track with an item id and a SHA-256.
The player's requests carry the device token in the ``Authorization`` header, and the server
refuses a request without it: a stream that plays, or a 401 without the header, shows that.
"""

from __future__ import annotations

import array
import queue
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from mtee.plugins.remote import sources as sources_module  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.cache import open_cache  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.client import ApiError  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.fetch import fetch_once  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.sources import (  # pyright: ignore[reportMissingImports]
    ServerTrackError,
    ServerTracks,
    _wait_until_prepared,
    set_stream_level,
)
from mtee.plugins.remote.store import (  # pyright: ignore[reportMissingImports]
    FolderMapping,
    RemoteStore,
)
from tests.plugins.remote.conftest import RemoteServer
from tests.plugins.remote.devices import (
    NO_ITEM,
    Computer,
    MakeUser,
    open_computer,
    source_files,
    wait_hashed,
)
from tests.plugins.remote.helpers import FakeLibrary, fake_job, sha256_of, upload_file
from tests.plugins.remote.records_helpers import make_sync_context, new_device_id
from tests.plugins.remote.stream_helpers import (
    StaticLink,
    http_get,
    item_facts,
    make_cover_copy,
    wait_for_copy,
)

from mtee.domain.source_tracks import PlayableSource  # pyright: ignore[reportMissingImports]
from mtee.services.mpv_backend import MpvBackend


@pytest.fixture(scope="module")
def sources(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    return source_files(tmp_path_factory.mktemp("streaming-sources"))


@pytest.fixture
def computer(
    tmp_path: Path, remote_server: RemoteServer, make_user: MakeUser
) -> Iterator[Computer]:
    with open_computer(tmp_path, remote_server, make_user) as device:
        yield device


def _server_track(device: Computer, relative: str, source: Path) -> tuple[str, str]:
    """Upload ``source`` from the second device, fetch it here; return ``(track_id, item_id)``."""
    upload_file(device.peer, device.root_id, relative, source)
    wait_hashed(device.client, device.root_id)
    device.fetch()
    row = (
        device.store.connection()
        .execute(
            "SELECT item_id, source_track_id FROM remote_server_items WHERE relative_path = ?",
            (relative,),
        )
        .fetchone()
    )
    assert row is not None and row["source_track_id"] is not None, f"{relative} is not server only"
    return str(row["source_track_id"]), str(row["item_id"])


def _tracks(device: Computer, state: str = "connected") -> ServerTracks:
    """The track source of the computer; ``state`` is the connection (``none``: signed out)."""
    client = None if state == "none" else device.client
    link = StaticLink(client, "offline" if state == "offline" else "connected")
    return ServerTracks(device.context, device.store, cast(Any, link))


def _token_of(device: Computer) -> str:
    return device.client.authorization_headers()["Authorization"].removeprefix("Bearer ")


def test_original_streams_with_the_token_in_a_header_and_keeps_a_verified_copy(
    computer: Computer, sources: dict[str, Path]
) -> None:
    _, item_id = _server_track(computer, "Stream/original.flac", sources["other"])
    sha, ext = item_facts(computer.store, item_id)
    tracks = _tracks(computer)

    streamed = tracks.open(item_id)

    assert streamed.path is None
    assert (
        streamed.url == f"{computer.client.base_url}/api/v1/items/{item_id}/stream?level=original"
    )
    assert streamed.headers == {"Authorization": f"Bearer {_token_of(computer)}"}
    token = _token_of(computer)
    assert token not in streamed.url and token not in repr(streamed)
    # The server refuses the same URL without the header, so the header is what authorises it.
    status, _, _ = http_get(streamed.url)
    assert status == 401
    status, headers, body = http_get(streamed.url, dict(streamed.headers))
    assert status == 200 and body == sources["other"].read_bytes()
    assert headers.get("x-mtee-codec") == "flac"

    kept = wait_for_copy(computer.context, item_id, sha, ext)
    assert sha256_of(kept) == sha
    assert kept.parent == open_cache(computer.context).folder
    # The next play is the local copy, and it is not downloaded again.
    again = tracks.open(item_id)
    assert again.path == kept and again.url is None


def test_offline_plays_the_cached_copy_and_refuses_a_track_that_is_not_cached(
    computer: Computer, sources: dict[str, Path]
) -> None:
    _, cached_id = _server_track(computer, "Offline/cached.flac", sources["short"])
    _, other_id = _server_track(computer, "Offline/not-cached.flac", sources["long"])
    sha, ext = item_facts(computer.store, cached_id)
    _tracks(computer).open(cached_id)
    kept = wait_for_copy(computer.context, cached_id, sha, ext)

    offline = _tracks(computer, "offline")
    assert offline.open(cached_id).path == kept
    with pytest.raises(ServerTrackError, match="Not available offline"):
        offline.open(other_id)
    with pytest.raises(ServerTrackError, match="Not available offline"):
        _tracks(computer, "none").open(other_id)


def test_a_mismatched_copy_is_never_played_and_the_track_streams_again(
    computer: Computer, sources: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, item_id = _server_track(computer, "Stream/damaged.flac", sources["other"])
    sha, ext = item_facts(computer.store, item_id)
    downloads: list[str] = []
    original = type(computer.client).download

    def counting(self: Any, item: str, target: Path, **options: Any) -> Path:
        downloads.append(item)
        return cast(Path, original(self, item, target, **options))

    monkeypatch.setattr(type(computer.client), "download", counting)
    tracks = _tracks(computer)
    tracks.open(item_id)
    kept = wait_for_copy(computer.context, item_id, sha, ext)
    kept.write_bytes(b"damaged by something else")

    streamed = tracks.open(item_id)

    assert streamed.path is None and streamed.url is not None
    assert wait_for_copy(computer.context, item_id, sha, ext) is not None
    assert sha256_of(kept) == sha
    assert downloads == [item_id, item_id]


def test_a_second_open_while_the_copy_is_downloading_starts_no_second_download(
    computer: Computer, sources: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, item_id = _server_track(computer, "Stream/twice.flac", sources["long"])
    sha, ext = item_facts(computer.store, item_id)
    downloads: list[str] = []
    original = type(computer.client).download

    def counting(self: Any, item: str, target: Path, **options: Any) -> Path:
        downloads.append(item)
        return cast(Path, original(self, item, target, **options))

    monkeypatch.setattr(type(computer.client), "download", counting)
    tracks = _tracks(computer)

    tracks.open(item_id)
    tracks.open(item_id)  # the core prepares the next track while this one plays
    wait_for_copy(computer.context, item_id, sha, ext)

    assert downloads == [item_id]


def test_a_lossy_level_is_prepared_then_streamed_as_opus_and_is_not_kept(
    computer: Computer, sources: dict[str, Path]
) -> None:
    _, item_id = _server_track(computer, "Stream/lossy.flac", sources["long"])
    sha, ext = item_facts(computer.store, item_id)
    set_stream_level(computer.context, "320")
    tracks = _tracks(computer)

    played = tracks.open(item_id)

    assert played.path is None
    assert played.url == (
        f"{computer.client.base_url}/api/v1/items/{item_id}/stream?level=320&codecs=flac,opus"
    )
    assert played.headers == {"Authorization": f"Bearer {_token_of(computer)}"}
    status, headers, body = http_get(played.url, dict(played.headers))
    assert status == 200 and body
    assert headers.get("x-mtee-codec") == "opus"
    assert headers.get("x-mtee-bitrate") is not None
    assert http_get(played.url)[0] == 401
    # A transcode is not a copy of the original: nothing is kept on this computer for it.
    assert open_cache(computer.context).lookup(item_id, sha, ext) is None


def test_the_preparation_gives_up_after_the_limit_with_a_readable_error(
    computer: Computer, sources: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, item_id = _server_track(computer, "Stream/slow.flac", sources["short"])
    client = computer.client
    monkeypatch.setattr(sources_module, "PREPARE_TIMEOUT_S", 0.3)
    monkeypatch.setattr(client, "prepare_stream", lambda *args, **kwargs: False)

    with pytest.raises(ServerTrackError, match="still preparing"):
        _wait_until_prepared(client, item_id, "320")


def test_a_server_only_track_gets_the_loudness_measured_by_mtee(
    computer: Computer, sources: dict[str, Path], tmp_path: Path
) -> None:
    """Normalization needs no change: the loudness of the server reaches the track's source row.

    The computer's own context has no track data, so this device is the records test's device:
    a sync context with every core record, on the same account.
    """
    local = tmp_path / "Loud"
    local.mkdir()
    context, _stub = make_sync_context(
        tmp_path / "loud-device", FakeLibrary([local], []), new_device_id()
    )
    store = RemoteStore(context)
    store.save_mapping(FolderMapping(str(local), computer.root_id, ""))
    upload_file(computer.peer, computer.root_id, "Loud/measured.flac", sources["short"])
    wait_hashed(computer.client, computer.root_id)
    fetch_once(context, store, computer.client, fake_job())
    row = (
        store.connection()
        .execute(
            "SELECT item_id, source_track_id FROM remote_server_items WHERE relative_path = ?",
            ("Loud/measured.flac",),
        )
        .fetchone()
    )
    assert row is not None and row["source_track_id"] is not None
    item_id, track_id = str(row["item_id"]), str(row["source_track_id"])
    computer.peer.put_track_data(
        item_id,
        {"loudness": {"integrated_lufs": -14.2, "sample_peak_dbfs": -1.0, "loudness_version": 2}},
    )

    fetch_once(context, store, computer.client, fake_job())

    loudness = context.track_data.read(track_id).loudness
    assert loudness is not None and loudness.integrated_lufs == -14.2


def test_a_track_the_server_does_not_know_is_refused(computer: Computer) -> None:
    with pytest.raises(ServerTrackError):
        _tracks(computer).open(NO_ITEM)
    with pytest.raises(ApiError):
        computer.client.get_item(NO_ITEM)


def test_the_cover_is_read_once_kept_and_answered_offline(
    computer: Computer, sources: dict[str, Path], tmp_path: Path
) -> None:
    covered = make_cover_copy(sources["short"], tmp_path / "copies" / "covered.flac", tmp_path)
    _, covered_id = _server_track(computer, "Covers/covered.flac", covered)
    _, plain_id = _server_track(computer, "Covers/plain.flac", sources["other"])
    tracks = _tracks(computer)

    picture = tracks.cover(covered_id)

    assert picture is not None and picture[:2] == b"\xff\xd8"  # a JPEG
    row = (
        computer.store.connection()
        .execute("SELECT revision FROM remote_server_items WHERE item_id = ?", (covered_id,))
        .fetchone()
    )
    kept = computer.context.data_dir / "covers" / f"{covered_id}-{row['revision']}.jpg"
    assert kept.read_bytes() == picture
    assert tracks.cover(covered_id) == picture
    assert _tracks(computer, "offline").cover(covered_id) == picture
    assert tracks.cover(plain_id) is None
    assert tracks.cover(NO_ITEM) is None


@pytest.mark.native_audio
def test_the_player_plays_the_stream_with_the_header_through_libmpv(
    computer: Computer, sources: dict[str, Path], tmp_path: Path
) -> None:
    _, item_id = _server_track(computer, "Play/libmpv.flac", sources["other"])
    source = _tracks(computer).open(item_id)
    assert isinstance(source, PlayableSource) and source.url is not None
    output = tmp_path / "out.pcm"
    backend = MpvBackend(
        None,
        audio_output="pcm",
        extra_options={"ao-pcm-file": str(output), "ao-pcm-waveheader": "no"},
    )
    events: queue.Queue[Any] = queue.Queue()
    backend.set_event_handler(events.put)
    names: list[str] = []
    try:
        backend.load(source, 1)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not {"eof", "error"} & set(names):
            try:
                names.append(events.get(timeout=0.1).name)
            except queue.Empty:
                continue
    finally:
        backend.close()

    assert "error" not in names and "eof" in names, names
    samples = array.array("h")
    samples.frombytes(output.read_bytes())
    # The sine wave of the source is audible: the decoded samples are not silence.
    assert len(samples) > 44_100 and max(abs(value) for value in samples) > 1000
