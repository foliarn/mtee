"""Folder mapping (plan 126.2): which watched folder of this computer syncs with which folder.

A mapping is a local watched folder, an optional subfolder of it (the local subfolder, plan 129.1),
its server root and an optional subfolder of that root. The folders of the library are read from
the core (``context.library.roots()``), the mappings from ``remote_mappings``; this module only
builds the rows the page shows and checks what it is given.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from mtee.plugins.api import PluginContext

from .store import FolderMapping

NOT_SYNCED = "Not synced"


@dataclass(frozen=True)
class LocalFolder:
    """A watched folder of the library, with its mapping when it has one."""

    path: str
    mapping: FolderMapping | None


def local_folders(context: PluginContext, mappings: Sequence[FolderMapping]) -> list[LocalFolder]:
    """Every watched folder, in the order the library lists them."""
    by_path = {mapping.local_root_path: mapping for mapping in mappings}
    return [
        LocalFolder(str(root.path), by_path.get(str(root.path))) for root in context.library.roots()
    ]


def clean_subpath(text: str) -> str:
    """Return a subfolder as a POSIX path without empty parts, or raise ``ValueError``."""
    parts: list[str] = []
    for raw in text.replace("\\", "/").split("/"):
        part = raw.strip()
        if not part:
            continue
        if part in (".", ".."):
            raise ValueError("The subfolder must not contain '.' or '..'.")
        parts.append(part)
    return "/".join(parts)


def checked_local_subpath(local_root: str, text: str) -> str:
    """Return a local subfolder of a watched folder, cleaned, or raise ``ValueError``.

    An empty text is the whole watched folder. Any other subfolder must exist on disk now: a
    mapping that starts at a missing folder would match nothing, and the person should hear that
    when they save rather than find an empty sync later.
    """
    cleaned = clean_subpath(text)
    if not cleaned:
        return ""
    if not Path(local_root).joinpath(*cleaned.split("/")).is_dir():
        raise ValueError(f"The local subfolder {cleaned} does not exist in this watched folder.")
    return cleaned


def watched_path(context: PluginContext, path: str) -> str:
    """Return ``path`` as the library names it, or raise when it is not a watched folder."""
    for root in context.library.roots():
        if str(root.path) == path:
            return str(root.path)
    raise ValueError("This folder is no longer a watched folder of the library.")


def describe(mapping: FolderMapping | None, root_names: Mapping[str, str]) -> str:
    """The text of a folder's row: its server folder, or that it is not synced.

    With a local subfolder the row reads "local subfolder → server folder / server subfolder", for
    example "baile → music / baile", so the person sees which part of the folder is synced.
    """
    if mapping is None:
        return NOT_SYNCED
    name = root_names.get(mapping.server_root_id, "a server folder")
    server = f"{name} / {mapping.server_subpath}" if mapping.server_subpath else name
    if mapping.local_subpath:
        return f"{mapping.local_subpath} → {server}"
    return server


def folder_row(folder: LocalFolder, root_names: Mapping[str, str]) -> dict[str, object]:
    """The map the page reads for one folder."""
    mapping = folder.mapping
    return {
        "path": folder.path,
        "text": describe(mapping, root_names),
        "mapped": mapping is not None,
        "rootId": mapping.server_root_id if mapping is not None else "",
        "subpath": mapping.server_subpath if mapping is not None else "",
        "localSubpath": mapping.local_subpath if mapping is not None else "",
    }
