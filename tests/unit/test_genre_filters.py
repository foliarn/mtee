import pytest
from tests.integration.test_genre_seed import genre_id

from mtee.domain.genre_filters import folder_protected_ids, matches_filter, validate_filter
from mtee.domain.genres import GenreError, initial_taxonomy


def spec(mode, *criteria):
    return {
        "version": 1,
        "mode": mode,
        "criteria": [{"kind": kind, "id": identity} for kind, identity in criteria],
    }


def test_all_any_exclusions_implicit_families_and_base_only():
    tree = initial_taxonomy()
    speed = genre_id("UK Garage \u203a Speed Garage")
    bass = genre_id("UK Garage \u203a Bassline")
    family = genre_id("UK Garage")
    hybrid = {"genreIds": [speed, bass]}
    single = {"genreIds": [speed]}
    base = {"genreIds": [family]}
    both = spec("all", ("genre", speed), ("genre", bass))
    assert matches_filter(hybrid, both, tree, "", {})
    assert not matches_filter(single, both, tree, "", {})
    either = spec("any", ("genre", speed), ("genre", bass))
    assert matches_filter(single, either, tree, "", {})
    assert not matches_filter(
        hybrid, spec("any", ("genre", speed), ("exclude_genre", bass)), tree, "", {}
    )
    assert matches_filter(single, spec("all", ("genre", family)), tree, "", {})
    assert matches_filter(base, spec("all", ("no_subgenre", "")), tree, "", {})
    assert matches_filter({"genreIds": []}, spec("all", ("no_subgenre", "")), tree, "", {})
    assert not matches_filter({"genreIds": []}, spec("all", ("family_only", "")), tree, "", {})
    assert matches_filter(base, spec("all", ("without_brush", "")), tree, speed, {})
    assert not matches_filter(single, spec("all", ("without_brush", "")), tree, speed, {})


def test_missing_definitions_protection_meta_and_tags():
    tree = initial_taxonomy()
    house = genre_id("House")
    with pytest.raises(GenreError, match="Unknown"):
        validate_filter(spec("all", ("genre", "removed")), tree, set(), set())
    with pytest.raises(GenreError, match="context"):
        validate_filter(spec("all", ("exclude_genre", house)), tree, set(), set(), {house})
    with pytest.raises(GenreError, match="Choose"):
        matches_filter({}, spec("all", ("without_brush", "")), tree, "", {})
    row = {"genreIds": [genre_id("House \u203a Deep")], "localTagIds": ["warm"]}
    assert matches_filter(
        row, spec("all", ("meta", "night"), ("tag", "warm")), tree, "", {"night": {house}}
    )


def test_folder_context_protects_taxonomy_ids_and_ancestors():
    tree = initial_taxonomy()
    protected = folder_protected_ids("d&b/jump up", tree)
    assert genre_id("Drum & Bass") in protected
    assert genre_id("Drum & Bass \u203a Jump Up") not in protected
    assert not folder_protected_ids("techno, trance", tree)
