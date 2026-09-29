"""Permanent storage of the calculated tempo, key and waveform of tracks.

Results live beside, never inside, the tags written in the audio files. A value
the user edited is flagged; the flag keeps a later analysis from replacing it.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime

from mtee.domain.analysis import (
    ANALYSIS_ALGORITHM_VERSION,
    TrackAnalysis,
    durations_agree,
)
from mtee.domain.musical_key import MusicalKey
from mtee.domain.waveform import WaveformPoints
from mtee.persistence.database import Database

__all__ = ["AnalysisRepository"]

_CHUNK = 500
_FIELDS = {"bpm": "bpm_user_edited", "key": "key_user_edited"}


class AnalysisRepository:
    """Reads and writes the ``track_analysis`` and ``track_waveforms`` tables."""

    def __init__(self, database: Database) -> None:
        self._database = database

    # ------------------------------------------------------- tempo and key

    def get(self, track_id: str) -> TrackAnalysis | None:
        row = (
            self._database.connection()
            .execute("SELECT * FROM track_analysis WHERE track_id = ?", (track_id,))
            .fetchone()
        )
        return _analysis_from_row(row) if row is not None else None

    def get_many(self, track_ids: Iterable[str]) -> dict[str, TrackAnalysis]:
        identities = list(dict.fromkeys(track_ids))
        found: dict[str, TrackAnalysis] = {}
        connection = self._database.connection()
        for start in range(0, len(identities), _CHUNK):
            chunk = identities[start : start + _CHUNK]
            marks = ",".join("?" * len(chunk))
            for row in connection.execute(
                f"SELECT * FROM track_analysis WHERE track_id IN ({marks})", chunk
            ):
                found[str(row["track_id"])] = _analysis_from_row(row)
        return found

    def save_result(
        self,
        track_id: str,
        *,
        bpm: float | None,
        key: MusicalKey | None,
        source_duration_us: int | None,
    ) -> TrackAnalysis:
        """Store a fresh analysis; a value the user edited is left untouched."""
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO track_analysis (track_id, bpm, key_tonic, key_minor, "
                "source_duration_us, algorithm_version, analyzed_at_utc) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(track_id) DO UPDATE SET "
                "bpm = CASE WHEN bpm_user_edited = 1 THEN bpm ELSE excluded.bpm END, "
                "key_tonic = CASE WHEN key_user_edited = 1 THEN key_tonic "
                "ELSE excluded.key_tonic END, "
                "key_minor = CASE WHEN key_user_edited = 1 THEN key_minor "
                "ELSE excluded.key_minor END, "
                "source_duration_us = excluded.source_duration_us, "
                "algorithm_version = excluded.algorithm_version, "
                "analyzed_at_utc = excluded.analyzed_at_utc",
                (
                    track_id,
                    round(bpm, 3) if bpm is not None else None,
                    key.tonic if key is not None else None,
                    int(key.minor) if key is not None else None,
                    source_duration_us,
                    ANALYSIS_ALGORITHM_VERSION,
                    _now(),
                ),
            )
        stored = self.get(track_id)
        assert stored is not None
        return stored

    def mark_user_edited(self, track_ids: Iterable[str], field: str) -> None:
        """Flag ``field`` (``bpm`` or ``key``) as edited by the user for these tracks."""
        column = _FIELDS.get(field)
        if column is None:
            raise ValueError(f"only {sorted(_FIELDS)} can be flagged as edited")
        with self._database.transaction() as connection:
            for track_id in dict.fromkeys(track_ids):
                connection.execute(
                    f"INSERT INTO track_analysis (track_id, {column}) VALUES (?, 1) "
                    f"ON CONFLICT(track_id) DO UPDATE SET {column} = 1",
                    (track_id,),
                )

    def is_current(self, analysis: TrackAnalysis | None, current_duration_us: int | None) -> bool:
        """Return whether ``analysis`` is a complete result that still fits the audio."""
        return (
            analysis is not None
            and analysis.analyzed
            and analysis.algorithm_version == ANALYSIS_ALGORITHM_VERSION
            and durations_agree(analysis.source_duration_us, current_duration_us)
        )

    # ------------------------------------------------------------ waveform

    def save_waveform(
        self, track_id: str, points: WaveformPoints, source_duration_us: int | None
    ) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO track_waveforms (track_id, duration_us, source_duration_us, "
                "points, algorithm_version, computed_at_utc) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(track_id) DO UPDATE SET duration_us = excluded.duration_us, "
                "source_duration_us = excluded.source_duration_us, points = excluded.points, "
                "algorithm_version = excluded.algorithm_version, "
                "computed_at_utc = excluded.computed_at_utc",
                (
                    track_id,
                    points.duration_us,
                    source_duration_us,
                    points.to_bytes(),
                    ANALYSIS_ALGORITHM_VERSION,
                    _now(),
                ),
            )

    def load_waveform(
        self, track_id: str, current_duration_us: int | None
    ) -> WaveformPoints | None:
        """Return the stored waveform when it still fits the audio, else ``None``."""
        row = (
            self._database.connection()
            .execute(
                "SELECT duration_us, source_duration_us, points, algorithm_version "
                "FROM track_waveforms WHERE track_id = ?",
                (track_id,),
            )
            .fetchone()
        )
        if row is None or int(row["algorithm_version"]) != ANALYSIS_ALGORITHM_VERSION:
            return None
        if not durations_agree(row["source_duration_us"], current_duration_us):
            return None
        try:
            return WaveformPoints.from_bytes(int(row["duration_us"]), bytes(row["points"]))
        except ValueError:
            return None


def _analysis_from_row(row: sqlite3.Row) -> TrackAnalysis:
    tonic = row["key_tonic"]
    minor = row["key_minor"]
    key = MusicalKey(int(tonic), bool(minor)) if tonic is not None and minor is not None else None
    return TrackAnalysis(
        track_id=str(row["track_id"]),
        bpm=float(row["bpm"]) if row["bpm"] is not None else None,
        key=key,
        bpm_user_edited=bool(row["bpm_user_edited"]),
        key_user_edited=bool(row["key_user_edited"]),
        source_duration_us=row["source_duration_us"],
        algorithm_version=row["algorithm_version"],
        analyzed_at_utc=row["analyzed_at_utc"],
    )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
