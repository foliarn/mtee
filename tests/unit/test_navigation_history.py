"""Pure page history transitions, independent of Qt and audio playback."""

from mtee.domain.navigation_history import NavigationHistory, NavigationLocation


def _page(tab: str, **view: object) -> NavigationLocation:
    return NavigationLocation("explorer", tab, view=dict(view))


def test_history_prunes_forward_branch_and_skips_repeated_destination() -> None:
    history = NavigationHistory().visit(_page("folder:a"))
    history = history.visit(_page("folder:b"))
    history = history.visit(_page("folder:b", search="query"))
    assert len(history.locations) == 2
    assert history.current is not None
    assert history.current.view == {"search": "query"}
    history = history.back().visit(_page("folder:c"))
    assert not history.can_forward
    assert [location.tab_id for location in history.locations] == ["folder:a", "folder:c"]


def test_capture_preserves_view_before_back_and_bounds_do_nothing() -> None:
    history = NavigationHistory().visit(_page("folder:a")).visit(_page("folder:b"))
    history = history.capture(_page("folder:b", scroll=125, selected=["track-id"]))
    history = history.back()
    assert history.current is not None and history.current.tab_id == "folder:a"
    assert history.back() is history
    history = history.forward()
    assert history.current is not None
    assert history.current.view == {"scroll": 125, "selected": ["track-id"]}
    assert history.forward() is history


def test_two_groups_keep_independent_immutable_histories() -> None:
    first = NavigationHistory().visit(_page("folder:a"))
    second = NavigationHistory().visit(_page("folder:a"))
    first = first.visit(_page("folder:b"))
    assert first.can_back
    assert not second.can_back
