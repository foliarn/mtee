"""The desktop stream cache (plan 127.6): verified copies, eviction, clearing, and its own folder.

These tests use no server: a copy is a file whose SHA-256 the test computes. Each test works in its
own temporary folder, and a file outside the cache folder stands for a library file that must
never be touched.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from mtee.plugins.remote.cache import (  # pyright: ignore[reportMissingImports]
    INCOMING_DIR,
    StreamCache,
    cache_limit_gb,
    ext_of,
    open_cache,
    set_cache_limit_gb,
)

ITEM_A = "a" * 32
ITEM_B = "b" * 32
ITEM_C = "c" * 32
SIZE = 1000
GIB = 1024**3


def _bytes(seed: int) -> bytes:
    return bytes((seed * 31 + index) % 251 for index in range(SIZE))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _download(cache: StreamCache, item_id: str, data: bytes, name: str = "song.flac") -> Path:
    """Write ``data`` as a download of the incoming folder and return its path."""
    path = cache.incoming_dir() / f"{item_id}-{name}"
    path.write_bytes(data)
    return path


def _add(cache: StreamCache, item_id: str, data: bytes, mtime: float) -> Path:
    """Keep ``data`` as the copy of ``item_id`` with the given modification time."""
    kept = cache.add(item_id, _sha(data), _download(cache, item_id, data))
    assert kept is not None
    os.utime(kept, (mtime, mtime))
    return kept


def test_a_download_whose_sha256_matches_is_kept_and_found_by_lookup(tmp_path: Path) -> None:
    cache = StreamCache(tmp_path / "cache", GIB)
    data = _bytes(1)
    source = _download(cache, ITEM_A, data)

    kept = cache.add(ITEM_A, _sha(data), source)

    assert kept == cache.path_for(ITEM_A, _sha(data), ".flac")
    assert kept is not None and kept.read_bytes() == data
    assert not source.exists()  # moved, not copied
    assert cache.lookup(ITEM_A, _sha(data), ".flac") == kept
    assert cache.size() == SIZE


def test_a_download_with_another_sha256_is_discarded(tmp_path: Path) -> None:
    cache = StreamCache(tmp_path / "cache", GIB)
    source = _download(cache, ITEM_A, _bytes(2))

    kept = cache.add(ITEM_A, _sha(_bytes(3)), source)

    assert kept is None
    assert not source.exists()
    assert cache.size() == 0
    assert list(cache.folder.glob("*.flac")) == []


def test_a_copy_whose_bytes_changed_is_discarded_by_lookup(tmp_path: Path) -> None:
    cache = StreamCache(tmp_path / "cache", GIB)
    data = _bytes(4)
    kept = cache.add(ITEM_A, _sha(data), _download(cache, ITEM_A, data))
    assert kept is not None
    kept.write_bytes(b"damaged")

    assert cache.lookup(ITEM_A, _sha(data), ".flac") is None
    assert not kept.exists()


def test_lookup_misses_for_another_revision_of_the_item(tmp_path: Path) -> None:
    cache = StreamCache(tmp_path / "cache", GIB)
    _add(cache, ITEM_A, _bytes(5), mtime=1_000)

    assert cache.lookup(ITEM_A, _sha(_bytes(6)), ".flac") is None
    assert cache.size() == SIZE  # the other revision's copy is not removed by a lookup


def test_eviction_removes_the_least_recently_used_copies_until_under_the_limit(
    tmp_path: Path,
) -> None:
    oldest, middle, newest = _bytes(7), _bytes(8), _bytes(9)
    cache = StreamCache(tmp_path / "cache", 2 * SIZE)
    first = _add(cache, ITEM_A, oldest, mtime=1_000)
    second = _add(cache, ITEM_B, middle, mtime=2_000)
    third = _add(cache, ITEM_C, newest, mtime=3_000)
    assert cache.size() == 3 * SIZE

    removed = cache.evict()

    assert removed == 1
    assert not first.exists()
    assert second.exists() and third.exists()
    assert cache.size() == 2 * SIZE <= cache.limit_bytes


def test_a_lookup_keeps_a_copy_longer_than_one_that_was_not_played(tmp_path: Path) -> None:
    cache = StreamCache(tmp_path / "cache", 2 * SIZE)
    played = _add(cache, ITEM_A, _bytes(10), mtime=1_000)
    idle = _add(cache, ITEM_B, _bytes(11), mtime=2_000)
    _add(cache, ITEM_C, _bytes(12), mtime=3_000)
    # A play of the first copy makes it the most recent one: the idle copy goes first.
    assert cache.lookup(ITEM_A, _sha(_bytes(10)), ".flac") == played

    cache.evict()

    assert played.exists()
    assert not idle.exists()


def test_eviction_never_removes_the_copy_just_added(tmp_path: Path) -> None:
    cache = StreamCache(tmp_path / "cache", SIZE // 2)
    kept = _add(cache, ITEM_A, _bytes(13), mtime=1_000)

    assert cache.evict(keep=kept) == 0
    assert kept.exists()


def test_clear_removes_every_copy_and_partial_download_and_nothing_else(tmp_path: Path) -> None:
    cache = StreamCache(tmp_path / "cache", GIB)
    _add(cache, ITEM_A, _bytes(14), mtime=1_000)
    partial = cache.incoming_dir() / f"{ITEM_B}-song.flac.part"
    partial.write_bytes(b"partial")
    library = tmp_path / "library" / "song.flac"
    library.parent.mkdir()
    library.write_bytes(b"a library file")

    assert cache.clear() == 2
    assert cache.size() == 0
    assert not partial.exists()
    assert library.read_bytes() == b"a library file"


def test_size_counts_the_copies_and_not_the_partial_downloads(tmp_path: Path) -> None:
    cache = StreamCache(tmp_path / "cache", GIB)
    assert cache.size() == 0
    _add(cache, ITEM_A, _bytes(15), mtime=1_000)
    (cache.incoming_dir() / "partial.part").write_bytes(b"x" * 500)

    assert cache.size() == SIZE


def test_add_refuses_a_file_outside_the_incoming_folder_and_leaves_it(tmp_path: Path) -> None:
    cache = StreamCache(tmp_path / "cache", GIB)
    library_file = tmp_path / "Music" / "song.flac"
    library_file.parent.mkdir()
    data = _bytes(16)
    library_file.write_bytes(data)

    with pytest.raises(ValueError):
        cache.add(ITEM_A, _sha(_bytes(17)), library_file)  # a mismatch would delete it

    assert library_file.read_bytes() == data


def test_clear_and_eviction_touch_nothing_outside_the_folder(tmp_path: Path) -> None:
    cache = StreamCache(tmp_path / "cache", SIZE)
    outside = tmp_path / "Music" / "keep.flac"
    outside.parent.mkdir()
    outside.write_bytes(_bytes(18) * 5)
    _add(cache, ITEM_A, _bytes(19), mtime=1_000)
    _add(cache, ITEM_B, _bytes(20), mtime=2_000)

    cache.evict()
    cache.clear()

    assert outside.read_bytes() == _bytes(18) * 5


def test_a_path_is_refused_for_a_bad_identifier_hash_or_extension(tmp_path: Path) -> None:
    cache = StreamCache(tmp_path / "cache", GIB)

    with pytest.raises(ValueError):
        cache.path_for("../escape", _sha(b"x"), ".flac")
    with pytest.raises(ValueError):
        cache.path_for(ITEM_A, "not-a-sha", ".flac")
    with pytest.raises(ValueError):
        cache.path_for(ITEM_A, _sha(b"x"), "/flac")
    assert ext_of("Album/Track.FLAC") == ".flac"
    assert ext_of("odd name.x y") == ""


class _FakeSettings:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.values.get(key, default)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value


def _context(tmp_path: Path) -> Any:
    return SimpleNamespace(settings=_FakeSettings(), data_dir=tmp_path)


def test_the_size_limit_is_stored_in_gb_from_1_to_200_with_a_default_of_10(tmp_path: Path) -> None:
    context = _context(tmp_path)
    assert cache_limit_gb(context) == 10

    set_cache_limit_gb(context, 25)
    assert cache_limit_gb(context) == 25
    assert open_cache(context).limit_bytes == 25 * GIB
    assert open_cache(context).folder == tmp_path / "cache"

    for refused in (0, 201, True, 2.5):
        with pytest.raises(ValueError):
            set_cache_limit_gb(context, refused)  # type: ignore[arg-type]
    context.settings.set("cache_size_gb", "not a number")
    assert cache_limit_gb(context) == 10
    context.settings.set("cache_size_gb", "500")
    assert cache_limit_gb(context) == 200


def test_the_incoming_folder_is_inside_the_cache_folder(tmp_path: Path) -> None:
    cache = StreamCache(tmp_path / "cache", GIB)
    assert cache.incoming_dir() == tmp_path / "cache" / INCOMING_DIR
    assert cache.incoming_dir().is_dir()
