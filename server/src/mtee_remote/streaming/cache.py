"""The transcode cache: one complete file per (source hash, plan key) (plan 127.1).

Layout: `<cache_dir>/<sha256[:2]>/<sha256>/<key>.<ext>`. A transcode writes
`<final>.part-<uuid>` and is renamed to `<final>` only when ffmpeg has finished, so a file
without `.part-` is always complete.

- One transcode per (sha256, key) at a time: concurrent callers await the same task.
- At most `max_concurrent` ffmpeg processes at once; the others wait in a queue.
- A caller that goes away (client disconnect) cancels the transcode only when nobody else
  waits for it. `close()` cancels every running transcode and waits until ffmpeg has exited.
- LRU eviction by mtime (a cache hit touches the file), only under `cache_dir`. A `.part-`
  file younger than an hour is never evicted. The file just made is never evicted by the
  call that made it.
- `cache_dir` must not be the filesystem root, and must not overlap the music folder.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import stat
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from mtee_remote import tools
from mtee_remote.streaming import transcode
from mtee_remote.streaming.transcode import TranscodeError
from mtee_remote.streaming.types import DeliveryPlan

PART_MIN_AGE_S = 3600
_PART_MARK = ".part-"
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(eq=False)
class _Job:
    key: tuple[str, str]
    final: Path
    cancel: threading.Event
    task: asyncio.Task[Path]
    waiters: int = 0


class TranscodeCache:
    """Complete transcodes on disk, shared by every request."""

    def __init__(
        self,
        cache_dir: Path,
        *,
        max_concurrent: int,
        limit_bytes: int,
        ffmpeg: str | None = None,
        music_dir: Path | None = None,
    ) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1.")
        if limit_bytes < 0:
            raise ValueError("limit_bytes cannot be negative.")
        resolved = cache_dir.resolve()
        if resolved == Path(resolved.anchor):
            raise ValueError("The transcode cache cannot be the filesystem root.")
        if music_dir is not None:
            music = music_dir.resolve()
            if resolved.is_relative_to(music) or music.is_relative_to(resolved):
                raise ValueError("The transcode cache cannot overlap the music folder.")
        resolved.mkdir(parents=True, exist_ok=True)
        self._dir = cache_dir
        self._root = resolved
        self._limit = limit_bytes
        self._ffmpeg = ffmpeg
        self._slots = asyncio.Semaphore(max_concurrent)
        self._jobs: dict[tuple[str, str], _Job] = {}
        self._live: set[_Job] = set()
        self._closed = False

    def path_for(self, sha256: str, plan: DeliveryPlan) -> Path:
        """Return where the complete transcode of `sha256` for `plan` lives."""
        if not _SHA256.fullmatch(sha256):
            raise ValueError("The SHA-256 must be 64 lowercase hex characters.")
        return self._dir / sha256[:2] / sha256 / f"{plan.key}.{plan.ext}"

    async def ensure(self, source: Path, sha256: str, plan: DeliveryPlan) -> Path:
        """Return the complete cached file for `plan`, transcoding it first if needed."""
        if plan.send_original:
            raise ValueError("The original file is not cached: serve the source instead.")
        if self._closed:
            raise RuntimeError("The transcode cache is closed.")
        final = self.path_for(sha256, plan)
        if final.is_file():
            try:
                os.utime(final)
                return final
            except FileNotFoundError:
                pass  # evicted since the check: transcode it again
        key = (sha256, plan.key)
        job = self._jobs.get(key)
        if job is None:
            job = self._start(key, source, final, plan)
        job.waiters += 1
        try:
            return await asyncio.shield(job.task)
        finally:
            job.waiters -= 1
            if job.waiters == 0 and not job.task.done():
                # Nobody waits any more: stop the transcode and forget it, so a new request
                # starts a fresh one instead of waiting for this cancelled one.
                job.cancel.set()
                if self._jobs.get(key) is job:
                    del self._jobs[key]

    def _start(self, key: tuple[str, str], source: Path, final: Path, plan: DeliveryPlan) -> _Job:
        cancel = threading.Event()
        task = asyncio.get_running_loop().create_task(self._transcode(source, final, plan, cancel))
        job = _Job(key=key, final=final, cancel=cancel, task=task)
        self._jobs[key] = job
        self._live.add(job)
        task.add_done_callback(lambda done: self._finished(job, done))
        return job

    def _finished(self, job: _Job, done: asyncio.Task[Path]) -> None:
        self._live.discard(job)
        if self._jobs.get(job.key) is job:
            del self._jobs[job.key]
        if not done.cancelled():
            done.exception()  # mark it retrieved: a cancelled job has no waiter left

    async def _transcode(
        self, source: Path, final: Path, plan: DeliveryPlan, cancel: threading.Event
    ) -> Path:
        async with self._slots:
            if cancel.is_set():
                raise TranscodeError("The transcode was cancelled before it started.")
            final.parent.mkdir(parents=True, exist_ok=True)
            part = final.with_name(f"{final.name}{_PART_MARK}{uuid.uuid4().hex}")
            ffmpeg = self._ffmpeg or tools.ffmpeg_path()
            await asyncio.to_thread(
                transcode.run_transcode, ffmpeg, source, plan, part, cancel=cancel
            )
            os.replace(part, final)
        self.evict(keep=final)
        return final

    def evict(self, *, keep: Path | None = None) -> int:
        """Delete least recently used files until the cache is under its limit.

        Returns the bytes freed. Only files under the cache folder are touched. Young `.part-`
        files are skipped, and `keep` (the file just made) is never deleted. Empty folders
        are removed, except the folders of transcodes still running.
        """
        entries = list(_regular_files(self._dir))
        total = sum(info.st_size for _, info in entries)
        freed = 0
        if total > self._limit:
            now = time.time()
            candidates = sorted(
                (
                    entry
                    for entry in entries
                    if not (
                        _PART_MARK in entry[0].name and now - entry[1].st_mtime < PART_MIN_AGE_S
                    )
                ),
                key=lambda entry: entry[1].st_mtime,
            )
            for path, info in candidates:
                if total <= self._limit:
                    break
                if keep is not None and path == keep:
                    continue
                try:
                    path.unlink()
                except OSError:
                    continue
                total -= info.st_size
                freed += info.st_size
        protected = {job.final.parent for job in self._live}
        _remove_empty_dirs(self._dir, protected)
        return freed

    def clear_stale_parts(self) -> int:
        """Delete every `.part-` file: leftovers of a crash. Call it before serving starts.

        Returns the number of files deleted.
        """
        removed = 0
        for path, _info in _regular_files(self._dir):
            if _PART_MARK not in path.name:
                continue
            try:
                path.unlink()
            except OSError:
                continue
            removed += 1
        return removed

    async def close(self) -> None:
        """Cancel every running transcode and wait until ffmpeg has exited."""
        self._closed = True
        live = list(self._live)
        for job in live:
            job.cancel.set()
        if live:
            await asyncio.gather(*(job.task for job in live), return_exceptions=True)


def _regular_files(root: Path) -> Iterator[tuple[Path, os.stat_result]]:
    """Yield `(path, lstat)` for every regular file under `root`; symlinks are skipped."""
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            path = Path(dirpath, name)
            try:
                info = path.lstat()
            except OSError:
                continue
            if stat.S_ISREG(info.st_mode):
                yield path, info


def _remove_empty_dirs(root: Path, protected: set[Path]) -> None:
    """Remove empty folders under `root` (bottom-up), never `root` or a protected folder."""
    for dirpath, _dirnames, _filenames in os.walk(root, topdown=False):
        folder = Path(dirpath)
        if folder == root or folder in protected:
            continue
        if any(target.is_relative_to(folder) for target in protected):
            continue  # an ancestor of a folder in use
        with contextlib.suppress(OSError):  # not empty, or in use: keep it
            folder.rmdir()
