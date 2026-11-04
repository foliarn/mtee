"""The order of the Artists list (plan 132.5): each mode on the fixture index, and the saved mode.

The library and the index are the ones of ``test_artist_index_service``. The saved mode is the
workspace document: it goes through the same repository the application uses, so a restart reads
the same value back.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from tests.integration.test_artist_index_service import (  # noqa: F401  (fixture)
    _service,
    _settle,
    library_setup,
)

from mtee.domain.artist_index import ARTIST_SORT_KEYS, DEFAULT_ARTIST_SORT
from mtee.models.artist_index_model import ArtistListModel
from mtee.models.window_layout import Leaf
from mtee.models.workspace_session import build_session_snapshot
from mtee.persistence.database import Database
from mtee.persistence.workspace_repository import DEFAULT_WORKSPACE, WorkspaceRepository


@pytest.fixture
def indexed(qapp, request):
    """The library of the index tests, with its artist index built; yields (jobs, service)."""
    database, library, _music = request.getfixturevalue("library_setup")
    jobs, service = _service(qapp, database, library)
    _settle(qapp, service)
    yield jobs, service
    jobs.shutdown()


def _names_and_counts(model: ArtistListModel) -> list[tuple[str, int]]:
    untyped = cast(Any, model)
    rows = [model.data(model.index(row, 0)) for row in range(untyped.count)]
    return [(str(row["name"]), int(row["trackCount"])) for row in rows]


def test_each_mode_orders_the_fixture_index(indexed) -> None:
    _jobs, service = indexed
    artists = ArtistListModel(service)
    everything = _names_and_counts(artists)
    assert len(everything) >= 3

    artists.setSortMode("name")
    by_name = _names_and_counts(artists)
    assert [name.casefold() for name, _ in by_name] == sorted(
        (name.casefold() for name, _ in everything)
    )

    artists.setSortMode("nameDesc")
    assert _names_and_counts(artists) == list(reversed(by_name))

    artists.setSortMode("mostTracks")
    counts = [count for _, count in _names_and_counts(artists)]
    assert counts == sorted(counts, reverse=True)
    assert sorted(_names_and_counts(artists)) == sorted(everything)

    artists.setSortMode("fewestTracks")
    counts = [count for _, count in _names_and_counts(artists)]
    assert counts == sorted(counts)


def test_an_unknown_mode_is_ignored_and_the_filter_keeps_the_order(indexed) -> None:
    _jobs, service = indexed
    artists = ArtistListModel(service)
    artists.setSortMode("fewestTracks")
    artists.setSortMode("sideways")
    assert artists.sortMode == "fewestTracks"
    artists.setFilterText("chase")
    counts = [count for _, count in _names_and_counts(artists)]
    assert counts == sorted(counts)


def test_the_saved_mode_comes_back_after_a_restart(tmp_path) -> None:
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    try:
        repository = WorkspaceRepository(database)
        assert repository.load()["artistSort"] == DEFAULT_ARTIST_SORT
        state = build_session_snapshot(
            expanded=[],
            groups={"g1": {"tabs": [], "active": ""}},
            layout_tree=Leaf("g1"),
            tab_states={},
            selection_by_tab={},
            anchor_by_tab={},
            active_group="g1",
            activity="artists",
            sidebar_visible=True,
            right_visible=False,
            right_tab="info",
            sidebar_width=240,
            right_panel_width=360,
            preview_tabs=True,
            column_preferences=cast(dict, DEFAULT_WORKSPACE["columnPreferences"]),
            artist_sort="mostTracks",
        )
        repository.save(state)
        assert WorkspaceRepository(database).load()["artistSort"] == "mostTracks"
    finally:
        database.close()


def test_a_stored_mode_that_is_not_known_falls_back_to_a_to_z(tmp_path) -> None:
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    try:
        repository = WorkspaceRepository(database)
        state = dict(repository.load())
        state["artistSort"] = "upside-down"
        repository.save(state)
        assert repository.load()["artistSort"] == DEFAULT_ARTIST_SORT
        assert "name" in ARTIST_SORT_KEYS
    finally:
        database.close()
