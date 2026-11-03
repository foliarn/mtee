"""Album covers: embedded and folder pictures, sizes, caching and refusals (plan 127.2)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette

from helpers import make_audio
from mtee_remote import tools
from mtee_remote.streaming import covers
from test_uploads import Env
from test_uploads import env as env
from test_uploads import other as other


def make_picture(path: Path, size: str, colour: str = "red") -> Path:
    """Write a one-frame picture (`.jpg` or `.png`, by the name) of `size` pixels."""
    subprocess.run(
        [
            tools.ffmpeg_path(),
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={colour}:s={size}",
            "-frames:v",
            "1",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def attach_cover(audio: Path, picture: Path, out: Path) -> Path:
    """Copy `audio` into `out` with `picture` as its attached front cover."""
    subprocess.run(
        [
            tools.ffmpeg_path(),
            "-v",
            "error",
            "-y",
            "-i",
            str(audio),
            "-i",
            str(picture),
            "-map",
            "0:a",
            "-map",
            "1:v",
            "-c",
            "copy",
            "-disposition:v:0",
            "attached_pic",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


def dimensions(tmp_path: Path, data: bytes) -> tuple[int, int]:
    """The width and height of a picture, as ffprobe reads them."""
    path = tmp_path / "probe.jpg"
    path.write_bytes(data)
    result = subprocess.run(
        [
            tools.ffprobe_path(),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        check=True,
    )
    stream = json.loads(result.stdout)["streams"][0]
    return int(stream["width"]), int(stream["height"])


def cover_url(item: dict[str, Any], size: str | None = None) -> str:
    suffix = f"?size={size}" if size is not None else ""
    return f"/api/v1/items/{item['item_id']}/cover{suffix}"


@pytest.fixture
def plain(env: Env, tmp_path: Path) -> tuple[Env, dict[str, Any]]:
    """A FLAC item with no embedded picture, in `rock/`."""
    data = make_audio(tmp_path / "plain.flac", "flac").read_bytes()
    return env, env.upload("rock/plain.flac", data)


@pytest.fixture
def runs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The source of every ffmpeg cover run, in order."""
    seen: list[str] = []
    real = covers._run_ffmpeg  # pyright: ignore[reportPrivateUsage]

    def counting(source: Path, px: int, output: Path) -> bool:
        seen.append(source.name)
        return real(source, px, output)

    monkeypatch.setattr(covers, "_run_ffmpeg", counting)
    return seen


def test_an_embedded_cover_is_resized_to_the_small_size(env: Env, tmp_path: Path) -> None:
    picture = make_picture(tmp_path / "front.jpg", "600x400")
    mp3 = make_audio(tmp_path / "tagged.mp3", "mp3")
    tagged = attach_cover(mp3, picture, tmp_path / "tagged-cover.mp3")
    item = env.upload("rock/tagged.mp3", tagged.read_bytes())
    response = env.client.get(cover_url(item, "s"), headers=env.headers)
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/jpeg"
    assert response.headers["Cache-Control"] == "private, max-age=604800"
    assert response.headers["ETag"] == f'"{item["sha256"]}-128"'
    width, height = dimensions(tmp_path, response.content)
    assert max(width, height) == 128


def test_a_folder_picture_is_used_when_there_is_no_embedded_cover(
    plain: tuple[Env, dict[str, Any]], tmp_path: Path
) -> None:
    env, item = plain
    make_picture(env.folder / "rock" / "cover.png", "400x400")
    response = env.client.get(cover_url(item, "m"), headers=env.headers)
    assert response.status_code == 200
    assert response.content[:3] == b"\xff\xd8\xff"  # a real JPEG, although the source was PNG
    assert dimensions(tmp_path, response.content) == (400, 400)


@pytest.mark.parametrize("name", ["Cover.JPG", "folder.jpeg", "FRONT.png", "album.PNG"])
def test_folder_names_are_case_insensitive(
    plain: tuple[Env, dict[str, Any]], tmp_path: Path, name: str
) -> None:
    env, item = plain
    make_picture(env.folder / "rock" / name, "200x200")
    response = env.client.get(cover_url(item, "s"), headers=env.headers)
    assert response.status_code == 200


@pytest.mark.parametrize("name", ["cover.gif", "scan.jpg", "cover.jpg.bak"])
def test_other_picture_names_are_not_covers(plain: tuple[Env, dict[str, Any]], name: str) -> None:
    env, item = plain
    (env.folder / "rock" / name).write_bytes(b"not looked at")
    response = env.client.get(cover_url(item, "s"), headers=env.headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_no_cover_at_all_is_not_found(plain: tuple[Env, dict[str, Any]]) -> None:
    env, item = plain
    response = env.client.get(cover_url(item, "m"), headers=env.headers)
    assert response.status_code == 404


def test_the_second_call_is_served_from_the_cache(
    plain: tuple[Env, dict[str, Any]], runs: list[str]
) -> None:
    env, item = plain
    make_picture(env.folder / "rock" / "cover.jpg", "300x300")
    first = env.client.get(cover_url(item, "l"), headers=env.headers)
    second = env.client.get(cover_url(item, "l"), headers=env.headers)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content
    # The first call tried the audio file (no embedded cover), then the folder picture.
    assert runs == ["plain.flac", "cover.jpg"]


def test_a_cover_is_never_upscaled(plain: tuple[Env, dict[str, Any]], tmp_path: Path) -> None:
    env, item = plain
    make_picture(env.folder / "rock" / "cover.jpg", "300x200")
    response = env.client.get(cover_url(item, "l"), headers=env.headers)
    assert response.status_code == 200
    assert dimensions(tmp_path, response.content) == (300, 200)


def test_the_default_size_is_medium(plain: tuple[Env, dict[str, Any]], tmp_path: Path) -> None:
    env, item = plain
    make_picture(env.folder / "rock" / "cover.jpg", "1000x800")
    response = env.client.get(cover_url(item), headers=env.headers)
    assert response.status_code == 200
    width, height = dimensions(tmp_path, response.content)
    assert max(width, height) == 512


def test_an_unknown_size_is_a_bad_request(plain: tuple[Env, dict[str, Any]]) -> None:
    env, item = plain
    response = env.client.get(cover_url(item, "xl"), headers=env.headers)
    assert response.status_code == 400


def test_another_users_cover_is_not_found(plain: tuple[Env, dict[str, Any]], other: Env) -> None:
    _env, item = plain
    make_picture(_env.folder / "rock" / "cover.jpg", "200x200")
    response = other.client.get(cover_url(item, "s"), headers=other.headers)
    assert response.status_code == 404


def test_no_token_is_refused(plain: tuple[Env, dict[str, Any]]) -> None:
    env, item = plain
    assert env.client.get(cover_url(item, "s")).status_code == 401


def test_a_failing_ffmpeg_gives_no_cover_and_no_part_file(
    plain: tuple[Env, dict[str, Any]], app: Starlette
) -> None:
    env, item = plain
    (env.folder / "rock" / "cover.jpg").write_bytes(b"not a picture")
    response = env.client.get(cover_url(item, "s"), headers=env.headers)
    assert response.status_code == 404
    cache = app.state.settings.data_dir / "cache" / "covers"
    assert not any(".part-" in path.name for path in cache.glob("*"))
