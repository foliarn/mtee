"""Folder mappings with a local subfolder (plan 129.1): the rules, the row text and the migration.

A mapping starts at a subfolder of a watched folder when ``local_subpath`` is set. The tests here
use a real database and the real migrations; the sync itself is tested in ``test_first_match.py``
and ``test_push.py``.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from mtee.plugins.remote.folders import (  # pyright: ignore[reportMissingImports]
    LocalFolder,
    checked_local_subpath,
    describe,
    folder_row,
)
from mtee.plugins.remote.store import (  # pyright: ignore[reportMissingImports]
    FolderMapping,
    RemoteStore,
)
from tests.plugins.remote.conftest import PLUGIN_DIR

from mtee.persistence.database import Database, discover_migrations
from mtee.plugins.api import PluginContext

NAMES = {"root-1": "music"}


def test_the_row_text_names_the_local_subfolder_then_the_server_folder() -> None:
    whole = FolderMapping("D:/Music", "root-1")
    server_sub = FolderMapping("D:/Music", "root-1", "Incoming")
    local_sub = FolderMapping("D:/Music", "root-1", "", "baile")
    both = FolderMapping("D:/Music", "root-1", "baile", "baile")

    assert describe(None, NAMES) == "Not synced"
    assert describe(whole, NAMES) == "music"
    assert describe(server_sub, NAMES) == "music / Incoming"
    assert describe(local_sub, NAMES) == "baile → music"
    assert describe(both, NAMES) == "baile → music / baile"


def test_the_folder_row_carries_the_local_subfolder() -> None:
    mapped = LocalFolder("D:/Music", FolderMapping("D:/Music", "root-1", "Incoming", "baile"))
    unmapped = LocalFolder("D:/Other", None)

    assert folder_row(mapped, NAMES) == {
        "path": "D:/Music",
        "text": "baile → music / Incoming",
        "mapped": True,
        "rootId": "root-1",
        "subpath": "Incoming",
        "localSubpath": "baile",
    }
    assert folder_row(unmapped, NAMES)["localSubpath"] == ""


def test_an_empty_local_subfolder_is_the_whole_watched_folder(tmp_path: Path) -> None:
    assert checked_local_subpath(str(tmp_path), "") == ""
    assert checked_local_subpath(str(tmp_path), " / ") == ""


def test_an_existing_local_subfolder_is_cleaned_and_kept(tmp_path: Path) -> None:
    (tmp_path / "Jazz" / "Baile").mkdir(parents=True)

    assert checked_local_subpath(str(tmp_path), " Jazz\\Baile/ ") == "Jazz/Baile"


def test_a_missing_local_subfolder_is_refused_with_a_readable_sentence(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="The local subfolder nowhere does not exist"):
        checked_local_subpath(str(tmp_path), "nowhere")


def test_a_local_subfolder_that_climbs_out_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must not contain"):
        checked_local_subpath(str(tmp_path), "../elsewhere")


def test_the_migration_keeps_existing_mappings_with_an_empty_local_subpath(
    tmp_path: Path,
) -> None:
    migrations = discover_migrations(PLUGIN_DIR / "remote" / "migrations")
    names = [migration.file_name for migration in migrations]
    (index,) = [at for at, name in enumerate(names) if name.startswith("006_local_subpath")]
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    # A database as the plugin left it before this milestone: migrations 001 to 005 only.
    database.migrate_plugin("remote", migrations[:index])
    with database.transaction() as conn:
        conn.execute(
            "INSERT INTO remote_mappings (local_root_path, server_root_id, server_subpath)"
            " VALUES (?, ?, ?)",
            (str(tmp_path / "Music"), "root-1", "Incoming"),
        )

    database.migrate_plugin("remote", migrations)

    store = RemoteStore(cast(PluginContext, SimpleNamespace(database=database)))
    assert store.mappings() == [FolderMapping(str(tmp_path / "Music"), "root-1", "Incoming", "")]
    database.close()
