"""Installing a new source: checked, swapped in, the old one kept, the settings untouched."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from mtee_remote_admin.paths import Layout, Origin
from mtee_remote_admin.updater import UpdateError, install_archive, update


def make_archive(path: Path, files: dict[str, str], top: str = "mtee-remote-main") -> Path:
    with tarfile.open(path, "w:gz") as bundle:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f"{top}/{name}" if top else name)
            info.size = len(data)
            bundle.addfile(info, io.BytesIO(data))
    return path


SERVER = {"server/compose.yaml": "services: {}\n", "server/admin/pyproject.toml": "[project]\n"}


@pytest.fixture
def where(tmp_path: Path) -> Layout:
    return Layout(tmp_path / "home", tmp_path / "config")


def test_a_new_source_replaces_the_old_one_which_is_kept(where: Layout, tmp_path: Path) -> None:
    where.config.mkdir(parents=True)
    where.env_file.write_text("PORT=8080\n")
    install_archive(where, make_archive(tmp_path / "one.tgz", {**SERVER, "VERSION": "1"}))
    install_archive(where, make_archive(tmp_path / "two.tgz", {**SERVER, "VERSION": "2"}))

    assert (where.source / "VERSION").read_text() == "2"
    assert (where.previous_source / "VERSION").read_text() == "1"
    assert where.env_file.read_text() == "PORT=8080\n", "the settings are not in the source"
    assert [path.name for path in where.home.iterdir() if path.name.startswith(".")] == []


def test_an_archive_without_a_server_changes_nothing(where: Layout, tmp_path: Path) -> None:
    install_archive(where, make_archive(tmp_path / "one.tgz", {**SERVER, "VERSION": "1"}))
    with pytest.raises(UpdateError, match="no MTEE Remote server"):
        install_archive(where, make_archive(tmp_path / "bad.tgz", {"README.md": "hi"}))
    assert (where.source / "VERSION").read_text() == "1"


def test_an_entry_outside_the_folder_is_refused(where: Layout, tmp_path: Path) -> None:
    archive = make_archive(tmp_path / "evil.tgz", {**SERVER, "../outside.txt": "x"}, top="")
    with pytest.raises(UpdateError, match="could not be unpacked"):
        install_archive(where, archive)
    assert not (where.home.parent / "outside.txt").exists()
    assert not where.source.exists()


def test_update_downloads_the_tarball_of_the_origin(where: Layout, tmp_path: Path) -> None:
    archive = make_archive(tmp_path / "src.tgz", {**SERVER, "VERSION": "3"})
    asked: list[str] = []

    def opener(url: str, timeout: float) -> io.BufferedReader:
        asked.append(url)
        return open(archive, "rb")

    update(where, Origin("someone/mtee-remote", "v0.2.0"), opener)

    assert asked == ["https://codeload.github.com/someone/mtee-remote/tar.gz/v0.2.0"]
    assert (where.source / "VERSION").read_text() == "3"
