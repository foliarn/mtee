import pytest

from mtee.domain.playlists import reorder_entries


def test_noncontiguous_batch_uses_source_order_and_end_boundary() -> None:
    order = ["A", "B", "C", "D", "E"]
    assert reorder_entries(order, ["D", "B"], "E") == ["A", "C", "B", "D", "E"]
    assert reorder_entries(order, ["D", "B"]) == ["A", "C", "E", "B", "D"]
    assert reorder_entries(order, ["E"], "A") == ["E", "A", "B", "C", "D"]
    assert order == ["A", "B", "C", "D", "E"]


def test_own_boundary_is_noop_and_invalid_ids_are_rejected() -> None:
    order = ["A", "B", "C", "D", "E"]
    assert reorder_entries(order, ["B", "D"], "B") == order
    assert reorder_entries(order, ["B"], "C") == order
    for moving, before in [(["B", "B"], "E"), (["X"], "E"), (["B"], "X")]:
        with pytest.raises(ValueError):
            reorder_entries(order, moving, before)
