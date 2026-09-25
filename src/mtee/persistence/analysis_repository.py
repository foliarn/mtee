"""Transactional persistence for calculated analyses and manual confirmations."""

from __future__ import annotations

import json
from typing import Any

from mtee.domain.analysis import (
    AnalysisMetric,
    AnalysisOverride,
    AnalysisResult,
)
from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database

__all__ = ["AnalysisRepository"]


class AnalysisRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def begin_run(self, run_id: str, track_id: str, revision: SourceRevision) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO analysis_runs(run_id,track_id,source_size_bytes,source_mtime_ns,"
                "source_file_id,source_generation,status) VALUES(?,?,?,?,?,?,'running')",
                (
                    run_id,
                    track_id,
                    revision.size_bytes,
                    revision.mtime_ns,
                    revision.file_id,
                    revision.generation,
                ),
            )

    def save_result(self, result: AnalysisResult) -> None:
        revision = result.source_revision
        metrics = [
            {"name": item.name, "value": item.value, "unit": item.unit} for item in result.metrics
        ]
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO analysis_results(result_id,run_id,track_id,analyzer,analyzer_version,"
                "source_size_bytes,source_mtime_ns,source_file_id,source_generation,config_json,"
                "status,metrics_json,segments_json,diagnostics,coverage,created_at_utc) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    result.result_id,
                    result.run_id,
                    result.track_id,
                    result.analyzer,
                    result.analyzer_version,
                    revision.size_bytes,
                    revision.mtime_ns,
                    revision.file_id,
                    revision.generation,
                    json.dumps(result.config, sort_keys=True),
                    result.status.value,
                    json.dumps(metrics, allow_nan=False),
                    json.dumps(result.segments, allow_nan=False),
                    result.diagnostics,
                    result.coverage,
                    result.created_at_utc,
                ),
            )

    def finish_run(self, run_id: str, status: str) -> None:
        if status not in {"succeeded", "partial", "failed", "cancelled"}:
            raise ValueError(f"Unsupported analysis run state: {status}")
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE analysis_runs SET status=?,finished_at_utc="
                "strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                "WHERE run_id=?",
                (status, run_id),
            )

    def results(self, track_id: str) -> list[dict[str, Any]]:
        rows = (
            self._database.connection()
            .execute(
                "SELECT * FROM analysis_results WHERE track_id=? "
                "ORDER BY created_at_utc DESC,result_id DESC",
                (track_id,),
            )
            .fetchall()
        )
        latest: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = dict(row)
            if item["analyzer"] not in latest:
                item["config"] = json.loads(item.pop("config_json"))
                item["metrics"] = json.loads(item.pop("metrics_json"))
                item["segments"] = json.loads(item.pop("segments_json"))
                latest[item["analyzer"]] = item
        return list(latest.values())

    def save_override(self, override: AnalysisOverride) -> None:
        rev = override.source_revision
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE analysis_overrides SET active=0 WHERE track_id=? "
                "AND field_name=? AND active=1",
                (override.track_id, override.field_name),
            )
            connection.execute(
                "INSERT INTO analysis_overrides(override_id,track_id,field_name,value_json,"
                "source_size_bytes,source_mtime_ns,source_file_id,source_generation,"
                "active,created_at_utc) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    override.override_id,
                    override.track_id,
                    override.field_name,
                    json.dumps(override.value, allow_nan=False),
                    rev.size_bytes,
                    rev.mtime_ns,
                    rev.file_id,
                    rev.generation,
                    int(override.active),
                    override.created_at_utc,
                ),
            )

    def clear_override(self, track_id: str, field_name: str) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE analysis_overrides SET active=0 WHERE track_id=? "
                "AND field_name=? AND active=1",
                (track_id, field_name),
            )

    def overrides(self, track_id: str) -> list[dict[str, Any]]:
        rows = (
            self._database.connection()
            .execute(
                "SELECT * FROM analysis_overrides WHERE track_id=? "
                "ORDER BY created_at_utc DESC,override_id DESC",
                (track_id,),
            )
            .fetchall()
        )
        return [{**dict(row), "value": json.loads(row["value_json"])} for row in rows]


def result_from_row(row: dict[str, Any]) -> tuple[AnalysisMetric, ...]:
    """Convert stored metric JSON to typed metric contracts."""
    return tuple(
        AnalysisMetric(str(item["name"]), item.get("value"), str(item.get("unit", "")))
        for item in json.loads(row.get("metrics_json", "[]"))
    )
