"""The one plugin list of the Plugins view (plan 132.6).

The installed plugins and the Marketplace plugins are one list, each plugin once. A plugin that is
installed and listed by a marketplace comes first, then the installed plugins that no marketplace
lists, then the plugins that are only listed. Each group is sorted by title. A plugin listed by
two marketplaces is one row: the first offer in the order of the list (an installed plugin has
its installed row, which is never a Marketplace row).

A row is ``{key, pluginId, title, letter, installed, tag, tagTone, warning}``. ``key`` is the
plugin id for an installed plugin, and ``id@address`` for a Marketplace one, as ``openDetail``
expects. A tag is shown only for an installed plugin: Running, Failed (warning) or Installed (P8).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Set
from typing import Any

__all__ = ["plugin_list_rows"]

_GROUP_INSTALLED_LISTED = 0
_GROUP_INSTALLED_OTHER = 1
_GROUP_NOT_INSTALLED = 2


def plugin_list_rows(
    installed: Iterable[Mapping[str, Any]],
    marketplace: Iterable[Mapping[str, Any]],
    listed_ids: Set[str],
) -> list[dict[str, Any]]:
    """The rows of the one list.

    ``installed`` and ``marketplace`` are the rows of the view, already filtered by the search.
    ``listed_ids`` holds the id of every plugin that an enabled marketplace lists.
    """
    rows: list[dict[str, Any]] = []
    installed_ids: set[str] = set()
    for row in installed:
        plugin_id = str(row["id"])
        installed_ids.add(plugin_id)
        status = str(row.get("status", ""))
        group = _GROUP_INSTALLED_LISTED if plugin_id in listed_ids else _GROUP_INSTALLED_OTHER
        rows.append(
            _row(
                key=plugin_id,
                plugin_id=plugin_id,
                title=str(row["title"]),
                letter=str(row.get("letter", "")),
                installed=True,
                group=group,
                tag=_INSTALLED_TAGS.get(status, "Installed"),
                tone=_INSTALLED_TONES.get(status, "neutral"),
                warning=status == "failed",
            )
        )
    seen: set[str] = set()
    for row in marketplace:
        plugin_id = str(row["id"])
        if plugin_id in installed_ids or plugin_id in seen:
            continue
        seen.add(plugin_id)
        rows.append(
            _row(
                key=str(row["key"]),
                plugin_id=plugin_id,
                title=str(row["title"]),
                letter=str(row.get("letter", "")),
                installed=False,
                group=_GROUP_NOT_INSTALLED,
                tag="",
                tone="neutral",
                warning=False,
            )
        )
    rows.sort(key=lambda item: (item["group"], item["title"].casefold(), item["pluginId"]))
    for item in rows:
        del item["group"]
    return rows


_INSTALLED_TAGS = {"running": "Running", "failed": "Failed"}
_INSTALLED_TONES = {"running": "primary", "failed": "warning"}


def _row(
    *,
    key: str,
    plugin_id: str,
    title: str,
    letter: str,
    installed: bool,
    group: int,
    tag: str,
    tone: str,
    warning: bool,
) -> dict[str, Any]:
    return {
        "key": key,
        "pluginId": plugin_id,
        "title": title,
        "letter": (letter or title.strip()[:1]).upper()[:1],
        "installed": installed,
        "tag": tag,
        "tagTone": tone,
        "warning": warning,
        "group": group,
    }
