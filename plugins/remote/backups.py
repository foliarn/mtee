"""Database backups of MTEE Remote (plan 126.8).

A backup is a copy of the MTEE database made by ``context.database_snapshot`` on a job thread, in
``base_dir/backups``. It is uploaded as a resumable backup upload (``purpose`` ``backup``) and the
local copy is removed once the server has committed it. The upload id, the copy and the sum are
kept in the plugin settings (``backup_pending``), so a cut upload resumes on the next try with the
same bytes. A restore downloads a backup into ``base_dir/restore``, checks its SHA-256 and offers
it to MTEE through ``context.database_snapshot.request_restore``: MTEE asks the person and applies
the restore at the next start, with its safety copies. This module never replaces the database.

The schedule (``backup_schedule``: daily, weekly or off, daily by default) is checked by the sync
engine after each pass: ``is_due`` says whether the last automatic backup (``last_auto_backup_utc``)
is older than the schedule, and ``run_automatic`` makes it. A failure waits an hour before the next
try, so a refused server is not sent a copy of the database every minute.

Every function here runs on a job thread (the snapshot and the restore request refuse the graphical
thread). Nothing is written to the graphical thread's files.
"""

from __future__ import annotations

import contextlib
import hashlib
import threading
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from mtee.domain.jobs import JobCancelledError
from mtee.plugins.api import JobContext, PluginContext

from .client import ApiError, NetworkError, RemoteClient, UploadOffsetError
from .store import RemoteStore, utc_now, write_log

DAILY = "daily"
WEEKLY = "weekly"
OFF = "off"
SCHEDULES = (DAILY, WEEKLY, OFF)
MANUAL = "manual"
AUTOMATIC = "automatic"

SCHEDULE_KEY = "backup_schedule"
LAST_AUTO_KEY = "last_auto_backup_utc"
RETRY_KEY = "backup_retry_utc"
PENDING_KEY = "backup_pending"
BACKUPS_DIR = "backups"
RESTORE_DIR = "restore"

DEFAULT_CHUNK_BYTES = 8 * 1024 * 1024
RETRY_DELAY = timedelta(hours=1)
MAX_DAILY = 365
MAX_WEEKLY = 104
_PERIODS = {DAILY: timedelta(days=1), WEEKLY: timedelta(days=7)}
_STALL_LIMIT = 3
_HASH_CHUNK_BYTES = 1024 * 1024
_UNREADABLE = "The server answered with something MTEE cannot read."

# One backup at a time: the pending record is one setting, and a second copy would overwrite it.
_LOCK = threading.Lock()


class BackupError(Exception):
    """A backup step that cannot go on; the message is the readable sentence for the person."""

    readable = True


# -- schedule and settings ---------------------------------------------------------------------


def schedule(context: PluginContext) -> str:
    """The automatic schedule: daily unless the setting says weekly or off."""
    value = context.settings.get(SCHEDULE_KEY, DAILY)
    return value if value in SCHEDULES else DAILY


def set_schedule(context: PluginContext, value: str) -> None:
    if value not in SCHEDULES:
        raise ValueError("The backup schedule must be Daily, Weekly or Off.")
    context.settings.set(SCHEDULE_KEY, value)


def last_automatic(context: PluginContext) -> datetime | None:
    """When the last automatic backup was committed, or None when there was none."""
    return _parse(context.settings.get(LAST_AUTO_KEY))


def is_due(context: PluginContext, now: datetime | None = None) -> bool:
    """Whether an automatic backup should be made now (the schedule says so and no retry waits)."""
    period = _PERIODS.get(schedule(context))
    if period is None:
        return False
    moment = now if now is not None else datetime.now(UTC)
    last = last_automatic(context)
    if last is not None and moment - last < period:
        return False
    retry = _parse(context.settings.get(RETRY_KEY))
    return retry is None or moment >= retry


def keep_counts(client: RemoteClient) -> dict[str, int]:
    """How many daily and weekly backups the server keeps: ``{"daily", "weekly"}``."""
    return client.backup_settings()


def set_keep(client: RemoteClient, *, daily: int, weekly: int) -> dict[str, int]:
    """Store how many daily (0 to 365) and weekly (0 to 104) backups the server keeps."""
    if not 0 <= daily <= MAX_DAILY:
        raise ValueError(f"The daily backups kept must be from 0 to {MAX_DAILY}.")
    if not 0 <= weekly <= MAX_WEEKLY:
        raise ValueError(f"The weekly backups kept must be from 0 to {MAX_WEEKLY}.")
    return client.put_backup_settings(daily, weekly)


# -- making a backup ---------------------------------------------------------------------------


