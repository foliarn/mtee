"""Tests of the center window tree and the dock state (plan 131.1)."""

from __future__ import annotations

import pytest

from mtee.models.window_layout import (
    DockState,
    Leaf,
    Split,
    groups,
    neighbour,
    node_from_dict,
    node_to_dict,
    remove,
    set_ratios,
    split,
)


def _single() -> Leaf:
    return Leaf("g1")


def test_split_right_creates_row_with_new_window_on_the_right() -> None:
    tree = split(_single(), "g1", "right", "g2")
    assert tree == Split("row", (Leaf("g1"), Leaf("g2")), (0.5, 0.5))


def test_split_left_puts_new_window_first() -> None:
    tree = split(_single(), "g1", "left", "g2")
    assert groups(tree) == ("g2", "g1")
    assert isinstance(tree, Split) and tree.orientation == "row"


def test_split_bottom_and_top_use_a_column() -> None:
    down = split(_single(), "g1", "bottom", "g2")
    up = split(_single(), "g1", "top", "g2")
    assert isinstance(down, Split) and down.orientation == "column"
    assert groups(down) == ("g1", "g2")
    assert groups(up) == ("g2", "g1")


def test_split_on_same_axis_is_flattened() -> None:
    tree = split(split(_single(), "g1", "right", "g2"), "g2", "right", "g3")
    assert isinstance(tree, Split)
    assert tree.orientation == "row"
    assert groups(tree) == ("g1", "g2", "g3")
    assert all(isinstance(child, Leaf) for child in tree.children)
    assert sum(tree.ratios) == pytest.approx(1.0)


def test_nested_split_on_other_axis_keeps_a_sub_split() -> None:
    tree = split(split(_single(), "g1", "right", "g2"), "g2", "bottom", "g3")
    assert isinstance(tree, Split)
    assert tree.orientation == "row"
    right = tree.children[1]
    assert isinstance(right, Split) and right.orientation == "column"
    assert groups(tree) == ("g1", "g2", "g3")


def test_split_unknown_group_or_duplicate_is_refused() -> None:
    with pytest.raises(ValueError):
        split(_single(), "missing", "right", "g2")
    with pytest.raises(ValueError):
        split(_single(), "g1", "right", "g1")
    with pytest.raises(ValueError):
        split(_single(), "g1", "diagonal", "g2")  # type: ignore[arg-type]


def test_remove_collapses_single_child_split() -> None:
    tree = split(_single(), "g1", "right", "g2")
    assert remove(tree, "g2") == Leaf("g1")


def test_remove_last_window_gives_none() -> None:
    assert remove(_single(), "g1") is None


def test_remove_middle_window_keeps_others_in_reading_order() -> None:
    tree = split(split(_single(), "g1", "right", "g2"), "g2", "right", "g3")
    after = remove(tree, "g2")
    assert after is not None
    assert groups(after) == ("g1", "g3")
    assert sum(after.ratios) == pytest.approx(1.0)  # type: ignore[union-attr]


def test_set_ratios_normalises_and_clamps_to_minimum() -> None:
    tree = split(_single(), "g1", "right", "g2")
    moved = set_ratios(tree, (), [0.99, 0.01], minimum=0.2)
    assert isinstance(moved, Split)
    assert moved.ratios[1] == pytest.approx(0.2)
    assert sum(moved.ratios) == pytest.approx(1.0)


def test_set_ratios_keeps_proportions_of_free_children() -> None:
    tree = split(split(_single(), "g1", "right", "g2"), "g2", "right", "g3")
    moved = set_ratios(tree, (), [0.6, 0.2, 0.2], minimum=0.1)
    assert isinstance(moved, Split)
    assert moved.ratios == pytest.approx((0.6, 0.2, 0.2))


def test_set_ratios_refuses_bad_input() -> None:
    tree = split(_single(), "g1", "right", "g2")
    with pytest.raises(ValueError):
        set_ratios(tree, (), [0.5], minimum=0.1)
    with pytest.raises(ValueError):
        set_ratios(tree, (), [0.5, 0.5], minimum=0.6)
    with pytest.raises(ValueError):
        set_ratios(tree, (), [-1.0, 2.0], minimum=0.1)
    with pytest.raises(ValueError):
        set_ratios(_single(), (), [1.0], minimum=0.1)


def test_neighbour_on_row_and_column() -> None:
    tree = split(split(_single(), "g1", "right", "g2"), "g2", "bottom", "g3")
    assert neighbour(tree, "g1", "right") == "g2"
    assert neighbour(tree, "g2", "left") == "g1"
    assert neighbour(tree, "g2", "bottom") == "g3"
    assert neighbour(tree, "g3", "top") == "g2"
    assert neighbour(tree, "g1", "left") is None
    assert neighbour(tree, "g3", "bottom") is None


def test_neighbour_enters_a_nested_sub_split_at_the_touching_leaf() -> None:
    tree = split(split(_single(), "g1", "right", "g2"), "g2", "bottom", "g3")
    assert neighbour(tree, "g1", "right") == "g2"


def test_groups_reading_order() -> None:
    tree = split(split(_single(), "g1", "bottom", "g2"), "g1", "right", "g3")
    assert groups(tree) == ("g1", "g3", "g2")


def test_round_trip_through_dict() -> None:
    tree = split(split(_single(), "g1", "right", "g2"), "g2", "bottom", "g3")
    assert node_from_dict(node_to_dict(tree)) == tree


@pytest.mark.parametrize(
    "data",
    [
        None,
        "nope",
        {"type": "unknown"},
        {"type": "leaf", "group": ""},
        {"type": "split", "orientation": "row", "children": [{"type": "leaf", "group": "g1"}]},
        {
            "type": "split",
            "orientation": "diagonal",
            "children": [{"type": "leaf", "group": "g1"}, {"type": "leaf", "group": "g2"}],
            "ratios": [0.5, 0.5],
        },
        {
            "type": "split",
            "orientation": "row",
            "children": [{"type": "leaf", "group": "g1"}, {"type": "leaf", "group": "g2"}],
            "ratios": [0.2, 0.2],
        },
        {
            "type": "split",
            "orientation": "row",
            "children": [{"type": "leaf", "group": "g1"}, {"type": "leaf", "group": "g1"}],
            "ratios": [0.5, 0.5],
        },
    ],
)
def test_invalid_tree_yields_one_default_leaf(data: object) -> None:
    assert node_from_dict(data) == Leaf("g1")


def test_dock_round_trip_and_clamping() -> None:
    dock = DockState(side="right", open=False, width=300, windows=("info", "queue"), ratio=0.3)
    assert DockState.from_dict("right", dock.to_dict()) == dock
    wide = DockState.from_dict("left", {"width": 10_000, "windows": ["a", "b", "c"]})
    assert wide.width == 480
    assert wide.windows == ("a", "b")
    narrow = DockState.from_dict("left", {"width": 1})
    assert narrow.width == 220


def test_dock_invalid_fields_fall_back_to_defaults() -> None:
    assert DockState.from_dict("left", "bad") == DockState(side="left")
    dock = DockState.from_dict("right", {"open": "yes", "width": True, "ratio": "x"})
    assert dock == DockState(side="right")
