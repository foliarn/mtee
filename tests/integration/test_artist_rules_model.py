"""The artist name rules of the Settings Library page: read and removed through the real store."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from mtee.domain.artist_index import MODE_ONE_ARTIST, MODE_SPLIT
from mtee.models.artist_rules_model import ArtistRulesModel
from mtee.persistence.credit_override_repository import CreditOverrideRepository
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.artist_index_service import ArtistIndexService
from mtee.services.jobs import JobService


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db = Database(tmp_path / "data" / "mtee.sqlite3")
    db.migrate()
    yield db
    db.close()


def _model(qapp, database: Database) -> tuple[ArtistRulesModel, JobService]:
    jobs = JobService(qapp, max_thread_count=1)
    index = ArtistIndexService(
        LibraryRepository(database), CreditOverrideRepository(database), jobs
    )
    return ArtistRulesModel(index), jobs


def test_the_rules_show_the_name_and_the_decision(qapp, database: Database) -> None:
    overrides = CreditOverrideRepository(database)
    overrides.set_mode("Alpha & Beta", MODE_SPLIT)
    overrides.set_mode("Duo", MODE_ONE_ARTIST)
    model, jobs = _model(qapp, database)
    try:
        rules = {rule["text"]: rule for rule in cast(list[dict[str, str]], model.rules)}

        assert set(rules) == {"Alpha & Beta", "Duo"}
        assert rules["Alpha & Beta"]["decision"] == "Split into separate artists"
        assert rules["Duo"]["decision"] == "This is one artist"
        assert rules["Duo"]["id"] == "duo"
    finally:
        assert jobs.wait_for_done(10_000)
        jobs.shutdown(1_000)


def test_removing_a_rule_forgets_it_in_the_store(qapp, database: Database) -> None:
    overrides = CreditOverrideRepository(database)
    overrides.set_mode("Alpha & Beta", MODE_SPLIT)
    overrides.set_mode("Duo", MODE_ONE_ARTIST)
    model, jobs = _model(qapp, database)
    try:
        model.removeRule("alpha & beta")

        assert [rule["text"] for rule in cast(list[dict[str, str]], model.rules)] == ["Duo"]
        assert "grouped automatically again" in cast(str, model.message)
        assert [row["text"] for row in overrides.all()] == ["Duo"]
    finally:
        assert jobs.wait_for_done(10_000)
        jobs.shutdown(1_000)


def test_removing_a_missing_rule_says_so_and_changes_nothing(qapp, database: Database) -> None:
    CreditOverrideRepository(database).set_mode("Duo", MODE_ONE_ARTIST)
    model, jobs = _model(qapp, database)
    try:
        model.removeRule("nobody")

        assert model.message == "That rule no longer exists."
        assert [rule["text"] for rule in cast(list[dict[str, str]], model.rules)] == ["Duo"]
    finally:
        assert jobs.wait_for_done(10_000)
        jobs.shutdown(1_000)


def test_no_rule_gives_an_empty_list(qapp, database: Database) -> None:
    model, jobs = _model(qapp, database)
    try:
        assert model.rules == []
    finally:
        assert jobs.wait_for_done(10_000)
        jobs.shutdown(1_000)
