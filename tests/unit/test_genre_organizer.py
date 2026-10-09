"""Destination validation and reviewed-only preview stay independent of folder names."""

import pytest

from mtee.plugins.genre_manager.organizer import OrganizationError, clean_relative_folder


@pytest.mark.parametrize(
    "value",
    ["../House", "/House", "C:/House", "House//Deep", "CON", "House/PRN.wav", "House ", "X?"],
)
def test_unsafe_windows_destinations_are_refused(value: str) -> None:
    with pytest.raises(OrganizationError):
        clean_relative_folder(value)


def test_relative_windows_separators_are_canonicalized() -> None:
    assert clean_relative_folder("House\\Deep House") == "House/Deep House"
    assert clean_relative_folder("") == ""
