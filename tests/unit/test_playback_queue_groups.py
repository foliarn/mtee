from __future__ import annotations

from typing import Any

from PySide6.QtCore import QModelIndex, QObject, Signal

from mtee.models.playback_queue_model import PlaybackQueueModel, _with_groups


def _row(entry_id: str, origin: str) -> dict[str, Any]:
    return {"entryId": entry_id, "origin": origin, "id": entry_id}


def test_the_leading_manual_run_is_next_and_everything_after_it_is_from() -> None:
    rows = [
        _row("m1", "manual"),
        _row("m2", "manual"),
        _row("c1", "context"),
        _row("m3", "manual"),  # moved into the context: no new header, shown in its place
        _row("c2", "context"),
    ]
    assert [row["queueGroup"] for row in _with_groups(rows)] == [
        "next",
        "next",
        "from",
        "from",
        "from",
    ]


def test_without_manual_additions_only_the_context_section_exists() -> None:
    rows = [_row("c1", "context"), _row("c2", "context")]
    assert {row["queueGroup"] for row in _with_groups(rows)} == {"from"}
    assert _with_groups([]) == []


def test_the_input_rows_are_not_modified() -> None:
    rows = [_row("m1", "manual")]
    _with_groups(rows)
    assert "queueGroup" not in rows[0]


class _Service(QObject):
    queueChanged = Signal()  # noqa: N815 - Qt naming

    def __init__(self) -> None:
        super().__init__()
        self.rows = [_row("m1", "manual"), _row("c1", "context")]

    def up_next(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.rows]

    def queue_rows(self) -> list[dict[str, Any]]:
        return [{**row, "current": False} for row in self.rows]


def test_the_upcoming_model_exposes_the_group_as_a_role(qapp) -> None:
    service = _Service()
    model = PlaybackQueueModel(service, upcoming_only=True)  # type: ignore[arg-type]
    names = {bytes(name.data()).decode(): role for role, name in model.roleNames().items()}
    assert {"modelData", "queueGroup"} <= set(names)
    first, second = model.index(0, 0, QModelIndex()), model.index(1, 0, QModelIndex())
    assert model.data(first, names["queueGroup"]) == "next"
    assert model.data(second, names["queueGroup"]) == "from"
    assert model.data(first, names["modelData"])["entryId"] == "m1"


def test_the_full_queue_model_has_no_groups(qapp) -> None:
    model = PlaybackQueueModel(_Service())  # type: ignore[arg-type]
    names = {bytes(name.data()).decode(): role for role, name in model.roleNames().items()}
    assert model.data(model.index(0, 0, QModelIndex()), names["queueGroup"]) == ""


def test_a_refresh_with_the_same_rows_does_not_reset_the_model(qapp) -> None:
    service = _Service()
    model = PlaybackQueueModel(service, upcoming_only=True)  # type: ignore[arg-type]
    resets: list[int] = []
    model.modelReset.connect(lambda: resets.append(1))
    service.queueChanged.emit()
    model.refresh()
    assert resets == []
    service.rows.append(_row("c2", "context"))
    model.refresh()
    assert resets == [1]
