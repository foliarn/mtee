"""The one plugin list (plan 132.6): dedupe, order, tags and the letter tile, on plain rows."""

from __future__ import annotations

from mtee.models.plugin_list import plugin_list_rows


def _installed(plugin_id: str, title: str, status: str = "disabled") -> dict[str, object]:
    return {"id": plugin_id, "title": title, "status": status, "letter": title[:1]}


def _market(plugin_id: str, title: str, address: str = "official") -> dict[str, object]:
    return {"id": plugin_id, "title": title, "key": f"{plugin_id}@{address}", "letter": title[:1]}


def test_a_plugin_installed_and_listed_appears_once_as_the_installed_row() -> None:
    rows = plugin_list_rows(
        [_installed("hello", "Hello", "running")],
        [_market("hello", "Hello"), _market("hello", "Hello", "other")],
        {"hello"},
    )
    assert len(rows) == 1
    assert rows[0]["installed"] is True and rows[0]["key"] == "hello"
    assert rows[0]["tag"] == "Running" and rows[0]["tagTone"] == "primary"


def test_the_order_is_listed_installed_then_other_installed_then_not_installed() -> None:
    rows = plugin_list_rows(
        [
            _installed("zeta_other", "Zeta other"),
            _installed("beta", "Beta"),
            _installed("gamma", "Gamma"),
        ],
        [_market("delta", "Delta"), _market("beta", "Beta"), _market("alpha", "Alpha")],
        {"beta", "delta", "alpha"},
    )
    assert [row["pluginId"] for row in rows] == ["beta", "gamma", "zeta_other", "alpha", "delta"]


def test_the_groups_are_sorted_by_name_without_case() -> None:
    rows = plugin_list_rows(
        [_installed("b", "bravo"), _installed("a", "Alpha")],
        [],
        {"a", "b"},
    )
    assert [row["title"] for row in rows] == ["Alpha", "bravo"]


def test_a_tag_is_shown_only_for_an_installed_plugin() -> None:
    rows = plugin_list_rows(
        [
            _installed("ran", "Ran", "running"),
            _installed("broke", "Broke", "failed"),
            _installed("off", "Off", "disabled"),
            _installed("restart", "Restart", "restart"),
        ],
        [_market("new", "New")],
        set(),
    )
    tags = {row["pluginId"]: (row["tag"], row["tagTone"], row["warning"]) for row in rows}
    assert tags["ran"] == ("Running", "primary", False)
    assert tags["broke"] == ("Failed", "warning", True)
    assert tags["off"] == ("Installed", "neutral", False)
    assert tags["restart"] == ("Installed", "neutral", False)
    assert tags["new"] == ("", "neutral", False)


def test_a_plugin_listed_by_two_marketplaces_is_one_row_with_the_first_offer() -> None:
    rows = plugin_list_rows(
        [],
        [_market("dup", "Dup", "first"), _market("dup", "Dup", "second")],
        {"dup"},
    )
    assert len(rows) == 1
    assert rows[0]["key"] == "dup@first" and rows[0]["installed"] is False


def test_the_letter_is_the_first_letter_of_the_title_in_capitals() -> None:
    rows = plugin_list_rows([], [{"id": "x", "title": " weather", "key": "x@a"}], set())
    assert rows[0]["letter"] == "W"
