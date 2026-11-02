"""The settings that may travel between devices, and how a plugin may write them.

This module is the one place that decides it (plan 125.6). A setting is synchronizable only if
its key is in ``SYNCED_SETTINGS``. The rule for adding a key: it describes a choice of the
person (how MTEE sounds, looks or is named), it means the same on every computer, and it holds
no path, no device name, no secret and no machine limit. Never add:

- folders and library roots (paths differ per computer);
- the audio output device, the volume and the muted state (hardware differs per computer);
- the window geometry and the layout of the editor groups (screens differ);
- the data paths, the device identifier, the plugin sources and every ``plugins.<id>.`` key
  (they belong to this installation or to one plugin);
- the analysis settings (``analysis/settings`` holds ``parallel_jobs``, a limit of this machine).

Keys the plan 125.6 proposal names but this module cannot carry yet:

- the track-list columns and widths of the library views live in the workspace state, not in
  the settings table; only the playlist columns (``playlists/columns``) are a setting;
- the profile avatar is a file of the profile folder (``profile/avatar_file`` is only its
  local file name), so it needs a file transfer through the profile service, not a setting;
- the keyboard shortcuts are not stored yet.

Each entry validates the text a plugin writes, so a plugin cannot store a value the models
could not read. ``plugins.enabled`` is allowed on the person's request: a plugin that writes it
can switch other installed plugins on or off, which applies at the next start (a plugin has
full access to the computer anyway, see ``docs/plugins.md``).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from mtee.domain.loudness import NORMALIZATION_LEVELS
from mtee.models.playback_settings_model import SETTING_NORMALIZATION
from mtee.plugins.loader import SETTING_ENABLED
from mtee.services.profile_service import DISPLAY_NAME_KEY, normalize_display_name

__all__ = [
    "PLAYLIST_COLUMNS_KEY",
    "SYNCED_SETTINGS",
    "SYNCED_SETTING_KEYS",
    "normalize_synced_value",
]

# The playlist columns have no constant in their model; this is the key it reads and writes.
PLAYLIST_COLUMNS_KEY = "playlists/columns"


def _text_name(value: str) -> str:
    return normalize_display_name(value)


def _object(value: str, check: Callable[[dict[str, Any]], None]) -> str:
    parsed = _parse(value)
    if not isinstance(parsed, dict):
        raise ValueError("expected a JSON object")
    check(parsed)
    return _dump(parsed)


def _normalization(parsed: dict[str, Any]) -> None:
    if set(parsed) - {"enabled", "level"}:
        raise ValueError("unknown field in the normalization setting")
    if "enabled" in parsed and type(parsed["enabled"]) is not bool:
        raise ValueError("'enabled' must be true or false")
    if "level" in parsed and parsed["level"] not in NORMALIZATION_LEVELS:
        raise ValueError(f"'level' must be one of {', '.join(NORMALIZATION_LEVELS)}")


def _playlist_columns(parsed: dict[str, Any]) -> None:
    if set(parsed) - {"order", "hidden", "widths", "showArtwork"}:
        raise ValueError("unknown field in the playlist columns")
    for name in ("order", "hidden"):
        if name in parsed and not _strings(parsed[name]):
            raise ValueError(f"'{name}' must be a list of column names")
    widths = parsed.get("widths", {})
    if not isinstance(widths, dict) or not all(
        isinstance(key, str) and type(width) is int and 0 <= width <= 4000
        for key, width in widths.items()
    ):
        raise ValueError("'widths' must map column names to widths")
    if "showArtwork" in parsed and type(parsed["showArtwork"]) is not bool:
        raise ValueError("'showArtwork' must be true or false")


def _plugin_list(value: str) -> str:
    parsed = _parse(value)
    if not _strings(parsed) or not all(parsed):
        raise ValueError("expected a JSON list of plugin ids")
    return _dump(parsed)


def _strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _parse(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"not valid JSON: {error.msg}") from error


def _dump(value: Any) -> str:
    # The same text SettingsRepository.set_json stores, so equal values compare equal.
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


# Key of the settings table -> check that returns the text to store, or raises ValueError.
SYNCED_SETTINGS: Mapping[str, Callable[[str], str]] = {
    SETTING_NORMALIZATION: lambda value: _object(value, _normalization),
    DISPLAY_NAME_KEY: _text_name,
    PLAYLIST_COLUMNS_KEY: lambda value: _object(value, _playlist_columns),
    SETTING_ENABLED: _plugin_list,
}
SYNCED_SETTING_KEYS = frozenset(SYNCED_SETTINGS)


def normalize_synced_value(key: str, value: str) -> str:
    """Return the text to store for ``key``; ``KeyError`` when the key may not travel.

    Raises ``ValueError`` with a readable reason when ``value`` is not valid for the key.
    """
    return SYNCED_SETTINGS[key](value)
