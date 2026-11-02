from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from mtee_remote.errors import ApiError
from mtee_remote.paths import normalize_relative_path, resolve_under


@pytest.mark.parametrize(
    "raw",
    [
        "a.flac",
        "Jazz/Miles Davis/So What.flac",
        "dossier avec espaces/été.mp3",
        "a/b/c/d.m4a",
        "..a/b..c/.hidden",
        "x" * 255,
        # Slash look-alikes are ordinary characters on Linux; real names use them.
        "AC\u2215DC/Back in Black.flac",
        "a\u2044b",
        "a\u2215..",
        "DJ TRACKS\u00cc\u0088IT.wav",  # a C1 control from a badly converted name
    ],
)
def test_valid_paths(raw: str) -> None:
    assert normalize_relative_path(raw) == raw


def test_paths_are_normalized_to_nfc() -> None:
    decomposed = "e\u0301te\u0301/morceau.flac"
    assert normalize_relative_path(decomposed) == "\u00e9t\u00e9/morceau.flac"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "/a",
        "a/../b",
        "..",
        ".",
        "a/./b",
        "a//b",
        "a/",
        "a\\b",
        "C:/x",
        "c:x",
        "\\\\server\\share",
        "//server/share",
        "a/\uff0e\uff0e/b",  # fullwidth dots
        "\uff0e\uff0e",
        "a/\uff0fb",  # fullwidth solidus
        "a\x00b",
        "a\x1fb",
        "a\x7fb",
        "x" * 256,
        "\u00e9" * 128,  # 256 bytes in UTF-8
        "a/" * 600 + "b",  # longer than 1024 characters
    ],
)
def test_rejected_paths(raw: str) -> None:
    with pytest.raises(ApiError) as error:
        normalize_relative_path(raw)
    assert error.value.code == "bad_request"
    assert error.value.status == 400


def test_resolve_under_returns_a_path_inside_base(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    assert resolve_under(tmp_path, "a/b.flac") == tmp_path / "a" / "b.flac"


def test_resolve_under_refuses_bad_paths(tmp_path: Path) -> None:
    with pytest.raises(ApiError):
        resolve_under(tmp_path, "../outside")


def _link_dir(link: Path, target: Path) -> None:
    """Make `link` a directory link to `target`: a symlink, or a junction on Windows."""
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        if sys.platform != "win32":
            pytest.skip("symlinks cannot be created here")
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=False
    )
    if result.returncode != 0:
        pytest.skip("neither symlinks nor junctions can be created here")


def test_resolve_under_refuses_a_symlink_escape(tmp_path: Path) -> None:
    base = tmp_path / "base"
    outside = tmp_path / "outside"
    base.mkdir()
    outside.mkdir()
    _link_dir(base / "link", outside)
    with pytest.raises(ApiError) as error:
        resolve_under(base, "link/secret.flac")
    assert error.value.code == "bad_request"
    # A link that stays inside the base is fine.
    (base / "real").mkdir()
    _link_dir(base / "inner", base / "real")
    assert resolve_under(base, "inner/x.flac") == base / "inner" / "x.flac"


@pytest.mark.skipif(sys.platform != "win32" and os.name != "nt", reason="Windows-only wording")
def test_windows_drive_forms_are_refused(tmp_path: Path) -> None:
    for raw in ("C:\\Windows", "C:/Windows", "D:file"):
        with pytest.raises(ApiError):
            resolve_under(tmp_path, raw)
