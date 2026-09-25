"""Durable conversion attempt journal and source lineage."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mtee.domain.conversion import ConversionResult, ConversionSettings, ConversionSource
from mtee.domain.tracks import sha256_of_file
from mtee.persistence.database import Database
from mtee.persistence.library_repository import normalize_path

__all__ = ["DerivationsRepository"]


class DerivationsRepository:
    """Record conversion state and completed derivation lineage transactionally."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def prepare(
        self,
        conversion_id: str,
        source: ConversionSource,
        destination: str,
        settings: ConversionSettings,
        ffmpeg_version: str,
        temporary_path: str = "",
        derived_track_id: str = "",
    ) -> None:
        """Commit an attempt before starting FFmpeg so interruption leaves a trace."""
        parameters = {name: getattr(settings, name) for name in settings.__dataclass_fields__}
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO conversion_attempts(conversion_id,source_track_id,source_path,"
                "destination_path,source_size_bytes,source_mtime_ns,source_file_id,"
                "source_generation,parameters_json,ffmpeg_version,status,temporary_path,"
                "derived_track_id,destination_path_key) "
                "VALUES(?,?,?,?,?,?,?,?,?,?, 'running',?,?,?)",
                (
                    conversion_id,
                    source.track_id,
                    str(source.path),
                    destination,
                    source.revision.size_bytes,
                    source.revision.mtime_ns,
                    source.revision.file_id,
                    source.revision.generation,
                    json.dumps(parameters, sort_keys=True),
                    ffmpeg_version,
                    temporary_path,
                    derived_track_id,
                    normalize_path(destination),
                ),
            )

    def record_verified_output(
        self,
        conversion_id: str,
        source_sha256: str,
        output_sha256: str,
        temporary_path: str,
        output_probe: Any,
        metadata_report: tuple[tuple[str, str], ...],
    ) -> None:
        """Persist proof of the verified temporary before publishing it."""
        validation = {
            "codec": str(output_probe.codec),
            "duration_us": output_probe.duration_us,
            "sample_rate": output_probe.sample_rate,
            "channels": output_probe.channels,
            "bits_per_sample": output_probe.bits_per_sample,
            "metadata_report": list(metadata_report),
        }
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE conversion_attempts SET source_sha256=?,output_sha256=?,"
                "temporary_path=?,validation_json=?,updated_at_utc=? "
                "WHERE conversion_id=? AND status='running'",
                (
                    source_sha256,
                    output_sha256,
                    temporary_path,
                    json.dumps(validation, sort_keys=True),
                    datetime.now(UTC).isoformat(timespec="seconds"),
                    conversion_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("The conversion journal is no longer running.")

    def record(self, result: ConversionResult, ffmpeg_version: str) -> None:
        """Upsert a result and its lineage after output publication."""
        derivation = result.derivation
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO conversion_attempts(conversion_id,source_track_id,source_path,"
                "destination_path,destination_path_key,source_size_bytes,source_mtime_ns,source_file_id,"
                "source_generation,source_sha256,output_sha256,parameters_json,ffmpeg_version,"
                "status,validation_json,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(conversion_id) DO UPDATE SET source_sha256=excluded.source_sha256,"
                "output_sha256=excluded.output_sha256,status=excluded.status,"
                "validation_json=excluded.validation_json,updated_at_utc=excluded.updated_at_utc",
                (
                    result.conversion_id,
                    result.source_track_id,
                    str(result.source),
                    str(result.destination),
                    normalize_path(result.destination),
                    derivation.source_revision.size_bytes if derivation else 0,
                    derivation.source_revision.mtime_ns if derivation else 0,
                    derivation.source_revision.file_id if derivation else None,
                    derivation.source_revision.generation if derivation else 0,
                    result.source_sha256,
                    result.output_sha256,
                    json.dumps(dict(derivation.parameters) if derivation else {}, sort_keys=True),
                    ffmpeg_version,
                    result.status,
                    json.dumps(
                        {
                            "message": result.message,
                            "codec": result.output_probe.codec if result.output_probe else "",
                            "duration_us": (
                                result.output_probe.duration_us if result.output_probe else None
                            ),
                        },
                        sort_keys=True,
                    ),
                    datetime.now(UTC).isoformat(timespec="seconds"),
                ),
            )
            if derivation is not None and result.status == "completed":
                connection.execute(
                    "INSERT INTO derivations(derived_track_id,source_track_id,source_size_bytes,"
                    "source_mtime_ns,source_file_id,source_generation,conversion_id,"
                    "parameters_json,time_mapping_status) VALUES(?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(derived_track_id) DO NOTHING",
                    (
                        derivation.derived_track_id,
                        derivation.source_track_id,
                        derivation.source_revision.size_bytes,
                        derivation.source_revision.mtime_ns,
                        derivation.source_revision.file_id,
                        derivation.source_revision.generation,
                        derivation.conversion_id,
                        json.dumps(dict(derivation.parameters), sort_keys=True),
                        derivation.time_mapping_status,
                    ),
                )

    def attempts(self) -> list[dict[str, Any]]:
        with self._database.connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM conversion_attempts ORDER BY created_at_utc,conversion_id"
                )
            ]

    def incomplete_attempts(self) -> list[dict[str, Any]]:
        with self._database.connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM conversion_attempts WHERE status IN ('prepared','running') "
                    "ORDER BY created_at_utc,conversion_id"
                )
            ]

    def recover_incomplete(self) -> list[dict[str, Any]]:
        """Recover only outputs whose pre-publication proof matches the final bytes."""
        issues: list[dict[str, Any]] = []
        for attempt in self.incomplete_attempts():
            destination = attempt["destination_path"]
            expected_hash = str(attempt.get("output_sha256", ""))
            derived_track_id = str(attempt.get("derived_track_id", ""))
            matched = False
            if expected_hash and str(attempt.get("source_sha256", "")) and derived_track_id:
                path = Path(str(destination))
                try:
                    matched = path.is_file() and sha256_of_file(path) == expected_hash
                except OSError:
                    matched = False
            if matched:
                self._record_recovered(attempt)
                issues.append(
                    {
                        "track_id": str(attempt["source_track_id"]),
                        "destination_path": str(destination),
                        "status": "recovered",
                        "message": "A matching published output was recovered from its journal proof.",
                    }
                )
            else:
                issues.append(
                    {
                        "track_id": str(attempt["source_track_id"]),
                        "destination_path": str(destination),
                        "temporary_path": str(attempt.get("temporary_path", "")),
                        "status": "needs_inspection",
                        "message": (
                            "An interrupted conversion has no matching final-output proof. "
                            "Existing files and temporary files were left unchanged."
                        ),
                    }
                )
        return issues

    def _record_recovered(self, attempt: dict[str, Any]) -> None:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE conversion_attempts SET status='completed',updated_at_utc=? "
                "WHERE conversion_id=? AND status IN ('prepared','running')",
                (now, str(attempt["conversion_id"])),
            )
            connection.execute(
                "INSERT INTO derivations(derived_track_id,source_track_id,source_size_bytes,"
                "source_mtime_ns,source_file_id,source_generation,conversion_id,parameters_json,"
                "time_mapping_status) VALUES(?,?,?,?,?,?,?,?, 'converted') "
                "ON CONFLICT(derived_track_id) DO NOTHING",
                (
                    str(attempt["derived_track_id"]),
                    str(attempt["source_track_id"]),
                    int(attempt["source_size_bytes"]),
                    int(attempt["source_mtime_ns"]),
                    attempt["source_file_id"],
                    int(attempt["source_generation"]),
                    str(attempt["conversion_id"]),
                    str(attempt["parameters_json"]),
                ),
            )

    def mark_status(self, conversion_id: str, status: str) -> None:
        if status not in {"failed", "cancelled", "conflict"}:
            raise ValueError(f"Unsupported attempt status: {status}")
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE conversion_attempts SET status=?,updated_at_utc=? WHERE conversion_id=?",
                (status, datetime.now(UTC).isoformat(timespec="seconds"), conversion_id),
            )

    def derivation(self, derived_track_id: str) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM derivations WHERE derived_track_id=?", (derived_track_id,)
            ).fetchone()
        return dict(row) if row is not None else None
