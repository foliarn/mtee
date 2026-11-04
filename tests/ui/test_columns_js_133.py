"""Unit tests of the track list column fitting in columns.js (plan 133.1 and 133.2).

The functions run through a QJSEngine, the same engine that runs the QML, so the tests check the
exact arithmetic the table uses.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from PySide6.QtQml import QJSEngine

SCRIPT = Path(__file__).resolve().parents[2] / "src" / "mtee" / "qml" / "components" / "columns.js"
GAP = 16


def _evaluate(engine: QJSEngine, text: str) -> Any:
    return cast(Any, engine.evaluate(text))


def _engine() -> QJSEngine:
    engine = QJSEngine()
    result = _evaluate(engine, SCRIPT.read_text(encoding="utf-8"))
    assert not result.isError(), result.toString()
    return engine


def _call(engine: QJSEngine, expression: str) -> Any:
    result = _evaluate(engine, f"JSON.stringify({expression})")
    assert not result.isError(), result.toString()
    return json.loads(result.toString())


def _fit(engine: QJSEngine, columns: list[tuple[str, int]], available: float, gap: float = GAP):
    payload = json.dumps([{"key": key, "width": width} for key, width in columns])
    return _call(engine, f"fitColumns({payload}, {available}, {gap})")


def _keys(fit: dict[str, Any]) -> list[str]:
    return [item["key"] for item in fit["items"]]


def _widths(fit: dict[str, Any]) -> dict[str, float]:
    return {item["key"]: item["width"] for item in fit["items"]}


def _used(fit: dict[str, Any], gap: float = GAP) -> float:
    return sum(item["width"] for item in fit["items"]) + (len(fit["items"]) + 1) * gap


COLUMNS = [("title", 0), ("artist", 150), ("album", 150), ("bpm", 52), ("key", 52)]


def test_when_everything_fits_every_column_is_kept_and_the_title_takes_the_rest(qapp) -> None:
    engine = _engine()
    fit = _fit(engine, COLUMNS, 900)

    assert _keys(fit) == ["title", "artist", "album", "bpm", "key"]
    assert fit["hidden"] == []
    assert _widths(fit)["artist"] == 150
    assert _widths(fit)["bpm"] == 52
    # The title absorbs the leftover, so the last column ends exactly at the right edge.
    assert _used(fit) == 900


def test_the_first_column_that_does_not_fit_and_all_after_it_are_hidden(qapp) -> None:
    engine = _engine()
    # Title (its 140 minimum), Artist (its 150) and Album fit in 520 px; BPM would need 572 px.
    fit = _fit(engine, COLUMNS, 520)

    assert _keys(fit) == ["title", "artist", "album"]
    assert fit["hidden"] == ["bpm", "key"]
    assert _used(fit) <= 520 + 0.001


def test_a_column_after_a_hidden_one_is_not_kept_even_if_it_is_narrow(qapp) -> None:
    engine = _engine()
    columns = [("title", 0), ("album", 300), ("key", 40)]
    fit = _fit(engine, columns, 420)

    # The album does not fit, so the narrow key that would fit is hidden too.
    assert _keys(fit) == ["title"]
    assert fit["hidden"] == ["album", "key"]


def test_only_title_and_artist_remain_when_the_window_is_narrow(qapp) -> None:
    engine = _engine()
    fit = _fit(engine, COLUMNS, 300)

    assert _keys(fit) == ["title", "artist"]
    assert fit["hidden"] == ["album", "bpm", "key"]
    assert _used(fit) == 300


def test_the_action_cell_follows_artist_when_only_title_and_artist_remain(qapp) -> None:
    engine = _engine()
    # The room between the play slot and the action cell of an 800 px table: 800 - 24 - 32 - 140.
    fit = _fit(engine, [("title", 300), ("artist", 150)], 604)
    assert _keys(fit) == ["title", "artist"]
    items = json.dumps(fit["items"])
    left = _call(engine, f"actionsLeft({items}, 800, 12, 32, 140, {GAP})")
    widths = _widths(fit)
    # Title absorbs the room, so the action cell starts one gap after Artist and ends at the edge.
    assert left == 12 + 32 + GAP + widths["title"] + GAP + widths["artist"] + GAP
    assert left + 140 == 800 - 12

    full = _fit(engine, COLUMNS, 900)
    right = _call(engine, f"actionsLeft({json.dumps(full['items'])}, 1000, 12, 32, 140, {GAP})")
    assert right == 1000 - 12 - 140


def test_below_the_minimums_artist_shrinks_before_title(qapp) -> None:
    engine = _engine()
    # Title's minimum is 140 and Artist's 44: with 250 px for both, Artist gives way first.
    fit = _fit(engine, [("title", 0), ("artist", 150)], 250 + 3 * GAP)
    widths = _widths(fit)
    assert widths["title"] == 140
    assert widths["artist"] == 110

    # Below both minimums Artist is at its floor and Title takes what is left.
    tight = _fit(engine, [("title", 0), ("artist", 150)], 100 + 3 * GAP)
    tight_widths = _widths(tight)
    assert tight_widths["artist"] == 44
    assert tight_widths["title"] < 140
    assert tight_widths["title"] >= 40


def test_a_title_with_its_own_width_still_absorbs_the_leftover(qapp) -> None:
    engine = _engine()
    # The stored width does not fix the drawn width: Title takes the room left over (plan 133.3).
    fit = _fit(engine, [("title", 300), ("artist", 150)], 900)
    widths = _widths(fit)
    assert widths["artist"] == 150
    assert widths["title"] == 900 - 3 * GAP - 150
    assert _used(fit) == 900

    shrunk = _fit(engine, [("title", 600), ("artist", 150)], 500)
    assert _widths(shrunk)["title"] == 500 - 3 * GAP - 150
    assert _used(shrunk) == 500


def test_a_narrower_artist_is_kept_at_its_own_width_when_there_is_room(qapp) -> None:
    engine = _engine()
    fit = _fit(engine, [("title", 0), ("artist", 44)], 600)
    assert _widths(fit)["artist"] == 44
    assert _widths(fit)["title"] == 600 - 3 * GAP - 44


# resizeBoundary(columns, k, delta, available): the border on the right of column k moves by delta.
# The widths are passed without gaps; available is the room the widths share.
def _boundary(
    engine: QJSEngine, columns: list[tuple[str, int]], k: int, delta: float, available: float
):
    payload = json.dumps([{"key": key, "width": width} for key, width in columns])
    return _widths(
        {"items": _call(engine, f"resizeBoundary({payload}, {k}, {delta}, {available})")}
    )


def _sum(widths: dict[str, float]) -> float:
    return sum(widths.values())


ROW = [("title", 300), ("artist", 150), ("album", 150), ("bpm", 52)]


def test_growing_a_column_takes_the_room_from_the_column_on_its_right(qapp) -> None:
    engine = _engine()
    widths = _boundary(engine, ROW, 1, 60, 652)
    assert widths == {"title": 300, "artist": 210, "album": 90, "bpm": 52}
    assert _sum(widths) == 652


def test_the_cascade_goes_to_the_next_column_when_the_nearest_is_at_its_minimum(qapp) -> None:
    engine = _engine()
    # Album is at its minimum of 44, so the 100 px come from BPM after the 56 px that album gives.
    columns = [("title", 300), ("artist", 150), ("album", 100), ("bpm", 100)]
    widths = _boundary(engine, columns, 1, 90, 650)
    assert widths == {"title": 300, "artist": 240, "album": 44, "bpm": 66}
    assert _sum(widths) == 650


def test_growth_stops_at_the_hard_right_limit(qapp) -> None:
    engine = _engine()
    columns = [("title", 300), ("artist", 150), ("album", 44), ("bpm", 44)]
    widths = _boundary(engine, columns, 1, 200, 538)
    # The columns on the right have 0 room left above their minimums, so artist cannot grow.
    assert widths == {"title": 300, "artist": 150, "album": 44, "bpm": 44}
    assert _sum(widths) == 538


def test_shrinking_gives_the_freed_room_to_the_nearest_column_on_the_right(qapp) -> None:
    engine = _engine()
    widths = _boundary(engine, ROW, 1, -80, 652)
    assert widths == {"title": 300, "artist": 70, "album": 230, "bpm": 52}
    assert _sum(widths) == 652


def test_shrinking_stops_at_the_minimum_of_the_dragged_column(qapp) -> None:
    engine = _engine()
    widths = _boundary(engine, ROW, 1, -500, 652)
    assert widths["artist"] == 44
    assert _sum(widths) == 652


def test_title_cannot_be_squeezed_under_its_minimum(qapp) -> None:
    engine = _engine()
    # Title is the dragged column and shrinks only to 140.
    widths = _boundary(engine, [("title", 300), ("artist", 150)], 0, -400, 450)
    assert widths["title"] == 140
    assert _sum(widths) == 450


def test_a_title_on_the_right_is_a_donor_down_to_its_minimum(qapp) -> None:
    engine = _engine()
    columns = [("artist", 150), ("album", 150), ("title", 200)]
    widths = _boundary(engine, columns, 0, 300, 500)
    # Album gives 106 (to 44); title gives its 60 down to 140, so artist grows by 166 only.
    assert widths["title"] == 140
    assert widths["album"] == 44
    assert widths["artist"] == 150 + 106 + 60
    assert _sum(widths) == 500


def test_the_last_column_has_no_border_to_drag(qapp) -> None:
    engine = _engine()
    assert _boundary(engine, ROW, 3, 40, 652) == {
        "title": 300,
        "artist": 150,
        "album": 150,
        "bpm": 52,
    }


def test_the_widest_column_stops_at_its_ceiling(qapp) -> None:
    engine = _engine()
    widths = _boundary(engine, [("artist", 600), ("album", 300), ("bpm", 52)], 0, 200, 1200)
    assert widths["artist"] == 640
