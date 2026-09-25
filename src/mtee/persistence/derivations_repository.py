"""Durable conversion attempt journal and source lineage."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from mtee.domain.conversion import ConversionResult, ConversionSettings, ConversionSource
from mtee.persistence.database import Database

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
    ) -> None:
        """Commit an attempt before starting FFmpeg so interruption leaves a trace."""
        parameters = {name: getattr(settings, name) for name in settings.__dataclass_fields__}
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO conversion_attempts(conversion_id,source_track_id,source_path,"
                "destination_path,source_size_bytes,source_mtime_ns,source_file_id,"
                "source_generation,parameters_json,ffmpeg_version,status) "
                "VALUES(?,?,?,?,?,?,?,?,?,?, 'running')",
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
                ),
            )

    def record(self, result: ConversionResult, ffmpeg_version: str) -> None:
        """Upsert a result and its lineage after output publication."""
        derivation = result.derivation
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO conversion_attempts(conversion_id,source_track_id,source_path,"
                "destination_path,source_size_bytes,source_mtime_ns,source_file_id,"
                "source_generation,source_sha256,output_sha256,parameters_json,ffmpeg_version,"
                "status,validation_json,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(conversion_id) DO UPDATE SET source_sha256=excluded.source_sha256,"
                "output_sha256=excluded.output_sha256,status=excluded.status,"
                "validation_json=excluded.validation_json,updated_at_utc=excluded.updated_at_utc",
                (
                    result.conversion_id,
                    result.source_track_id,
                    str(result.source),
                    str(result.destination),
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