def make_backup(
    context: PluginContext,
    client: RemoteClient,
    job: JobContext,
    *,
    kind: str,
    label: str | None = None,
    chunk_bytes: int = DEFAULT_CHUNK_BYTES,
) -> dict[str, Any]:
    """Make a backup of the database now, upload it and return the server's record of it.

    ``kind`` is ``manual`` or ``automatic``. A pending copy of the same kind and label (a cut
    upload) is sent again from the bytes the server holds; any other pending copy is dropped first.
    The local copy is removed after the server committed it. The commit is logged in ``remote_log``.
    """
    if kind not in (MANUAL, AUTOMATIC):
        raise ValueError("The backup kind must be manual or automatic.")
    with _LOCK:
        pending = _pending(context)
        if pending is not None and not _matches(pending, kind, label):
            _drop(context, client, pending)
            pending = None
        if pending is None:
            pending = _new_pending(context, kind, label)
        backup = _upload(context, client, job, pending, chunk_bytes)
        _finish(context, pending, backup)
        return backup


def run_automatic(context: PluginContext, client: RemoteClient, job: JobContext) -> None:
    """The automatic backup of the schedule. A failure is logged and retried after an hour.

    A network failure is not logged here: the connection state shows it, and the next pass retries.
    """
    try:
        make_backup(context, client, job, kind=AUTOMATIC)
    except (JobCancelledError, NetworkError):
        raise
    except Exception as error:
        context.settings.set(RETRY_KEY, _iso(datetime.now(UTC) + RETRY_DELAY))
        _log(context, f"The automatic backup failed: {_readable(error)}", "warning")
        raise


def _pending(context: PluginContext) -> dict[str, Any] | None:
    value = context.settings.get_json(PENDING_KEY, None)
    if not isinstance(value, dict):
        return None
    required = ("path", "sha256", "size", "kind")
    return value if all(key in value for key in required) else None


def _matches(pending: dict[str, Any], kind: str, label: str | None) -> bool:
    return (
        pending.get("kind") == kind
        and pending.get("label") == label
        and Path(str(pending["path"])).is_file()
    )


def _new_pending(context: PluginContext, kind: str, label: str | None) -> dict[str, Any]:
    path = _snapshot(context)
    try:
        size = path.stat().st_size
        digest = _sha256_of(path)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    pending: dict[str, Any] = {
        "path": str(path),
        "sha256": digest,
        "size": size,
        "kind": kind,
        "label": label,
        "upload_id": None,
        "created_utc": utc_now(),
    }
    context.settings.set_json(PENDING_KEY, pending)
    return pending


def _snapshot(context: PluginContext) -> Path:
    """A consistent copy of the database in ``base_dir/backups``, named by its UTC time."""
    folder = context.base_dir / BACKUPS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = folder / f"{stamp}.db"
    index = 2
    while target.exists():
        target = folder / f"{stamp}-{index}.db"
        index += 1
    return Path(context.database_snapshot.snapshot(target))


def _upload(
    context: PluginContext,
    client: RemoteClient,
    job: JobContext,
    pending: dict[str, Any],
    chunk_bytes: int,
) -> dict[str, Any]:
    """Resume the upload the server holds, or open one; send the bytes; commit; return the record.

    An upload the server holds as ``done`` was committed before this run could record it: its
    record is the result.
    """
    held = pending.get("upload_id")
    status = _status(client, held) if isinstance(held, str) else None
    state = None if status is None else status.get("state")
    if state == "done":
        return _committed(client, pending)
    if state in ("open", "conflict") and isinstance(held, str):
        upload_id = held
        offset = _count(status.get("received_bytes")) if status is not None else 0
    else:
        opened = client.open_backup_upload(
            size_bytes=int(pending["size"]),
            sha256=str(pending["sha256"]),
            kind=str(pending["kind"]),
            label=pending.get("label"),
        )
        upload_id = str(opened["upload_id"])
        pending["upload_id"] = upload_id
        context.settings.set_json(PENDING_KEY, pending)
        offset = 0
    _send(
        client,
        job,
        Path(str(pending["path"])),
        upload_id,
        offset,
        int(pending["size"]),
        chunk_bytes,
    )
    parsed = client.commit_upload(upload_id)
    backup = parsed.get("backup")
    if not isinstance(backup, dict):
        raise ApiError(200, "bad_response", _UNREADABLE)
    return backup


def _status(client: RemoteClient, upload_id: str) -> dict[str, Any] | None:
    """The state of an upload; None when the server does not know it any more."""
    try:
        return client.upload_status(upload_id)
    except ApiError as error:
        if error.status == 404:
            return None
        raise


def _committed(client: RemoteClient, pending: dict[str, Any]) -> dict[str, Any]:
    """The server's record of a backup it committed earlier (the same bytes, the same kind)."""
    for backup in client.backups():
        if backup.get("sha256") == pending["sha256"] and backup.get("kind") == pending["kind"]:
            return backup
    return {"sha256": pending["sha256"], "kind": pending["kind"], "size_bytes": pending["size"]}


