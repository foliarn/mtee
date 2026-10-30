"""The packing script: the archive it writes, the libraries MTEE ships, and its refusals.

The tests never call pip or uv. Every requirement they use is either shipped by MTEE, or no
requirement is given at all; the install step is not reached.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "tests" / "plugins" / "sample"


def _load_packer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "pack_plugin", ROOT / "scripts" / "pack_plugin.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered first: the dataclasses of the script look up their module while they are built.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


packer = _load_packer()


def _mtee_range() -> str:
    major, minor = importlib.metadata.version("mtee").split(".")[:2]
    return f">={major}.{minor},<{major}.{int(minor) + 1}"


def _fake_distribution(
    folder: Path,
    name: str,
    version: str,
    *,
    requires: tuple[str, ...] = (),
    top_level: str | None = None,
    modules: tuple[str, ...] = (),
    licence_files: dict[str, str] | None = None,
) -> Path:
    """Write a ``.dist-info`` folder, with the files its RECORD lists, in ``folder``."""
    dist_info = folder / f"{name}-{version}.dist-info"
    dist_info.mkdir(parents=True)
    metadata = ["Metadata-Version: 2.1", f"Name: {name}", f"Version: {version}"]
    metadata += [f"Requires-Dist: {text}" for text in requires]
    (dist_info / "METADATA").write_text("\n".join(metadata) + "\n", encoding="utf-8")
    if top_level is not None:
        (dist_info / "top_level.txt").write_text(top_level + "\n", encoding="utf-8")
    rows = list(modules)
    for module in modules:
        target = folder / module
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")
    for relative, text in (licence_files or {}).items():
        target = dist_info / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        rows.append(f"{dist_info.name}/{relative}")
    rows.append(f"{dist_info.name}/METADATA")
    (dist_info / "RECORD").write_text("".join(f"{row},,\n" for row in rows), encoding="utf-8")
    return dist_info


def test_packing_the_sample_writes_the_package_layout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status = packer.main(
        [
            str(SAMPLE),
            "--out",
            str(tmp_path),
            "--author",
            "Ada",
            "--licence",
            "GPL-3.0-or-later",
            "--homepage",
            "https://example.test/sample",
        ]
    )

    assert status == 0
    (package,) = tmp_path.glob("*.mteeplugin")
    assert package.name == "sample-0.1.0.mteeplugin"
    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
        description = json.loads(archive.read("plugin.json"))
    assert {
        "plugin.json",
        "sample/",
        "sample/manifest.py",
        "sample/__init__.py",
        "sample/migrations/001_sample_items.sql",
        "libs/",
        "LICENSES/",
    } <= names
    assert not [name for name in names if "__pycache__" in name or name.endswith(".pyc")]
    assert not [name for name in names if name.startswith("/") or ".." in name.split("/")]
    assert description["id"] == "sample"
    assert description["version"] == "0.1.0"
    assert description["api_version"] == 1
    assert description["python"] == "3.12"
    assert description["platform"] == "any"
    assert description["mtee"] == _mtee_range()
    assert description["libraries"] == []
    assert description["top_level_modules"] == {}
    assert description["author"] == "Ada"
    assert description["licence"] == "GPL-3.0-or-later"
    assert description["homepage"] == "https://example.test/sample"
    assert "Packed" in capsys.readouterr().out


def test_the_readme_and_the_plugin_licence_are_packed(tmp_path: Path) -> None:
    folder = tmp_path / "source" / "sample"
    shutil.copytree(SAMPLE, folder, ignore=shutil.ignore_patterns("__pycache__"))
    (folder / "README.md").write_bytes(b"# Sample\n")
    (folder / "LICENSE").write_bytes(b"GPL text\n")
    out = tmp_path / "out"

    assert packer.main([str(folder), "--out", str(out)]) == 0

    (package,) = out.glob("*.mteeplugin")
    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
        assert archive.read("README.md") == b"# Sample\n"
    assert "README.md" in names
    assert "LICENSES/sample/LICENSE" in names


def test_a_package_folder_named_otherwise_than_its_id_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    renamed = tmp_path / "renamed"
    shutil.copytree(SAMPLE, renamed, ignore=shutil.ignore_patterns("__pycache__"))

    status = packer.main([str(renamed), "--out", str(tmp_path / "out")])

    assert status == 2
    assert "must be named after the plugin id sample" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_an_existing_package_is_never_overwritten(tmp_path: Path) -> None:
    assert packer.main([str(SAMPLE), "--out", str(tmp_path)]) == 0

    assert packer.main([str(SAMPLE), "--out", str(tmp_path)]) == 2


def test_a_requirement_mtee_ships_is_not_bundled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("mutagen>=0.1\n", encoding="utf-8")

    status = packer.main([str(SAMPLE), "--requirements", str(requirements), "--out", str(tmp_path)])

    assert status == 0
    assert "Uses MTEE's mutagen " in capsys.readouterr().out
    (package,) = tmp_path.glob("*.mteeplugin")
    with zipfile.ZipFile(package) as archive:
        description = json.loads(archive.read("plugin.json"))
        assert not [
            name for name in archive.namelist() if name.startswith("libs/") and name != "libs/"
        ]
    assert description["libraries"] == []
    assert description["platform"] == "win_amd64"


def test_a_requirement_mtee_ships_at_another_version_stops_the_packing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("mutagen<0\n", encoding="utf-8")

    status = packer.main([str(SAMPLE), "--requirements", str(requirements), "--out", str(tmp_path)])

    assert status == 2
    error = capsys.readouterr().err
    assert "MTEE ships mutagen" in error
    assert "cannot use MTEE's copy" in error
    assert not list(tmp_path.glob("*.mteeplugin"))


def test_libraries_need_a_windows_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("mutagen>=0.1\n", encoding="utf-8")

    status = packer.main(
        [
            str(SAMPLE),
            "--requirements",
            str(requirements),
            "--out",
            str(tmp_path),
            "--platform",
            "any",
        ]
    )

    assert status == 2
    assert "use --platform win_amd64" in capsys.readouterr().err


def test_requirement_lines_keep_their_hashes_and_their_specifier() -> None:
    text = (
        "# pinned by hand\n"
        "Requests==2.31.0 \\\n"
        "    --hash=sha256:aaa \\\n"
        "    --hash=sha256:bbb\n"
        "typing_extensions>=4.12,<5  # for typing\n"
    )

    lines = packer.read_requirements(text)

    assert [line.name for line in lines] == ["requests", "typing-extensions"]
    assert str(lines[0].specifier) == "==2.31.0"
    assert lines[0].text.split() == [
        "Requests==2.31.0",
        "--hash=sha256:aaa",
        "--hash=sha256:bbb",
    ]
    assert lines[1].written == ">=4.12,<5"


def test_a_requirements_file_may_not_name_options_other_than_hashes() -> None:
    with pytest.raises(packer.PackError, match="may list requirements and --hash options only"):
        packer.read_requirements("-r other.txt\n")


def test_a_library_mtee_ships_is_left_out_when_the_plugin_accepts_it() -> None:
    lines = packer.read_requirements("Typing_Extensions>=4.12\nfake-lib==1.0\n")

    plan = packer.plan_requirements(lines, {"typing-extensions": "4.13.0"})

    assert [line.name for line in plan.kept] == ["fake-lib"]
    assert plan.notes == ("Uses MTEE's Typing_Extensions 4.13.0",)


def test_a_library_mtee_ships_at_a_version_the_plugin_refuses_stops_the_packing() -> None:
    lines = packer.read_requirements("requests<2.30\n")

    with pytest.raises(packer.PackError) as refused:
        packer.plan_requirements(lines, {"requests": "2.31.0"})

    assert str(refused.value) == (
        "MTEE ships requests 2.31.0, but the plugin requires requests <2.30; "
        "the plugin cannot use MTEE's copy, so it is not packed."
    )


def test_a_dependency_mtee_ships_is_removed_after_checking_the_requirement_that_pulled_it(
    tmp_path: Path,
) -> None:
    libs = tmp_path / "libs"
    _fake_distribution(libs, "Dep", "1.0.0", modules=("dep.py",))
    _fake_distribution(libs, "User", "2.0.0", requires=("dep>=1.0",), modules=("user.py",))

    notes = packer.prune_provided(libs, {"dep": "1.0.5"})

    assert notes == ["Uses MTEE's Dep 1.0.5"]
    assert not (libs / "dep.py").exists()
    assert not (libs / "Dep-1.0.0.dist-info").exists()
    assert (libs / "user.py").exists()


def test_a_dependency_pulled_by_a_requirement_mtee_does_not_accept_stops_the_packing(
    tmp_path: Path,
) -> None:
    libs = tmp_path / "libs"
    _fake_distribution(libs, "Dep", "1.0.0", modules=("dep.py",))
    _fake_distribution(libs, "User", "2.0.0", requires=("dep>=1.0",))

    with pytest.raises(packer.PackError, match=re.escape("User requires Dep >=1.0")):
        packer.prune_provided(libs, {"dep": "0.9"})
    assert (libs / "dep.py").exists()


def test_a_requirement_for_another_extra_does_not_constrain_the_dependency(tmp_path: Path) -> None:
    libs = tmp_path / "libs"
    _fake_distribution(libs, "Dep", "1.0.0", modules=("dep.py",))
    _fake_distribution(libs, "User", "2.0.0", requires=('dep>=1.0; extra == "socks"',))

    assert packer.prune_provided(libs, {"dep": "0.9"}) == ["Uses MTEE's Dep 0.9"]


def test_top_level_modules_come_from_top_level_txt_or_from_record(tmp_path: Path) -> None:
    libs = tmp_path / "libs"
    _fake_distribution(libs, "Alpha", "1.0", top_level="alpha\n", modules=("alpha/__init__.py",))
    _fake_distribution(
        libs,
        "Beta",
        "2.0",
        modules=("beta/__init__.py", "beta/core.py", "_native.cp312-win_amd64.pyd"),
    )

    libraries, modules = packer.describe_libraries(libs, tmp_path / "licences", {})

    assert modules == {"_native": "Beta", "alpha": "Alpha", "beta": "Beta"}
    assert [(library.name, library.version, library.accepts) for library in libraries] == [
        ("Alpha", "1.0", "==1.0"),
        ("Beta", "2.0", "==2.0"),
    ]


def test_the_accepted_range_of_a_listed_library_is_its_specifier(tmp_path: Path) -> None:
    libs = tmp_path / "libs"
    _fake_distribution(libs, "Alpha", "1.5", top_level="alpha\n")
    lines = {"alpha": packer.read_requirements("Alpha>=1,<2\n")[0]}

    libraries, _ = packer.describe_libraries(libs, tmp_path / "licences", lines)

    assert libraries[0].accepts == ">=1,<2"


def test_licence_texts_are_copied_and_a_missing_one_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    libs = tmp_path / "libs"
    licences = tmp_path / "licences"
    _fake_distribution(
        libs,
        "Alpha",
        "1.0",
        top_level="alpha\n",
        licence_files={"licenses/LICENSE.txt": "MIT text\n", "NOTICE": "Notice text\n"},
    )
    _fake_distribution(libs, "Beta", "2.0", top_level="beta\n")

    packer.describe_libraries(libs, licences, {})

    assert (licences / "Alpha" / "LICENSE.txt").read_text(encoding="utf-8") == "MIT text\n"
    assert (licences / "Alpha" / "NOTICE").read_text(encoding="utf-8") == "Notice text\n"
    assert not (licences / "Beta").exists()
    assert "no licence text found for Beta" in capsys.readouterr().out


def test_mtee_runtime_libraries_are_the_closure_not_the_dev_environment() -> None:
    shipped = packer.mtee_runtime_libraries()

    assert "mtee" not in shipped  # the closure holds the libraries MTEE needs, not MTEE itself
    assert "pytest" not in shipped
    assert "pyinstaller" not in shipped
    assert all(name == canonicalize_name(name) for name in shipped)
    assert shipped["pyside6-essentials"] == importlib.metadata.version("PySide6-Essentials")
