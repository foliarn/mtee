"""Track rows sort by Camelot code: number, then letter (1A, 1B, ..., 12A, 12B)."""

from __future__ import annotations

from typing import Any

from mtee.models.workspace_rows import sort_rows

_CAMELOT_ORDER = [f"{number}{letter}" for number in range(1, 13) for letter in "AB"]


def _row(title: str, key_camelot: str, key: str | None = None) -> dict[str, Any]:
    return {
        "id": f"id-{title}",
        "title": title,
        "key": key_camelot if key is None else key,
        "keyCamelot": key_camelot,
    }


def _codes(rows: list[dict[str, Any]]) -> list[str]:
    return [str(row["keyCamelot"]) for row in rows]


def _titles(rows: list[dict[str, Any]]) -> list[str]:
    return [str(row["title"]) for row in rows]


def test_key_sort_ascending_orders_numbers_before_letters() -> None:
    # Reversed input, so the result cannot come from the input order.
    rows = [_row(code, code) for code in reversed(_CAMELOT_ORDER)]

    assert _codes(sort_rows(rows, "key", True)) == _CAMELOT_ORDER


def test_key_sort_puts_ten_after_nine() -> None:
    rows = [_row("ten", "10A"), _row("nine", "9B")]

    assert _titles(sort_rows(rows, "key", True)) == ["nine", "ten"]


def test_key_sort_descending_is_the_exact_reverse_of_ascending() -> None:
    rows = [_row(code, code) for code in _CAMELOT_ORDER[5:] + _CAMELOT_ORDER[:5]]

    ascending = _codes(sort_rows(rows, "key", True))
    descending = _codes(sort_rows(rows, "key", False))

    assert ascending == _CAMELOT_ORDER
    assert descending == _CAMELOT_ORDER[::-1]


def test_rows_without_a_camelot_code_go_last_in_title_order() -> None:
    rows = [
        _row("Zed", "", key=""),
        _row("Bravo", "2A"),
        _row("Alpha", "", key=""),
        _row("Charlie", "13A", key="13A"),
        _row("Delta", "1B"),
    ]

    ascending = sort_rows(rows, "key", True)
    descending = sort_rows(rows, "key", False)

    assert _titles(ascending) == ["Delta", "Bravo", "Alpha", "Charlie", "Zed"]
    # Missing values stay last in both directions.
    assert _titles(descending) == ["Bravo", "Delta", "Alpha", "Charlie", "Zed"]


def test_key_sort_reads_lowercase_letters_as_their_camelot_letter() -> None:
    rows = [
        _row("B", "8B"),
        _row("A", "8a"),
        _row("C", "1b"),
        _row("D", "1A"),
    ]

    assert _codes(sort_rows(rows, "key", True)) == ["1A", "1b", "8a", "8B"]


def test_key_sort_falls_back_to_the_key_field_when_camelot_is_empty() -> None:
    rows = [
        _row("Classic", "", key="9b"),
        _row("Minor name", "", key="Am"),
        _row("Eight", "8A"),
    ]

    result = sort_rows(rows, "key", True)

    # "Am" is a classic name, not a Camelot code, so it has no position and goes last.
    assert _titles(result) == ["Eight", "Classic", "Minor name"]


def test_key_sort_keeps_title_order_for_equal_codes_in_both_directions() -> None:
    rows = [_row("second", "8A"), _row("first", "8a")]

    assert _titles(sort_rows(rows, "key", True)) == ["first", "second"]
    assert _titles(sort_rows(rows, "key", False)) == ["first", "second"]
