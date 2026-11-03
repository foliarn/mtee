"""Explorer > Server (plan 126.9): the folder tree, its fold state, and the folder tabs.

The tree and the tabs read the plugin's tables; the library is the fake of the remote tests. The
server-only track of a tab is a real track source, made by ``show_as_server_only``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from mtee.plugins.remote.availability import (  # pyright: ignore[reportMissingImports]
    availability_column,
)
from mtee.plugins.remote.explorer import (  # pyright: ignore[reportMissingImports]
    FOLDS_KEY,
    SECTION_ID,
    TAB_KIND,
    ServerFolders,
)
from mtee.plugins.remote.sources import (  # pyright: ignore[reportMissingImports]
    show_as_server_only,
)
from mtee.plugins.remote.store import (  # pyright: ignore[reportMissingImports]
    FolderMapping,
    RemoteStore,
    ServerRow,
    insert_link,
    upsert_server_item,
)
from tests.plugins.remote.helpers import FakeLibrary, make_context, track

from mtee.plugins.api import (
    PluginContext,
    SidebarSection,
    TabHeader,
    TabKind,
    TabRequest,
    TrackListRow,
)

ROOT = "root-1"
WARM = {
    "title": ["Warm Static"],
    "artist": ["Loop Foundry"],
    "album": ["Loops"],
    "technical": {"duration_us": 252_000_000},
}


@dataclass
class Tree:
    context: PluginContext
    store: RemoteStore
    folders: ServerFolders
    library: FakeLibrary
    music: Path


def _item(
    store: RemoteStore,
    item_id: str,
    relative_path: str,
    *,
    root: str = ROOT,
    metadata: dict[str, Any] | None = None,
) -> None:
    with store.transaction() as conn:
        upsert_server_item(
            conn,
            ServerRow(
                item_id=item_id,
                root_id=root,
                relative_path=relative_path,
                size_bytes=1000,
                sha256=f"sha-{item_id}",
                audio_hash=None,
                revision=1,
                metadata_json=None if metadata is None else json.dumps(metadata),
                updated_at_utc="2026-11-03T10:00:00+00:00",
            ),
        )


def _link(store: RemoteStore, track_id: str, item_id: str) -> None:
    with store.transaction() as conn:
        insert_link(
            conn,
            track_id=track_id,
            item_id=item_id,
            item_revision=1,
            local_sha256="local",
            audio_hash=None,
        )


def _tree(tmp_path: Path, tracks: int = 2) -> Tree:
    music = tmp_path / "Music"
    library = FakeLibrary(
        [music], [track(f"t{index}", music / f"{index}.flac") for index in range(tracks)]
    )
    context = make_context(tmp_path, library)
    store = RemoteStore(context)
    store.save_mapping(FolderMapping(str(music), ROOT, ""))
    _item(store, "i1", "House/Deep House/a.flac", metadata=WARM)
    _item(store, "i2", "House/Deep House/b.flac")
    _item(store, "i3", "House/c.flac")
    _item(store, "i4", "Techno/d.flac")
    _item(store, "i5", "Incoming/e.flac")
    # A folder of another server root is not mapped here, so it is not shown.
    _item(store, "x1", "Other/f.flac", root="root-2")
    return Tree(context, store, ServerFolders(context, store), library, music)


@pytest.fixture
def tree(tmp_path: Path) -> Tree:
    return _tree(tmp_path)


def _by_id(folders: ServerFolders) -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in folders.build()}


def test_the_tree_lists_the_mapped_folders_with_depth_and_counts(tree: Tree) -> None:
    rows = tree.folders.build()

    assert [row["id"] for row in rows] == [
        f"{ROOT}/",
        f"{ROOT}/House",
        f"{ROOT}/House/Deep House",
        f"{ROOT}/Incoming",
        f"{ROOT}/Techno",
    ]
    by_id = _by_id(tree.folders)
    assert by_id[f"{ROOT}/"] == {
        "id": f"{ROOT}/",
        "name": "Music",
        "depth": 0,
        "kind": "group",
        "expanded": True,
        "count": "5",
    }
    assert by_id[f"{ROOT}/House"]["depth"] == 1
    assert by_id[f"{ROOT}/House"]["count"] == "3"
    assert by_id[f"{ROOT}/House/Deep House"]["depth"] == 2
    assert by_id[f"{ROOT}/House/Deep House"]["name"] == "Deep House"
    assert by_id[f"{ROOT}/House/Deep House"]["count"] == "2"
    assert by_id[f"{ROOT}/Techno"]["count"] == "1"


def test_a_subfolder_mapping_starts_at_its_folder(tree: Tree) -> None:
    tree.store.save_mapping(FolderMapping(str(tree.music), ROOT, "House"))
    rows = tree.folders.build()

    assert [row["id"] for row in rows] == [f"{ROOT}/House", f"{ROOT}/House/Deep House"]
    assert rows[0]["name"] == "House"
    assert rows[0]["depth"] == 0
    assert rows[1]["depth"] == 1
    assert rows[0]["count"] == "3"


def test_an_unmapped_server_root_is_not_shown(tree: Tree) -> None:
    assert not any("root-2" in row["id"] for row in tree.folders.build())


def test_a_library_of_up_to_2000_tracks_starts_expanded(tree: Tree) -> None:
    assert all(row["expanded"] for row in tree.folders.build())


def test_the_section_starts_collapsed_only_for_a_library_over_2000_tracks(tmp_path: Path) -> None:
    small = _tree(tmp_path / "small", tracks=2000)
    big = _tree(tmp_path / "big", tracks=2001)
    assert small.folders.starts_expanded() is True
    assert big.folders.starts_expanded() is False


def test_the_section_start_is_not_written_and_the_folders_start_expanded(tmp_path: Path) -> None:
    big = _tree(tmp_path, tracks=2001)
    # The collapsed start is the section's; the folders keep no default of their own.
    assert big.folders.starts_expanded() is False
    assert all(row["expanded"] for row in big.folders.build())
    assert big.context.settings.get_json(FOLDS_KEY, None) is None


def test_a_default_stored_by_an_earlier_version_is_ignored(tree: Tree) -> None:
    tree.context.settings.set_json(FOLDS_KEY, {"default_folded": True, "folded": {}})
    assert all(row["expanded"] for row in tree.folders.build())


def test_a_fold_is_remembered_per_folder_across_instances(tree: Tree) -> None:
    tree.folders.set_folded(f"{ROOT}/House", True)

    by_id = _by_id(tree.folders)
    assert by_id[f"{ROOT}/House"]["expanded"] is False
    assert by_id[f"{ROOT}/Techno"]["expanded"] is True
    # A new section, as after a restart, reads the same stored fold.
    again = ServerFolders(tree.context, tree.store)
    assert _by_id(again)[f"{ROOT}/House"]["expanded"] is False


def test_a_chevron_fold_goes_through_on_fold_and_is_remembered(tree: Tree) -> None:
    # The core calls on_fold(row_id, expanded) when the chevron is clicked.
    tree.folders.on_fold(f"{ROOT}/House", False)
    assert _by_id(tree.folders)[f"{ROOT}/House"]["expanded"] is False
    assert _by_id(tree.folders)[f"{ROOT}/Techno"]["expanded"] is True

    tree.folders.on_fold(f"{ROOT}/House", True)
    assert _by_id(tree.folders)[f"{ROOT}/House"]["expanded"] is True
    assert _by_id(ServerFolders(tree.context, tree.store))[f"{ROOT}/House"]["expanded"] is True


def test_the_section_declares_its_fold_start_and_name_click(tree: Tree) -> None:
    section = next(
        item for item in tree.folders.contributions() if isinstance(item, SidebarSection)
    )
    assert section.on_fold == tree.folders.on_fold
    assert section.expanded == tree.folders.starts_expanded
    assert section.activate == tree.folders.activate


def test_a_folder_row_opens_its_folder_tab(tree: Tree) -> None:
    ref = f"{ROOT}/House/Deep House"
    assert tree.folders.activate(ref) == TabRequest(TAB_KIND, ref)
    assert tree.folders.activate("") is None


def test_the_section_and_the_tab_kind_are_contributed(tree: Tree) -> None:
    contributions = tree.folders.contributions()
    section = next(item for item in contributions if isinstance(item, SidebarSection))
    assert section.section_id == SECTION_ID == "server"
    assert section.title == "Server"
    assert section.activity == "explorer"
    assert section.model is tree.folders.model
    kind = next(item for item in contributions if isinstance(item, TabKind))
    assert kind.kind == TAB_KIND == "remote.folder"


def test_a_folder_tab_lists_only_the_tracks_directly_in_it(tree: Tree) -> None:
    rows = tree.folders.tab_rows(f"{ROOT}/House")
    assert [row.row_id for row in rows] == ["i3"]


def test_a_linked_track_plays_its_local_track_and_a_server_only_one_its_source(
    tree: Tree,
) -> None:
    _link(tree.store, "t0", "i1")
    source = show_as_server_only(tree.context, tree.store, "i2", "House/Deep House/b.flac", None)

    rows = {row.row_id: row for row in tree.folders.tab_rows(f"{ROOT}/House/Deep House")}
    assert set(rows) == {"i1", "i2"}
    assert all(isinstance(row, TrackListRow) for row in rows.values())
    assert rows["i1"].track_id == "t0"
    assert rows["i2"].track_id == source != ""
    # The tags of the server come from the snapshot of the item.
    assert rows["i1"].title == "Warm Static"
    assert rows["i1"].artist == "Loop Foundry"
    assert rows["i1"].album == "Loops"
    assert rows["i1"].duration_seconds == pytest.approx(252.0)
    # Without a snapshot the file name is the title.
    assert rows["i2"].title == "b"


def test_a_server_only_track_without_a_source_yet_is_unavailable(tree: Tree) -> None:
    rows = {row.row_id: row for row in tree.folders.tab_rows(f"{ROOT}/House/Deep House")}
    assert rows["i2"].track_id == ""


def test_the_folder_tab_header_names_the_folder_and_counts_the_tracks(tree: Tree) -> None:
    _link(tree.store, "t0", "i1")

    header = tree.folders.tab_header(f"{ROOT}/House/Deep House")
    assert isinstance(header, TabHeader)
    assert header.title == "Deep House"
    assert header.kind_label == "Server folder"
    assert header.meta == "2 tracks · 1 on this computer"
    assert tree.folders.tab_title(f"{ROOT}/House/Deep House") == "Deep House"
    assert tree.folders.tab_header(f"{ROOT}/Techno").meta == "1 track · 0 on this computer"
    assert tree.folders.tab_title(f"{ROOT}/") == "Music"


def test_the_availability_badge_shows_on_folder_tabs_by_default(tree: Tree) -> None:
    column = availability_column(tree.context, tree.store)
    assert "remote.folder" in column.default_visible_for
    assert "playlist" in column.default_visible_for
