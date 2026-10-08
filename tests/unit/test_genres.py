"""Genre invariants, family fallbacks and the inclusive Jungle BPM boundary."""

import pytest

from mtee.domain.genres import Genre, GenreError, Taxonomy, initial_taxonomy, jungle_or_breaks


def test_precise_assignments_and_last_subgenre_fallback() -> None:
    tree = Taxonomy(
        [
            Genre("house", None, "House"),
            Genre("deep", "house", "Deep"),
            Genre("minimal", "house", "Minimal"),
            Genre("dub", None, "Dubstep"),
            Genre("dub-deep", "dub", "Deep"),
        ]
    )
    assert tree.normalize(["house", "deep", "minimal"]) == {"deep", "minimal"}
    assert tree.remove(["deep", "minimal", "dub-deep"], ["deep"]) == {"minimal", "dub-deep"}
    assert tree.remove(["minimal", "dub-deep"], ["minimal"]) == {"house", "dub-deep"}
    assert tree.remove(["house"], ["house"]) == set()
    assert tree.path("dub-deep") == "Dubstep \u203a Deep"
    assert tree.families(["deep", "minimal", "dub-deep"]) == {"house", "dub"}


@pytest.mark.parametrize(
    "nodes",
    [
        [Genre("a", "b", "A"), Genre("b", "a", "B")],
        [Genre("a", "missing", "A")],
        [Genre("a", None, "House"), Genre("b", None, "  HOUSE ")],
        [Genre("a", None, "")],
        [Genre("a", None, "A"), Genre("a", None, "B")],
    ],
)
def test_invalid_tree_is_refused(nodes: list[Genre]) -> None:
    with pytest.raises(GenreError):
        Taxonomy(nodes)


@pytest.mark.parametrize(
    ("bpm", "expected"),
    [
        (87, "Drum & Bass \u203a Jungle"),
        (159, "Breaks"),
        (160, "Drum & Bass \u203a Jungle"),
        (90, "Breaks"),
        (None, None),
        (0, None),
        (-1, None),
        (float("inf"), None),
        (float("nan"), None),
    ],
)
def test_bpm_rule(bpm: float | None, expected: str | None) -> None:
    assert jungle_or_breaks(bpm) == expected


def test_initial_ids_and_paths_are_reproducible() -> None:
    first, second = initial_taxonomy(), initial_taxonomy()
    assert first.nodes == second.nodes
    assert len(first.nodes) == 48
    assert sum(node.name == "Deep" for node in first.nodes.values()) == 2
