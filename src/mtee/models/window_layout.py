"""Pure layout model of the center windows and of the docks.

The center is a tree. A leaf is one center window, identified by a stable group id
(``"g1"``, ``"g2"``...). A split divides its area between two or more children along one
axis. The model holds no Qt object: the workspace keeps the group contents, and QML draws
the tree. Every operation returns a new tree; the input is never modified.

Terms:

- ``row`` split: children side by side (their separators are vertical). A ``left`` or
  ``right`` edge creates a row split.
- ``column`` split: children stacked (their separators are horizontal). A ``top`` or
  ``bottom`` edge creates a column split.
- ratio: the share of the split's length taken by one child. The ratios sum to 1.
- path: the child indexes from the root to a split, e.g. ``()`` is the root.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

__all__ = [
    "DEFAULT_DOCK_WIDTH",
    "DEFAULT_GROUP_ID",
    "DockState",
    "Edge",
    "GroupId",
    "Leaf",
    "Node",
    "Orientation",
    "Split",
    "groups",
    "neighbour",
    "node_from_dict",
    "node_to_dict",
    "remove",
    "set_ratios",
    "split",
]

GroupId = str
Orientation = Literal["row", "column"]
Edge = Literal["left", "right", "top", "bottom"]
Direction = Literal["left", "right", "top", "bottom"]
DockSide = Literal["left", "right"]

DEFAULT_GROUP_ID: GroupId = "g1"
DEFAULT_DOCK_WIDTH = 260
MIN_DOCK_WIDTH = 220
MAX_DOCK_WIDTH = 480
_EDGES: tuple[str, ...] = ("left", "right", "top", "bottom")
_ORIENTATIONS: tuple[str, ...] = ("row", "column")
_RATIO_TOLERANCE = 1e-6


@dataclass(frozen=True, slots=True)
class Leaf:
    """One center window."""

    group_id: GroupId


@dataclass(frozen=True, slots=True)
class Split:
    """Children divided along ``orientation``. ``ratios`` sum to 1, one per child."""

    orientation: Orientation
    children: tuple[Node, ...]
    ratios: tuple[float, ...]


Node = Leaf | Split


def _axis_of(edge: str) -> Orientation:
    """Return the split orientation an edge or a direction moves along."""
    return "row" if edge in ("left", "right") else "column"


def _even(count: int) -> tuple[float, ...]:
    return tuple(1.0 / count for _ in range(count))


def _flatten(node: Node) -> Node:
    """Remove splits nested in a split of the same orientation, and single-child splits."""
    if isinstance(node, Leaf):
        return node
    children: list[Node] = []
    ratios: list[float] = []
    for child, ratio in zip(node.children, node.ratios, strict=True):
        flat = _flatten(child)
        if isinstance(flat, Split) and flat.orientation == node.orientation:
            children.extend(flat.children)
            ratios.extend(ratio * sub for sub in flat.ratios)
        else:
            children.append(flat)
            ratios.append(ratio)
    if len(children) == 1:
        return children[0]
    total = sum(ratios)
    return Split(node.orientation, tuple(children), tuple(r / total for r in ratios))


def _leaf_path(node: Node, group_id: GroupId) -> tuple[int, ...] | None:
    """Return the child indexes leading to the leaf of ``group_id``, or None."""
    if isinstance(node, Leaf):
        return () if node.group_id == group_id else None
    for index, child in enumerate(node.children):
        found = _leaf_path(child, group_id)
        if found is not None:
            return (index, *found)
    return None


def _node_at(node: Node, path: Sequence[int]) -> Node:
    for index in path:
        if isinstance(node, Leaf):
            raise ValueError("path leads into a leaf")
        node = node.children[index]
    return node


def _replace_at(node: Node, path: Sequence[int], new: Node) -> Node:
    if not path:
        return new
    if isinstance(node, Leaf):
        raise ValueError("path leads into a leaf")
    index, rest = path[0], path[1:]
    children = list(node.children)
    children[index] = _replace_at(children[index], rest, new)
    return Split(node.orientation, tuple(children), node.ratios)


def groups(tree: Node) -> tuple[GroupId, ...]:
    """Return the group ids in reading order (depth first, children in order)."""
    if isinstance(tree, Leaf):
        return (tree.group_id,)
    result: list[GroupId] = []
    for child in tree.children:
        result.extend(groups(child))
    return tuple(result)


def split(tree: Node, target: GroupId, edge: Edge, new_group: GroupId) -> Node:
    """Put ``new_group`` beside ``target`` on ``edge`` and return the new tree.

    The new window takes half of the target's area. A split of the same orientation as the
    parent is merged into it, so ``split`` on the same axis never nests.
    """
    if edge not in _EDGES:
        raise ValueError(f"unknown edge: {edge!r}")
    if new_group in groups(tree):
        raise ValueError(f"group already in the layout: {new_group!r}")
    path = _leaf_path(tree, target)
    if path is None:
        raise ValueError(f"unknown group: {target!r}")
    target_leaf = Leaf(target)
    new_leaf = Leaf(new_group)
    pair = (new_leaf, target_leaf) if edge in ("left", "top") else (target_leaf, new_leaf)
    replacement = Split(_axis_of(edge), pair, _even(2))
    return _flatten(_replace_at(tree, path, replacement))


def remove(tree: Node, group: GroupId) -> Node | None:
    """Remove ``group`` and return the new tree, or None when it was the only window.

    The space of the removed window goes to its siblings in proportion to their ratios.
    Splits left with one child collapse into that child.
    """
    path = _leaf_path(tree, group)
    if path is None:
        raise ValueError(f"unknown group: {group!r}")
    if not path:
        return None
    parent_path, index = path[:-1], path[-1]
    parent = _node_at(tree, parent_path)
    assert isinstance(parent, Split)
    children = tuple(c for i, c in enumerate(parent.children) if i != index)
    ratios = [r for i, r in enumerate(parent.ratios) if i != index]
    total = sum(ratios)
    kept = Split(parent.orientation, children, tuple(r / total for r in ratios))
    return _flatten(_replace_at(tree, parent_path, kept))


def _clamp_shares(values: list[float], minimum: float) -> list[float]:
    """Return shares of at least ``minimum`` that sum to 1, keeping the proportions."""
    count = len(values)
    if minimum * count > 1 + _RATIO_TOLERANCE:
        raise ValueError("minimum share too large for the number of children")
    weights = [max(v, 1e-9) for v in values]
    shares = [0.0] * count
    fixed: set[int] = set()
    while True:
        free = [i for i in range(count) if i not in fixed]
        remaining = 1.0 - minimum * len(fixed)
        weight_total = sum(weights[i] for i in free)
        for i in free:
            shares[i] = remaining * weights[i] / weight_total
        below = [i for i in free if shares[i] < minimum - _RATIO_TOLERANCE]
        if not below:
            break
        for i in below:
            shares[i] = minimum
        fixed.update(below)
    return shares


def set_ratios(tree: Node, path: Sequence[int], ratios: Sequence[float], minimum: float) -> Node:
    """Return the tree with the split at ``path`` given new ``ratios``.

    Each share is at least ``minimum`` (the caller passes the share that keeps a window above
    its minimum size). The shares are normalised to sum to 1.
    """
    node = _node_at(tree, path)
    if isinstance(node, Leaf):
        raise ValueError("ratios belong to a split, not to a leaf")
    if len(ratios) != len(node.children):
        raise ValueError("one ratio per child is needed")
    if any(not (r == r) or r < 0 for r in ratios):
        raise ValueError("ratios must be positive numbers")
    shares = _clamp_shares(list(ratios), minimum)
    updated = Split(node.orientation, node.children, tuple(shares))
    return _replace_at(tree, path, updated)


def neighbour(tree: Node, group: GroupId, direction: Direction) -> GroupId | None:
    """Return the group next to ``group`` in ``direction``, or None when there is none.

    The nearest split on the axis of the direction decides the neighbour. The neighbour is
    its first or last leaf, the one that touches ``group`` on that side.
    """
    if direction not in _EDGES:
        raise ValueError(f"unknown direction: {direction!r}")
    path = _leaf_path(tree, group)
    if path is None:
        raise ValueError(f"unknown group: {group!r}")
    axis = _axis_of(direction)
    forward = direction in ("right", "bottom")
    for depth in range(len(path) - 1, -1, -1):
        parent = _node_at(tree, path[:depth])
        assert isinstance(parent, Split)
        if parent.orientation != axis:
            continue
        index = path[depth]
        target_index = index + 1 if forward else index - 1
        if 0 <= target_index < len(parent.children):
            sibling = parent.children[target_index]
            entering = _entering_side(direction)
            return _edge_leaf(sibling, entering)
    return None


def _entering_side(direction: str) -> str:
    """The side of the neighbour that faces the window we move from."""
    return {"right": "left", "left": "right", "bottom": "top", "top": "bottom"}[direction]


def _edge_leaf(node: Node, side: str) -> GroupId:
    """The leaf of ``node`` that touches ``side``: first child for left/top, last otherwise."""
    while isinstance(node, Split):
        on_axis = node.orientation == _axis_of(side)
        node = node.children[-1] if on_axis and side in ("right", "bottom") else node.children[0]
    return node.group_id


def node_to_dict(node: Node) -> dict[str, Any]:
    """Return the JSON form of a tree."""
    if isinstance(node, Leaf):
        return {"type": "leaf", "group": node.group_id}
    return {
        "type": "split",
        "orientation": node.orientation,
        "children": [node_to_dict(child) for child in node.children],
        "ratios": list(node.ratios),
    }


def node_from_dict(data: Any) -> Node:
    """Read the JSON form of a tree. An invalid tree yields one empty leaf (the default group).

    Validation: known types, at least two children per split, ratios that are positive and
    sum to 1, group ids that are non-empty strings and unique.
    """
    try:
        node = _parse(data)
        if len(set(groups(node))) != len(groups(node)):
            raise ValueError("duplicate group id")
        return node
    except (ValueError, TypeError, KeyError, IndexError):
        return Leaf(DEFAULT_GROUP_ID)


def _parse(data: Any) -> Node:
    if not isinstance(data, Mapping):
        raise ValueError("node must be a mapping")
    kind = data.get("type")
    if kind == "leaf":
        group = data.get("group")
        if not isinstance(group, str) or not group:
            raise ValueError("leaf needs a group id")
        return Leaf(group)
    if kind != "split":
        raise ValueError("unknown node type")
    orientation = data.get("orientation")
    if orientation not in _ORIENTATIONS:
        raise ValueError("unknown orientation")
    raw_children = data.get("children")
    raw_ratios = data.get("ratios")
    if not isinstance(raw_children, list) or not isinstance(raw_ratios, list):
        raise ValueError("split needs lists")
    if len(raw_children) < 2 or len(raw_children) != len(raw_ratios):
        raise ValueError("split needs two children or more, one ratio per child")
    ratios: list[float] = []
    for value in raw_ratios:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ValueError("ratios must be positive numbers")
        ratios.append(float(value))
    total = sum(ratios)
    if abs(total - 1.0) > 1e-3:
        raise ValueError("ratios must sum to 1")
    children = tuple(_parse(child) for child in raw_children)
    return Split(orientation, children, tuple(r / total for r in ratios))  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class DockState:
    """A left or right dock: open or closed, its width, its tool windows and their split.

    ``windows`` holds up to two tool window ids; ``ratio`` is the share of the first window
    when two are stacked. The width is kept inside ``MIN_DOCK_WIDTH``..``MAX_DOCK_WIDTH``.
    """

    side: DockSide
    open: bool = True
    width: int = DEFAULT_DOCK_WIDTH
    windows: tuple[str, ...] = ()
    ratio: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "open": self.open,
            "width": self.width,
            "windows": list(self.windows),
            "ratio": self.ratio,
        }

    @classmethod
    def from_dict(cls, side: DockSide, data: Any) -> DockState:
        """Read a dock. Invalid fields fall back to their defaults, one by one."""
        default = cls(side=side)
        if not isinstance(data, Mapping):
            return default
        is_open = data.get("open", default.open)
        width = data.get("width", default.width)
        if isinstance(width, bool) or not isinstance(width, (int, float)):
            width = default.width
        width = int(min(max(width, MIN_DOCK_WIDTH), MAX_DOCK_WIDTH))
        raw_windows = data.get("windows", [])
        windows: tuple[str, ...] = ()
        if isinstance(raw_windows, list):
            windows = tuple(w for w in raw_windows if isinstance(w, str) and w)[:2]
        ratio = data.get("ratio", default.ratio)
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)):
            ratio = default.ratio
        ratio = min(max(float(ratio), 0.1), 0.9)
        return cls(
            side=side,
            open=bool(is_open) if isinstance(is_open, bool) else default.open,
            width=width,
            windows=windows,
            ratio=ratio,
        )
