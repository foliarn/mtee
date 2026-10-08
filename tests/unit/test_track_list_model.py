"""Incremental list updates preserve Qt views instead of resetting them."""

from __future__ import annotations

from PySide6.QtCore import Qt

from mtee.models.track_list_model import TrackListModel


def _track(identity: str, title: str) -> dict[str, object]:
    return {"id": identity, "title": title}


def test_replace_inserts_updates_moves_and_removes_without_model_reset(qapp) -> None:
    model = TrackListModel()
    resets: list[bool] = []
    model.modelReset.connect(lambda: resets.append(True))

    model.replace([_track(str(index), f"Track {index}") for index in range(100)])
    assert model.rowCount() == 100
    model.replace(
        [_track("84", "Renamed 84"), _track("100", "New track")]
        + [_track(str(index), f"Track {index}") for index in range(85, 100)]
    )

    assert model.track_ids_snapshot() == ["84", "100", *[str(i) for i in range(85, 100)]]
    assert model.rowCount() == 17
    first = model.data(model.index(0, 0), int(Qt.ItemDataRole.UserRole) + 1)
    assert first["title"] == "Renamed 84"
    assert not resets


def test_local_genre_labels_update_in_place_and_survive_reload(qapp) -> None:
    model = TrackListModel()
    resets: list[bool] = []
    model.modelReset.connect(lambda: resets.append(True))
    labels = ["House", "House \u203a Deep", "House \u203a Deep · Drum & Bass \u203a Jump Up"]
    rows = [
        dict(_track(str(i), f"Track {i}"), mteeGenres=[label]) for i, label in enumerate(labels)
    ]
    model.replace(rows)
    model.replace(rows)
    rows[0]["mteeGenres"] = ["House \u203a Minimal"]
    model.replace(rows)
    assert model.rows_snapshot()[0]["mteeGenres"] == ["House \u203a Minimal"]
    assert model.track_ids_snapshot() == ["0", "1", "2"]
    assert not resets
    reopened = TrackListModel()
    reopened.replace(model.rows_snapshot())
    assert reopened.rows_snapshot() == model.rows_snapshot()
