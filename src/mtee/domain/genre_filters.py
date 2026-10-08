"""Versioned composable filters over local taxonomy, independent of playback queues."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from mtee.domain.genres import RESOURCES, GenreError, Taxonomy, initial_taxonomy


def validate_filter(
    spec: dict[str, Any],
    tree: Taxonomy,
    metas: set[str],
    tags: set[str],
    protected: set[str] | None = None,
) -> None:
    if spec.get("version") != 1 or spec.get("mode") not in {"all", "any"}:
        raise GenreError("Unsupported filter; edit or reset this filter")
    if not isinstance(spec.get("criteria"), list):
        raise GenreError("Invalid filter criteria")
    for criterion in spec["criteria"]:
        kind = criterion.get("kind")
        identity = criterion.get("id", "")
        if kind in {"genre", "exclude_genre"}:
            tree.ancestors(identity)
            if kind == "exclude_genre" and identity in (protected or set()):
                raise GenreError("This family belongs to the current folder context")
        elif kind == "meta":
            if identity not in metas:
                raise GenreError("Missing meta-family; edit this filter")
        elif kind == "tag":
            if identity not in tags:
                raise GenreError("Missing local tag; edit this filter")
        elif kind not in {"without_brush", "no_subgenre", "family_only", "no_genre"}:
            raise GenreError("Unknown criterion; edit this filter")


def matches_filter(
    row: dict[str, Any],
    spec: dict[str, Any],
    tree: Taxonomy,
    brush: str,
    meta_members: dict[str, set[str]],
) -> bool:
    direct = set(row.get("genreIds", []))
    effective = direct | {a for g in direct for a in tree.ancestors(g)}
    results = []
    exclusions = []
    for criterion in spec["criteria"]:
        kind = criterion["kind"]
        identity = criterion.get("id", "")
        if kind == "exclude_genre":
            exclusions.append(identity not in effective)
            continue
        if kind == "genre":
            value = identity in effective
        elif kind == "meta":
            value = bool(effective & meta_members[identity])
        elif kind == "tag":
            value = identity in row.get("localTagIds", [])
        elif kind == "without_brush":
            if not brush or brush not in tree.nodes:
                raise GenreError("Choose a brush for this filter")
            value = brush not in effective
        elif kind == "no_genre":
            value = not direct
        elif kind == "no_subgenre":
            value = not any(tree.nodes[g].parent_id for g in direct)
        else:
            value = bool(direct) and not any(tree.nodes[g].parent_id for g in direct)
        results.append(value)
    return all(exclusions) and (
        not results or (all(results) if spec["mode"] == "all" else any(results))
    )


def folder_protected_ids(relative: str, tree: Taxonomy) -> set[str]:
    """The folder's original context survives manual assignment changes."""
    result = set()
    for identity in folder_context_mapping().get(relative, []):
        if identity in tree.nodes:
            result.update(tree.ancestors(identity))
            if tree.nodes[identity].parent_id is None:
                result.add(identity)
    return result


@lru_cache(maxsize=1)
def folder_context_mapping() -> dict[str, list[str]]:
    mapping = json.loads((RESOURCES / "folder_mapping.json").read_text(encoding="utf-8"))
    original = initial_taxonomy()
    by_path = {original.path(i): i for i in original.nodes}
    return {
        rule["folder"]: (
            [by_path["Drum & Bass \u203a Jungle"], by_path["Breaks"]]
            if rule.get("rule")
            else rule.get("genres", [])
        )
        for rule in mapping["rules"]
    }
