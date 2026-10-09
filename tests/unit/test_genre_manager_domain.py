"""Ordered genre choices are independent from the UI gesture."""

import pytest

from mtee.plugins.genre_manager.domain import (
    GenreConflictError,
    add_genre,
    make_primary,
    remove_genre,
    validate_order,
)

PARENTS = {
    "house": None,
    "deep": "house",
    "minimal": "house",
    "techno": None,
}


def test_descendant_refines_the_same_position_without_implicit_parent() -> None:
    assert add_genre(["house", "techno"], "deep", PARENTS) == ("deep", "techno")
    assert add_genre(["deep"], "house", PARENTS) == ("deep",)
    assert add_genre(["deep"], "minimal", PARENTS) == ("deep", "minimal")


def test_remove_and_promote_are_explicit_and_preserve_remaining_order() -> None:
    assert remove_genre(["deep", "minimal", "techno"], "deep") == ("minimal", "techno")
    assert make_primary(["deep", "minimal", "techno"], "techno") == ("techno", "deep", "minimal")
    assert remove_genre(["deep"], "deep") == ()


@pytest.mark.parametrize("invalid", [["house", "deep"], ["deep", "deep"], ["missing"]])
def test_invalid_explicit_lists_are_refused(invalid: list[str]) -> None:
    with pytest.raises(GenreConflictError):
        validate_order(invalid, PARENTS)
