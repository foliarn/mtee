"""The drag payload keeps model order and the same rules the QML walk used to apply."""

from __future__ import annotations

from mtee.models.track_list_model import TrackListModel


def _row(identity: str, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": identity,
        "trackId": f"track-{identity}",
        "entryId": f"entry-{identity}",
        "title": f"Title {identity}",
        "artist": f"Artist {identity}",
        "available": True,
    }
    row.update(extra)
    return row


def test_payload_follows_model_order_and_skips_empty_entries(qapp) -> None:
    model = TrackListModel()
    model.replace(
        [
            _row("1"),
            _row("2", available=False),
            _row("3", entryId=""),
            _row("4"),
        ]
    )

    payload = model.dragPayload(["4", "3", "2"], False)

    assert payload["count"] == 3
    assert payload["title"] == "Title 2"
    assert payload["artist"] == "Artist 2"
    assert payload["trackIds"] == ["2", "3", "4"]
    assert payload["entryIds"] == ["entry-2", "entry-4"]
    assert payload["canAdd"] is False


def test_playlist_payload_uses_track_ids_and_can_add_when_all_available(qapp) -> None:
    model = TrackListModel()
    model.replace([_row("1"), _row("2")])

    payload = model.dragPayload(["2", "1"], True)

    assert payload["trackIds"] == ["track-1", "track-2"]
    assert payload["entryIds"] == ["entry-1", "entry-2"]
    assert payload["canAdd"] is True


def test_payload_with_no_chosen_row_is_empty(qapp) -> None:
    model = TrackListModel()
    model.replace([_row("1")])

    payload = model.dragPayload(["missing"], False)

    assert payload["count"] == 0
    assert payload["trackIds"] == []
    assert payload["entryIds"] == []
    assert payload["title"] == ""
    assert payload["artist"] == ""
