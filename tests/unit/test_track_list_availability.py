"""The track filter "Hide tracks not on this device" (plan 125.3): the list model and the choice.

A plugin is stood in for by a record with a ``TrackAvailability`` contribution. Without a
provider nothing is asked and nothing is left out.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from PySide6.QtCore import Qt

from mtee.models.availability_filter import SETTING_HIDE_NOT_ON_DEVICE, AvailabilityFilter
from mtee.models.track_list_model import TrackListModel
from mtee.plugins.api import Availability, TrackAvailability
from mtee.plugins.availability_registry import TrackAvailabilityRegistry
from mtee.plugins.loader import LoadedPlugin, PluginStatus

_DATA_ROLE = int(Qt.ItemDataRole.UserRole) + 1
REMOTE_IDS = {"t2", "t4"}


class _Settings:
    """A stored value per key, like the settings repository for JSON values."""

    def __init__(self, stored: dict[str, Any] | None = None) -> None:
        self.values: dict[str, Any] = dict(stored or {})

    def get_json(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def set_json(self, key: str, value: Any) -> None:
        self.values[key] = value


class _Record:
    """Stands for a LoadedPlugin: the registry reads three attributes."""

    def __init__(self, plugin_id: str, contributions: Sequence[Any], status: PluginStatus) -> None:
        self.plugin_id = plugin_id
        self.title = plugin_id.title()
        self.status = status
        self.contributions = tuple(contributions)


def _provider(calls: list[tuple[str, ...]]) -> TrackAvailability:
    def status(track_ids: Sequence[str]) -> Mapping[str, Availability]:
        calls.append(tuple(track_ids))
        return {track_id: "remote" for track_id in track_ids if track_id in REMOTE_IDS}

    return TrackAvailability(status)


def _registry(calls: list[tuple[str, ...]] | None = None) -> TrackAvailabilityRegistry:
    registry = TrackAvailabilityRegistry()
    provider = _provider(calls if calls is not None else [])
    records = cast(Any, [_Record("remote", [provider], PluginStatus.RUNNING)])
    registry.register(cast(Sequence[LoadedPlugin], records))
    return registry


def _rows(*identities: str) -> list[dict[str, object]]:
    return [{"id": identity, "title": f"Title {identity}"} for identity in identities]


def _hidden(model: TrackListModel) -> int:
    return int(cast(Any, model).hiddenCount)


def _shown(model: TrackListModel) -> list[str]:
    return model.track_ids_snapshot()


def test_the_filter_hides_remote_rows_and_counts_them(qapp) -> None:
    calls: list[tuple[str, ...]] = []
    filter_ = AvailabilityFilter()
    filter_.attach(_registry(calls), _Settings({SETTING_HIDE_NOT_ON_DEVICE: True}))
    model = TrackListModel()
    model.set_hidden_ids(filter_.remote_ids)
    counts: list[int] = []
    model.rowsChanged.connect(lambda: counts.append(_hidden(model)))

    model.replace(_rows("t1", "t2", "t3", "t4"))
    assert _shown(model) == ["t1", "t3"]
    assert model.hiddenCount == 2
    assert model.rowCount() == 2
    assert [row["number"] for row in model.rows_snapshot()] == [1, 2]
    assert len(model.source_rows_snapshot()) == 4  # the hidden rows are kept
    assert calls and set(calls[-1]) == {"t1", "t2", "t3", "t4"}
    assert counts and counts[-1] == 2


def test_turning_the_filter_off_restores_the_rows(qapp) -> None:
    filter_ = AvailabilityFilter()
    settings = _Settings()
    filter_.attach(_registry(), settings)
    model = TrackListModel()
    model.set_hidden_ids(filter_.remote_ids)
    model.replace(_rows("t1", "t2", "t3", "t4"))
    assert model.hiddenCount == 0 and model.rowCount() == 4

    filter_.set_wanted(True)
    model.refresh_filter()
    assert _shown(model) == ["t1", "t3"] and model.hiddenCount == 2

    filter_.set_wanted(False)
    model.refresh_filter()
    assert _shown(model) == ["t1", "t2", "t3", "t4"]
    assert model.hiddenCount == 0
    assert settings.values[SETTING_HIDE_NOT_ON_DEVICE] is False


def test_the_choice_is_stored_and_read_back_at_the_next_start(qapp) -> None:
    settings = _Settings({SETTING_HIDE_NOT_ON_DEVICE: True})
    filter_ = AvailabilityFilter()
    filter_.attach(_registry(), settings)
    assert filter_.wanted is True and filter_.hiding is True
    filter_.set_wanted(False)
    assert settings.values[SETTING_HIDE_NOT_ON_DEVICE] is False


def test_without_a_provider_the_filter_has_no_effect_and_asks_nothing(qapp) -> None:
    settings = _Settings({SETTING_HIDE_NOT_ON_DEVICE: True})
    filter_ = AvailabilityFilter()
    filter_.attach(TrackAvailabilityRegistry(), settings)
    assert filter_.provided is False and filter_.hiding is False
    assert filter_.wanted is True  # the stored choice is kept for when a plugin provides it

    model = TrackListModel()
    model.set_hidden_ids(filter_.remote_ids)
    model.replace(_rows("t1", "t2"))
    assert _shown(model) == ["t1", "t2"]
    assert model.hiddenCount == 0


def test_a_list_without_a_filter_source_shows_everything(qapp) -> None:
    model = TrackListModel()
    model.replace(_rows("t1", "t2", "t4"))
    assert _shown(model) == ["t1", "t2", "t4"] and model.hiddenCount == 0


def test_the_provider_is_asked_only_when_the_filter_is_on(qapp) -> None:
    calls: list[tuple[str, ...]] = []
    filter_ = AvailabilityFilter()
    filter_.attach(_registry(calls), _Settings())
    model = TrackListModel()
    model.set_hidden_ids(filter_.remote_ids)
    model.replace(_rows("t1", "t2"))
    assert calls == []  # the filter is off: no question is asked


def test_a_change_of_some_tracks_refilters_only_lists_that_hold_them(qapp) -> None:
    calls: list[tuple[str, ...]] = []
    filter_ = AvailabilityFilter()
    filter_.attach(_registry(calls), _Settings({SETTING_HIDE_NOT_ON_DEVICE: True}))
    model = TrackListModel()
    model.set_hidden_ids(filter_.remote_ids)
    model.replace(_rows("t1", "t3"))
    asked = len(calls)

    model.refresh_filter({"t9"})  # none of its tracks changed
    assert len(calls) == asked
    model.refresh_filter({"t3"})
    assert len(calls) == asked + 1


def test_the_rows_of_a_plugin_list_are_judged_by_their_track_id(qapp) -> None:
    filter_ = AvailabilityFilter()
    filter_.attach(_registry(), _Settings({SETTING_HIDE_NOT_ON_DEVICE: True}))
    model = TrackListModel()
    model.set_hidden_ids(filter_.remote_ids)
    # A playlist entry has its own id; the track it plays is its trackId.
    model.replace(
        [
            {"id": "entry-1", "trackId": "t2", "title": "remote"},
            {"id": "entry-2", "trackId": "", "title": "unavailable"},
            {"id": "entry-3", "trackId": "t1", "title": "local"},
        ]
    )
    assert [row["title"] for row in model.rows_snapshot()] == ["unavailable", "local"]
    assert model.hiddenCount == 1


def test_a_failing_provider_leaves_every_track_shown(qapp) -> None:
    def broken(track_ids: Sequence[str]) -> Mapping[str, Availability]:
        raise OSError("the server is down")

    registry = TrackAvailabilityRegistry()
    records = cast(Any, [_Record("broken", [TrackAvailability(broken)], PluginStatus.RUNNING)])
    registry.register(cast(Sequence[LoadedPlugin], records))
    filter_ = AvailabilityFilter()
    filter_.attach(registry, _Settings({SETTING_HIDE_NOT_ON_DEVICE: True}))
    model = TrackListModel()
    model.set_hidden_ids(filter_.remote_ids)
    model.replace(_rows("t2", "t3"))
    assert _shown(model) == ["t2", "t3"] and model.hiddenCount == 0


def test_only_a_running_plugin_provides_availability(qapp) -> None:
    provider = _provider([])
    stopped = cast(Any, [_Record("stopped", [provider], PluginStatus.DISABLED)])
    registry = TrackAvailabilityRegistry()
    registry.register(cast(Sequence[LoadedPlugin], stopped))
    assert registry.provided is False
    assert registry.remote_ids(["t2"]) == frozenset()
