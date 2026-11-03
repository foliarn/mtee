"""The first-match rules, as a table (plan 126.2). Pure: no file, no database, no server."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from mtee.plugins.remote.matcher import (  # pyright: ignore[reportMissingImports]
    DUPLICATE,
    UNREADABLE,
    LocalTrack,
    MatchResult,
    ServerItem,
    match,
)


def local(track_id: str, path: str, sha: str | None, audio: str | None) -> LocalTrack:
    return LocalTrack(track_id, path, sha, audio)


def server(item_id: str, path: str, sha: str, audio: str | None, revision: int = 1) -> ServerItem:
    return ServerItem(item_id, "root-1", path, sha, audio, revision=revision)


@dataclass(frozen=True)
class Case:
    name: str
    local: list[LocalTrack]
    server: list[ServerItem]
    counts: dict[str, int]


CASES = [
    Case(
        "identical files are matched",
        [local("l1", "a.flac", "s1", "A1")],
        [server("v1", "a.flac", "s1", "A1")],
        {"matched": 1, "tags_differ": 0, "to_upload": 0, "server_only": 0, "not_matched": 0},
    ),
    Case(
        "same audio with different tags differs by its SHA-256",
        [local("l1", "a.flac", "s1", "A1")],
        [server("v1", "a.flac", "s2", "A1")],
        {"matched": 0, "tags_differ": 1, "to_upload": 0, "server_only": 0, "not_matched": 0},
    ),
    Case(
        "no audio hash on the local side compares the SHA-256 alone",
        [local("l1", "a.flac", "s1", None)],
        [server("v1", "a.flac", "s1", "A1")],
        {"matched": 1, "tags_differ": 0, "to_upload": 0, "server_only": 0, "not_matched": 0},
    ),
    Case(
        "no audio hash on the server side compares the SHA-256 alone",
        [local("l1", "a.flac", "s1", "A1")],
        [server("v1", "a.flac", "s1", None)],
        {"matched": 1, "tags_differ": 0, "to_upload": 0, "server_only": 0, "not_matched": 0},
    ),
    Case(
        "no audio hash on either side and other bytes: nothing pairs",
        [local("l1", "a.flac", "s1", None)],
        [server("v1", "a.flac", "s2", None)],
        {"matched": 0, "tags_differ": 0, "to_upload": 1, "server_only": 1, "not_matched": 0},
    ),
    Case(
        "a local track whose hash failed is not matched",
        [local("l1", "a.flac", None, None)],
        [server("v1", "a.flac", "s1", "A1")],
        {"matched": 0, "tags_differ": 0, "to_upload": 0, "server_only": 1, "not_matched": 1},
    ),
    Case(
        "a local track with no server copy goes up",
        [local("l1", "a.flac", "s1", "A1")],
        [],
        {"matched": 0, "tags_differ": 0, "to_upload": 1, "server_only": 0, "not_matched": 0},
    ),
    Case(
        "a server item with no local track is server only",
        [],
        [server("v1", "a.flac", "s1", "A1")],
        {"matched": 0, "tags_differ": 0, "to_upload": 0, "server_only": 1, "not_matched": 0},
    ),
    Case(
        "two local copies of one audio: the one with the server's path is matched",
        [local("l1", "a.flac", "s1", "A1"), local("l2", "b.flac", "s1", "A1")],
        [server("v1", "b.flac", "s1", "A1")],
        {"matched": 1, "tags_differ": 0, "to_upload": 0, "server_only": 0, "not_matched": 1},
    ),
    Case(
        "two local copies, no path equal: the first by path is matched, the other is a duplicate",
        [local("l2", "b.flac", "s1", "A1"), local("l1", "a.flac", "s1", "A1")],
        [server("v1", "c.flac", "s1", "A1")],
        {"matched": 1, "tags_differ": 0, "to_upload": 0, "server_only": 0, "not_matched": 1},
    ),
    Case(
        "two server items with one audio: the one with the local path is paired, the other stays",
        [local("l1", "b.flac", "s1", "A1")],
        [server("v1", "a.flac", "s1", "A1"), server("v2", "b.flac", "s1", "A1")],
        {"matched": 1, "tags_differ": 0, "to_upload": 0, "server_only": 1, "not_matched": 0},
    ),
    Case(
        "two local copies with no server copy: the first goes up, the second is a duplicate",
        [local("l1", "a.flac", "s1", "A1"), local("l2", "b.flac", "s2", "A1")],
        [],
        {"matched": 0, "tags_differ": 0, "to_upload": 1, "server_only": 0, "not_matched": 1},
    ),
    Case(
        "an unreadable local track is not matched, even when the server has its path",
        [local("l1", "a.flac", None, None)],
        [server("v1", "a.flac", "s1", "A1")],
        {"matched": 0, "tags_differ": 0, "to_upload": 0, "server_only": 1, "not_matched": 1},
    ),
    Case(
        "a mixed folder: each rule applies to its own tracks",
        [
            local("l1", "same.flac", "s1", "A1"),
            local("l2", "tags.flac", "s2", "A2"),
            local("l3", "new.flac", "s3", "A3"),
            local("l4", "copy.flac", "s1", "A1"),
            local("l5", "broken.flac", None, None),
        ],
        [
            server("v1", "same.flac", "s1", "A1"),
            server("v2", "tags.flac", "s9", "A2"),
            server("v3", "only.flac", "s4", "A4"),
        ],
        {"matched": 1, "tags_differ": 1, "to_upload": 1, "server_only": 1, "not_matched": 2},
    ),
]


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_the_rules_give_the_expected_counts(case: Case) -> None:
    result = match(case.local, case.server)
    assert result.counts == case.counts


def test_the_matched_pair_is_the_one_with_the_path_equal() -> None:
    result = match(
        [local("l1", "a.flac", "s1", "A1"), local("l2", "b.flac", "s1", "A1")],
        [server("v1", "b.flac", "s1", "A1")],
    )
    assert [(pair.local.track_id, pair.server.item_id) for pair in result.matched] == [("l2", "v1")]
    assert [entry.local.track_id for entry in result.not_matched] == ["l1"]
    assert result.not_matched[0].reason == DUPLICATE


def test_the_reasons_of_the_not_matched_tracks_are_named() -> None:
    result = match(
        [
            local("l1", "broken.flac", None, None),
            local("l2", "a.flac", "s1", "A1"),
            local("l3", "copy.flac", "s1", "A1"),
        ],
        [server("v1", "a.flac", "s1", "A1")],
    )
    reasons = {entry.local.track_id: entry.reason for entry in result.not_matched}
    assert reasons == {"l1": UNREADABLE, "l3": DUPLICATE}


def test_a_tag_difference_keeps_both_sides() -> None:
    result = match([local("l1", "a.flac", "s1", "A1")], [server("v1", "a.flac", "s2", "A1", 7)])
    (pair,) = result.tags_differ
    assert pair.local.sha256 == "s1"
    assert pair.server.sha256 == "s2"
    assert pair.server.revision == 7


def test_the_result_order_does_not_depend_on_the_input_order() -> None:
    locals_ = [local("l2", "b.flac", "s2", "A2"), local("l1", "a.flac", "s1", None)]
    servers = [server("v2", "b.flac", "s9", "A2"), server("v1", "a.flac", "s1", "A1")]
    forward = match(locals_, servers)
    backward = match(list(reversed(locals_)), list(reversed(servers)))
    assert forward == backward


def test_merged_results_add_their_lists() -> None:
    first = match([local("l1", "a.flac", "s1", "A1")], [server("v1", "a.flac", "s1", "A1")])
    second = match([local("l2", "b.flac", "s2", "A2")], [])
    merged = MatchResult.merged([first, second])
    assert merged.counts == {
        "matched": 1,
        "to_upload": 1,
        "server_only": 0,
        "tags_differ": 0,
        "not_matched": 0,
    }
