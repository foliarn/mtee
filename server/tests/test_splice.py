"""Tags-only (splice) replacement uploads (plan 129.2).

The server holds an older copy of a file; the client sends only the bytes around the audio
payload, and the server rebuilds the file from them and the payload it already has.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from mtee.services.audio_payload import Span, payload_span, read_tag_parts, span_sha256
from mutagen.aiff import AIFF
from mutagen.flac import FLAC
from mutagen.id3 import COMM, TIT2
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.wave import WAVE

from helpers import make_audio
from test_uploads import Env, blob, error_code, sha
from test_uploads import env as env

LONG_COMMENT = "A long comment about this track. " * 100  # about 3 KB


def retag(path: Path) -> None:
    """Change the tags of a copy in place: the audio stays the same."""
    suffix = path.suffix
    if suffix == ".flac":
        flac = FLAC(path)
        flac["title"] = "A new title"
        flac["comment"] = LONG_COMMENT
        flac.save()
    elif suffix == ".m4a":
        mp4 = MP4(path)
        assert mp4.tags is not None
        mp4.tags["\xa9nam"] = ["A new title"]
        mp4.tags["\xa9cmt"] = [LONG_COMMENT]
        mp4.save()
    else:
        audio = {".mp3": MP3, ".wav": WAVE, ".aiff": AIFF}[suffix](path)
        if audio.tags is None:
            audio.add_tags()
        assert audio.tags is not None
        audio.tags.add(TIT2(encoding=3, text=["A new title"]))
        audio.tags.add(COMM(encoding=3, lang="eng", desc="", text=[LONG_COMMENT]))
        audio.save()


class Pair:
    """The server's old file and the client's retagged copy of the same audio."""

    def __init__(self, env: Env, tmp_path: Path, fmt: str = "flac", seconds: float = 1.0) -> None:
        self.env = env
        self.fmt = fmt
        old = make_audio(tmp_path / "old" / f"song.{fmt}", fmt, seconds=seconds, title="Old")
        self.old = old.read_bytes()
        self.local = tmp_path / "local" / f"song.{fmt}"
        self.local.parent.mkdir()
        self.local.write_bytes(self.old)
        retag(self.local)
        self.new = self.local.read_bytes()
        self.item = env.upload(f"rock/song.{fmt}", self.old)

    def parts(self) -> tuple[Span, bytes, bytes]:
        span = payload_span(self.local)
        assert span is not None
        prefix, suffix = read_tag_parts(self.local, span)
        return span, prefix, suffix

    def create(self, **override: Any) -> Any:
        span, prefix, _ = self.parts()
        body: dict[str, Any] = {
            "purpose": "item",
            "mode": "splice",
            "root_id": self.env.root_id,
            "relative_path": self.item["relative_path"],
            "size_bytes": len(self.new),
            "sha256": sha(self.new),
            "span_length": span.length,
            "span_sha256": span_sha256(self.local, span),
            "prefix_size": len(prefix),
            "base_item_id": self.item["item_id"],
            "base_revision": self.item["revision"],
        }
        body.update(override)
        body = {key: value for key, value in body.items() if value is not None}
        return self.env.client.post("/api/v1/uploads", json=body, headers=self.env.headers)

    def send(self, upload_id: str) -> int:
        _, prefix, suffix = self.parts()
        sent = prefix + suffix
        if sent:
            assert self.env.put(upload_id, sent, 0, len(sent)).status_code == 200
        return len(sent)

    def server_file(self) -> Path:
        return self.env.folder / self.item["relative_path"]


@pytest.mark.parametrize("fmt", ["flac", "mp3", "wav", "m4a", "aiff"])
def test_a_splice_rebuilds_the_clients_file_from_its_tag_parts(
    env: Env, tmp_path: Path, fmt: str
) -> None:
    pair = Pair(env, tmp_path, fmt, seconds=5.0)
    assert pair.new != pair.old
    created = pair.create()
    assert created.status_code == 201, created.text
    upload_id = created.json()["upload_id"]
    span = pair.parts()[0]
    # The upload is only the tag parts, whatever the final size is.
    assert created.json()["size_bytes"] == len(pair.new) - span.length
    assert pair.send(upload_id) == created.json()["size_bytes"]
    if fmt == "wav":
        assert created.json()["size_bytes"] < len(pair.new) // 10

    committed = env.commit(upload_id)
    assert committed.status_code == 200, committed.text
    item = committed.json()["item"]
    assert (item["revision"], item["sha256"], item["size_bytes"]) == (
        2,
        sha(pair.new),
        len(pair.new),
    )
    assert pair.server_file().read_bytes() == pair.new
    assert env.status(upload_id)["state"] == "done"
    assert not list((env.library / ".mtee-tmp" / "uploads").iterdir())
    # The old revision went to the server trash, byte for byte.
    entries = env.trash_entries()
    assert len(entries) == 1
    trashed = list((env.library / ".mtee-trash").rglob(f"song.{fmt}"))
    assert [path.read_bytes() for path in trashed] == [pair.old]
    assert env.kinds() == ["added", "replaced"]


def test_a_splice_can_be_sent_in_two_chunks_and_resumed(env: Env, tmp_path: Path) -> None:
    pair = Pair(env, tmp_path)
    upload_id = pair.create().json()["upload_id"]
    _, prefix, suffix = pair.parts()
    sent = prefix + suffix
    half = len(sent) // 2
    assert env.put(upload_id, sent[:half], 0, len(sent)).status_code == 200
    assert env.status(upload_id)["received_bytes"] == half
    assert env.put(upload_id, sent[half:], half, len(sent)).status_code == 200
    assert env.commit(upload_id).status_code == 200
    assert pair.server_file().read_bytes() == pair.new


def test_the_server_hash_worker_reads_the_rebuilt_file(env: Env, tmp_path: Path) -> None:
    pair = Pair(env, tmp_path)
    upload_id = pair.create().json()["upload_id"]
    pair.send(upload_id)
    item = env.commit(upload_id).json()["item"]
    assert item["hash_state"] == "pending"


def test_a_different_payload_is_refused_and_nothing_changes(env: Env, tmp_path: Path) -> None:
    pair = Pair(env, tmp_path)
    created = pair.create(span_sha256=sha(b"other audio"))
    upload_id = created.json()["upload_id"]
    pair.send(upload_id)
    response = env.commit(upload_id)
    assert (response.status_code, error_code(response)) == (409, "splice_refused")
    assert "whole file" in response.json()["error"]["message"]
    assert pair.server_file().read_bytes() == pair.old
    item = env.client.get(f"/api/v1/items/{pair.item['item_id']}", headers=env.headers).json()
    assert item["revision"] == 1
    assert env.trash_entries() == []
    assert env.kinds() == ["added"]
    assert env.status(upload_id)["state"] == "cancelled"
    assert not list((env.library / ".mtee-tmp" / "uploads").iterdir())
    # The normal full upload of the same item still works afterwards.
    again = env.upload(
        pair.item["relative_path"], pair.new, base_item_id=pair.item["item_id"], base_revision=1
    )
    assert again["revision"] == 2
    assert pair.server_file().read_bytes() == pair.new


def test_a_payload_of_another_length_is_refused(env: Env, tmp_path: Path) -> None:
    pair = Pair(env, tmp_path)
    span = pair.parts()[0]
    # The client lies about the length (and so about the size of what it sends).
    created = pair.create(span_length=span.length - 1, prefix_size=len(pair.parts()[1]))
    assert created.status_code == 201
    upload_id = created.json()["upload_id"]
    size = created.json()["size_bytes"]
    assert env.put(upload_id, blob(size), 0, size).status_code == 200
    response = env.commit(upload_id)
    assert (response.status_code, error_code(response)) == (409, "splice_refused")
    assert pair.server_file().read_bytes() == pair.old


def test_a_wrong_final_sha256_is_refused_after_the_rebuild(env: Env, tmp_path: Path) -> None:
    pair = Pair(env, tmp_path)
    upload_id = pair.create(sha256=sha(b"not the file")).json()["upload_id"]
    pair.send(upload_id)
    response = env.commit(upload_id)
    assert (response.status_code, error_code(response)) == (409, "splice_refused")
    assert pair.server_file().read_bytes() == pair.old
    assert env.trash_entries() == []
    assert not list((env.library / ".mtee-tmp" / "uploads").iterdir())


def test_a_server_file_that_is_not_audio_is_refused(env: Env, tmp_path: Path) -> None:
    pair = Pair(env, tmp_path)
    # Another item whose stored bytes are not a known audio container.
    junk = blob(5000, "junk")
    junk_item = env.upload("junk.flac", junk)
    upload_id = pair.create(
        base_item_id=junk_item["item_id"], base_revision=1, relative_path="junk.flac"
    ).json()["upload_id"]
    pair.send(upload_id)
    response = env.commit(upload_id)
    assert (response.status_code, error_code(response)) == (409, "splice_refused")
    assert (env.folder / "junk.flac").read_bytes() == junk


def test_a_stale_base_revision_is_a_conflict_not_a_refusal(env: Env, tmp_path: Path) -> None:
    pair = Pair(env, tmp_path)
    upload_id = pair.create().json()["upload_id"]
    pair.send(upload_id)
    # Another device replaces the file first.
    other = blob(300, "other")
    env.upload(
        pair.item["relative_path"], other, base_item_id=pair.item["item_id"], base_revision=1
    )
    response = env.commit(upload_id)
    assert (response.status_code, error_code(response)) == (409, "conflict")
    assert env.status(upload_id)["state"] == "conflict"
    assert pair.server_file().read_bytes() == other


def test_fewer_bytes_than_promised_are_not_committed(env: Env, tmp_path: Path) -> None:
    pair = Pair(env, tmp_path)
    upload_id = pair.create().json()["upload_id"]
    _, prefix, suffix = pair.parts()
    sent = prefix + suffix
    assert env.put(upload_id, sent[:-1], 0, len(sent)).status_code == 200
    response = env.commit(upload_id)
    assert (response.status_code, error_code(response)) == (400, "bad_request")
    assert "bytes were received" in response.json()["error"]["message"]
    assert env.status(upload_id)["state"] == "open"
    assert pair.server_file().read_bytes() == pair.old
    # The missing byte arrives and the commit works.
    assert env.put(upload_id, sent[-1:], len(sent) - 1, len(sent)).status_code == 200
    assert env.commit(upload_id).status_code == 200
    assert pair.server_file().read_bytes() == pair.new


@pytest.mark.parametrize(
    "override",
    [
        {"base_item_id": None, "base_revision": None},  # a splice is always a replacement
        {"mode": "diff"},
        {"span_length": 10**9},  # longer than the file
        {"prefix_size": 10**9},  # more than the tag parts
        {"span_length": -1},
        {"span_sha256": "xyz"},
        {"span_sha256": None},
        {"prefix_size": None},
    ],
)
def test_a_bad_splice_request_is_refused_at_creation(
    env: Env, tmp_path: Path, override: dict[str, Any]
) -> None:
    pair = Pair(env, tmp_path)
    response = pair.create(**override)
    assert (response.status_code, error_code(response)) == (400, "bad_request")
    assert not list((env.library / ".mtee-tmp" / "uploads").iterdir())


def test_splice_fields_need_the_splice_mode(env: Env, tmp_path: Path) -> None:
    pair = Pair(env, tmp_path)
    response = pair.create(mode="full")
    assert (response.status_code, error_code(response)) == (400, "bad_request")
    # With mode "full" and none of the splice fields it is a normal replacement.
    span, prefix, _ = pair.parts()
    body = {
        "purpose": "item",
        "mode": "full",
        "root_id": env.root_id,
        "relative_path": pair.item["relative_path"],
        "size_bytes": len(pair.new),
        "sha256": sha(pair.new),
        "base_item_id": pair.item["item_id"],
        "base_revision": 1,
    }
    created = env.client.post("/api/v1/uploads", json=body, headers=env.headers)
    assert created.status_code == 201
    assert created.json()["size_bytes"] == len(pair.new)
    assert span.length > 0 and prefix


def test_the_quota_counts_the_rebuilt_file_not_only_the_bytes_sent(
    env: Env, tmp_path: Path
) -> None:
    pair = Pair(env, tmp_path)
    conn = env.app.state.db.conn()
    # The old file is replaced, so the user needs room for the final file only.
    conn.execute(
        "UPDATE users SET quota_bytes = ? WHERE user_id = ?", (len(pair.new) - 1, env.user_id)
    )
    conn.commit()
    response = pair.create()
    assert (response.status_code, error_code(response)) == (413, "quota_exceeded")
    conn.execute("UPDATE users SET quota_bytes = ? WHERE user_id = ?", (len(pair.new), env.user_id))
    conn.commit()
    assert pair.create().status_code == 201