def _send(
    client: RemoteClient,
    job: JobContext,
    path: Path,
    upload_id: str,
    offset: int,
    size: int,
    chunk_bytes: int,
) -> None:
    """Send the bytes of the copy from ``offset`` on, one chunk at a time; cancel between two."""
    stalls = 0
    with path.open("rb") as handle:
        while offset < size:
            job.raise_if_cancelled()
            handle.seek(offset)
            data = handle.read(min(chunk_bytes, size - offset))
            if not data:
                raise BackupError("The copy of the database is shorter than it was. Try again.")
            try:
                offset = client.upload_chunk(upload_id, offset, data, size)
            except UploadOffsetError as error:
                # The server holds other bytes: continue where it stands, not where this run was.
                stalls = stalls + 1 if error.offset == offset else 0
                if stalls > _STALL_LIMIT:
                    raise ApiError(
                        416,
                        "range_not_satisfiable",
                        "The server keeps refusing the bytes of this backup.",
                    ) from None
                offset = error.offset


def _finish(context: PluginContext, pending: dict[str, Any], backup: dict[str, Any]) -> None:
    """Forget the pending copy, remove its local file, and record the backup in the log."""
    context.settings.delete(PENDING_KEY)
    Path(str(pending["path"])).unlink(missing_ok=True)
    if pending["kind"] == AUTOMATIC:
        context.settings.set(LAST_AUTO_KEY, utc_now())
        context.settings.delete(RETRY_KEY)
    size = size_text(int(backup.get("size_bytes") or pending["size"]))
    kind = "automatic" if pending["kind"] == AUTOMATIC else "manual"
    _log(context, f"Saved a {kind} database backup on the server ({size}).")


def _drop(context: PluginContext, client: RemoteClient, pending: dict[str, Any]) -> None:
    """Forget a pending copy that no longer matches the request: cancel its upload, delete it."""
    upload_id = pending.get("upload_id")
    if isinstance(upload_id, str):
        with contextlib.suppress(ApiError, NetworkError):
            client.cancel_upload(upload_id)
    Path(str(pending["path"])).unlink(missing_ok=True)
    context.settings.delete(PENDING_KEY)


# -- restoring a backup ------------------------------------------------------------------------


def restore(context: PluginContext, client: RemoteClient, job: JobContext, backup_id: str) -> Path:
    """Download a backup, verify its SHA-256 and offer it to MTEE's restore; return its file.

    A download whose bytes do not match raises ``DownloadError`` (readable) and offers nothing.
    The file stays in ``base_dir/restore`` until the person has answered MTEE's question.
    """
    if not backup_id.isalnum():
        raise BackupError("This backup has no valid identifier.")
    listed = {str(item.get("backup_id")): item for item in client.backups()}
    entry = listed.get(backup_id)
    if entry is None:
        raise BackupError("This backup is no longer on the server.")
    target = context.base_dir / RESTORE_DIR / f"{backup_id}.db"
    client.download_backup(backup_id, target, expected_sha256=str(entry.get("sha256", "")), job=job)
    context.database_snapshot.request_restore(target)
    _log(context, "A database backup was offered to restore, and waits for your confirmation.")
    return target


# -- what the page shows -----------------------------------------------------------------------


def backup_rows(
    raw: Sequence[Mapping[str, Any]], device_names: Mapping[str, str]
) -> list[dict[str, Any]]:
    """The rows of the backup list: date, kind, device, size; newest first, as the server sends."""
    rows: list[dict[str, Any]] = []
    for item in raw:
        created = _parse(item.get("created_at_utc"))
        size = item.get("size_bytes")
        rows.append(
            {
                "backupId": str(item.get("backup_id", "")),
                "when": _when_text(created),
                "kind": "Automatic" if item.get("kind") == AUTOMATIC else "Manual",
                "device": device_names.get(str(item.get("device_id", "")), "Unknown device"),
                "size": size_text(size if isinstance(size, int) else 0),
            }
        )
    return rows


def last_backup_text(raw: Sequence[Mapping[str, Any]]) -> str:
    """The line under 'Back up now': the newest backup and its size, or that there is none."""
    if not raw:
        return (
            "No backup on the server yet. It holds playlists, play history, analysis, "
            "tag corrections and settings."
        )
    newest = raw[0]
    size = newest.get("size_bytes")
    return (
        f"Last backup: {_when_text(_parse(newest.get('created_at_utc')))}, "
        f"{size_text(size if isinstance(size, int) else 0)}. It holds playlists, play history, "
        "analysis, tag corrections and settings."
    )


def size_text(size: int) -> str:
    """A size as the page shows it: bytes, KB, MB or GB."""
    if size < 1024:
        return f"{size} B"
    if size < 1024**2:
        return f"{size / 1024:.0f} KB"
    if size < 1024**3:
        return f"{size / 1024**2:.0f} MB"
    return f"{size / 1024**3:.1f} GB"


# -- helpers -----------------------------------------------------------------------------------


def _when_text(moment: datetime | None) -> str:
    if moment is None:
        return "Unknown date"
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")


def _parse(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _readable(error: BaseException) -> str:
    message = getattr(error, "message", None)
    if isinstance(message, str) and message:
        return message
    return str(error) or type(error).__name__


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _log(context: PluginContext, text: str, level: str = "info") -> None:
    store = RemoteStore(context)
    with store.transaction() as conn:
        write_log(conn, text, level)
