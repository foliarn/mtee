"""Downloading the original file of an item, with Range support (milestone 124.5)."""

from __future__ import annotations

import pytest

from test_uploads import Env, blob, build_env, other, sha  # noqa: F401
from test_uploads import env as env


@pytest.fixture
def song(env: Env) -> tuple[Env, dict[str, object], bytes]:
    data = blob(5000, "song")
    item = env.upload("rock/song.flac", data)
    return env, item, data


def url(item: dict[str, object]) -> str:
    return f"/api/v1/items/{item['item_id']}/file"


def test_a_plain_download_has_length_ranges_type_and_etag(
    song: tuple[Env, dict[str, object], bytes],
) -> None:
    env, item, data = song
    response = env.client.get(url(item), headers=env.headers)
    assert response.status_code == 200
    assert response.content == data
    assert response.headers["Accept-Ranges"] == "bytes"
    assert response.headers["Content-Length"] == str(len(data))
    assert response.headers["Content-Type"] == "audio/flac"
    assert response.headers["ETag"] == f'"{sha(data)}"'


@pytest.mark.parametrize(
    ("name", "media_type"),
    [
        ("a.flac", "audio/flac"),
        ("a.mp3", "audio/mpeg"),
        ("a.m4a", "audio/mp4"),
        ("a.wav", "audio/wav"),
        ("a.aiff", "audio/aiff"),
        ("a.ogg", "audio/ogg"),
        ("a.opus", "audio/opus"),
        ("A.MP3", "audio/mpeg"),
        ("a.ape", "application/octet-stream"),
    ],
)
def test_the_content_type_follows_the_extension(env: Env, name: str, media_type: str) -> None:
    item = env.upload(name, blob(100, name))
    response = env.client.get(url(item), headers=env.headers)
    assert response.headers["Content-Type"] == media_type


def test_range_from_the_start_to_the_end(song: tuple[Env, dict[str, object], bytes]) -> None:
    env, item, data = song
    response = env.client.get(url(item), headers={**env.headers, "Range": "bytes=0-"})
    assert response.status_code == 206
    assert response.content == data
    assert response.headers["Content-Range"] == f"bytes 0-{len(data) - 1}/{len(data)}"
    assert response.headers["Content-Length"] == str(len(data))
    assert response.headers["Accept-Ranges"] == "bytes"


def test_range_in_the_middle(song: tuple[Env, dict[str, object], bytes]) -> None:
    env, item, data = song
    response = env.client.get(url(item), headers={**env.headers, "Range": "bytes=100-199"})
    assert response.status_code == 206
    assert response.content == data[100:200]
    assert response.headers["Content-Range"] == f"bytes 100-199/{len(data)}"
    assert response.headers["Content-Length"] == "100"


def test_suffix_range(song: tuple[Env, dict[str, object], bytes]) -> None:
    env, item, data = song
    response = env.client.get(url(item), headers={**env.headers, "Range": "bytes=-100"})
    assert response.status_code == 206
    assert response.content == data[-100:]
    assert (
        response.headers["Content-Range"] == f"bytes {len(data) - 100}-{len(data) - 1}/{len(data)}"
    )


def test_a_range_past_the_end_is_416_with_the_size(
    song: tuple[Env, dict[str, object], bytes],
) -> None:
    env, item, data = song
    response = env.client.get(url(item), headers={**env.headers, "Range": f"bytes={len(data)}-"})
    assert response.status_code == 416
    assert response.headers["Content-Range"] == f"bytes */{len(data)}"


def test_head_has_the_headers_and_no_body(song: tuple[Env, dict[str, object], bytes]) -> None:
    env, item, data = song
    response = env.client.head(url(item), headers=env.headers)
    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["Content-Length"] == str(len(data))


def test_a_download_after_a_replacement_serves_the_new_bytes(
    song: tuple[Env, dict[str, object], bytes],
) -> None:
    env, item, _ = song
    new = blob(300, "new")
    env.upload("rock/song.flac", new, base_item_id=item["item_id"], base_revision=1)
    response = env.client.get(url(item), headers=env.headers)
    assert response.content == new
    assert response.headers["ETag"] == f'"{sha(new)}"'


def test_unknown_foreign_trashed_and_missing_items_are_404(
    song: tuple[Env, dict[str, object], bytes],
    other: Env,  # noqa: F811
) -> None:
    env, item, _ = song
    assert env.client.get(f"/api/v1/items/{'0' * 32}/file", headers=env.headers).status_code == 404
    assert other.client.get(url(item), headers=other.headers).status_code == 404
    (env.folder / "rock" / "song.flac").unlink()
    response = env.client.get(url(item), headers=env.headers)
    assert (response.status_code, response.json()["error"]["code"]) == (404, "not_found")
    assert env.client.get(url(item)).status_code == 401


def test_a_trashed_item_cannot_be_downloaded(song: tuple[Env, dict[str, object], bytes]) -> None:
    env, item, _ = song
    assert (
        env.client.post(f"/api/v1/items/{item['item_id']}/trash", headers=env.headers).status_code
        == 200
    )
    assert env.client.get(url(item), headers=env.headers).status_code == 404
