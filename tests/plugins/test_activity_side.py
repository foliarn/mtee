"""The bar side of a plugin activity (plan 131.4): left by default, left or right only."""

from __future__ import annotations

import pytest

from mtee.plugins.api import PluginActivity
from mtee.plugins.contributions import check_contributions


def test_the_side_defaults_to_left() -> None:
    assert PluginActivity("remote", "Remote", "cloud").side == "left"


@pytest.mark.parametrize("side", ["left", "right"])
def test_left_and_right_are_accepted(side: str) -> None:
    check_contributions("p", [PluginActivity("remote", "Remote", "cloud", side=side)])


@pytest.mark.parametrize("side", ["top", "", "Right", "centre"])
def test_any_other_side_is_refused(side: str) -> None:
    with pytest.raises(ValueError, match="side"):
        check_contributions("p", [PluginActivity("remote", "Remote", "cloud", side=side)])
