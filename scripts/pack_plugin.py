"""Pack a plugin package into a ``.mteeplugin`` file (plan 123.1, ``docs/plugins.md`` section 11).

Run from the core worktree::

    uv run python scripts/pack_plugin.py tests/plugins/sample --out .local/dist
    uv run python scripts/pack_plugin.py <plugin folder> --requirements <file> \\
        --wheel <file.whl> --out <dir> --licence GPL-3.0-or-later

The plugin folder is the package itself: it holds ``manifest.py`` and is named after the plugin
id. Libraries from ``--requirements`` and ``--wheel`` are installed for ``win_amd64`` and Python
3.12 into a temporary ``libs/`` folder. ``pip`` is not installed in the project environment
(``uv run python -m pip`` fails), so the installs use ``uv pip install``; ``--python-platform``
makes uv resolve for the target platform rather than for this machine. Libraries that MTEE ships
(its runtime closure, ``mtee.plugins.package.mtee_runtime_libraries``: not the development tools
of the environment) are never bundled: they are removed from ``libs/`` after the install, and the
plugin uses MTEE's copy. The packing stops
when the plugin's range does not accept MTEE's version. The install takes the whole requirements
file, because ``--require-hashes`` needs every dependency pinned in it; so the wheels of the
libraries MTEE ships are downloaded, hash-checked, then dropped.

A library that is published only as a source archive (``--allow-source NAME``, repeatable) is
built on this machine by uv; every other library must come as a wheel. The packing refuses such a
library when its build left compiled modules (``.pyd``, ``.so``): a Windows wheel is needed then.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from mtee.plugins.api import PluginManifest
from mtee.plugins.package import (
    LIBS_DIRECTORY,
    LICENSES_DIRECTORY,
    PACKAGE_SUFFIX,
    PLUGIN_JSON,
    PYTHON_VERSION,
    BundledLibrary,
    PluginDescription,
    bundled_distributions,
    distribution_name,
    mtee_runtime_libraries,
    normalize_name,
    record_paths,
    top_level_modules,
)

# The platforms a package can name, with the target triple uv resolves for.
PLATFORMS = {"win_amd64": "x86_64-pc-windows-msvc", "any": ""}
# The environment a requirement's marker is evaluated in: the platform the libraries are for.
TARGET_ENVIRONMENT = {
    "python_version": PYTHON_VERSION,
    "python_full_version": f"{PYTHON_VERSION}.0",
    "implementation_name": "cpython",
    "sys_platform": "win32",
    "os_name": "nt",
    "platform_system": "Windows",
    "platform_machine": "AMD64",
    "extra": "",
}
COMPILED_SUFFIXES = (".pyd", ".so")
MANIFEST_FILE = "manifest.py"
README_FILE = "README.md"
LICENCE_FILE = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE)", re.IGNORECASE)


class PackError(Exception):
    """The package cannot be built; the message is one sentence for the person who runs this."""


@dataclass(frozen=True, slots=True)
class RequirementLine:
    """One requirement of a requirements file. ``text`` is the logical line, its hashes included."""

    name: str
    display: str
    specifier: SpecifierSet
    # The version range as the file writes it (``>=2.28,<3``); ``specifier`` sorts its clauses.
    written: str
    text: str


@dataclass(frozen=True, slots=True)
class RequirementPlan:
    """The requirements MTEE does not ship, and the notes and names of those it does ship."""

    kept: tuple[RequirementLine, ...]
    notes: tuple[str, ...]
    provided: tuple[str, ...]


def read_requirements(text: str) -> list[RequirementLine]:
    """Read the requirements of a requirements file; ``--hash`` options stay on their line."""
    lines: list[RequirementLine] = []
    for logical in _logical_lines(text):
        requirement_text = re.split(r"\s+--", logical, maxsplit=1)[0].strip()
        if not requirement_text or requirement_text.startswith("-"):
            raise PackError(
                "The requirements file may list requirements and --hash options only, "
                f"not {logical!r}."
            )
        try:
            requirement = Requirement(requirement_text)
        except InvalidRequirement as error:
            raise PackError(f"{requirement_text!r} is not a valid requirement: {error}") from error
        if requirement.url:
            raise PackError(
                f"{requirement.name} is given by a URL; add its wheel with --wheel instead."
            )
        lines.append(
            RequirementLine(
                name=normalize_name(requirement.name),
                display=requirement.name,
                specifier=requirement.specifier,
                written=_written_range(requirement_text),
                text=logical,
            )
        )
    return lines


def _written_range(requirement_text: str) -> str:
    """Return the version range of a requirement as written, without spaces or brackets."""
    before_marker = requirement_text.split(";", 1)[0]
    match = re.match(
        r"^\s*[A-Za-z0-9][A-Za-z0-9._-]*\s*(\[[^\]]*\])?\s*\(?([^)]*?)\)?\s*$", before_marker
    )
    return match.group(2).replace(" ", "") if match else ""


def plan_requirements(
    lines: Sequence[RequirementLine], installed: Mapping[str, str]
) -> RequirementPlan:
    """Split the requirements into those MTEE ships and those to install.

    A requirement MTEE ships gets a note; it is refused, with one sentence, when the version
    MTEE ships is not the one the requirement accepts. The file given to uv keeps every line
    (``--require-hashes`` needs each dependency pinned), so ``prune_provided`` removes the
    MTEE-shipped distributions from ``libs/`` after the install.
    """
    kept: list[RequirementLine] = []
    provided: list[str] = []
    notes: list[str] = []
    for line in lines:
        version = installed.get(line.name)
        if version is None:
            kept.append(line)
            continue
        _check_accepted(line.display, line.specifier, version, "the plugin")
        provided.append(line.name)
        notes.append(f"Uses MTEE's {line.display} {version}")
    return RequirementPlan(kept=tuple(kept), notes=tuple(notes), provided=tuple(provided))


def prune_provided(
    libs: Path, installed: Mapping[str, str], reported: frozenset[str] = frozenset()
) -> list[str]:
    """Remove from ``libs`` the distributions MTEE ships; return a note for each one removed.

    Each one is checked against the requirement that pulled it in (when the bundled metadata
    names one), so a plugin never gets a copy of MTEE's library that it does not accept. A
    distribution whose name is in ``reported`` was already noted and gets no second note.
    """
    bundled = bundled_distributions(libs)
    pulled = _pulled_requirements(bundled)
    notes: list[str] = []
    for dist_info, distribution in bundled:
        name = distribution_name(distribution, dist_info)
        canonical = normalize_name(name)
        version = installed.get(canonical)
        if version is None:
            continue
        for pulling, specifier in pulled.get(canonical, []):
            _check_accepted(name, specifier, version, pulling)
        _remove_distribution(libs, dist_info)
        if canonical not in reported:
            notes.append(f"Uses MTEE's {name} {version}")
    return notes


def describe_libraries(
    libs: Path, licences: Path, lines: Mapping[str, RequirementLine]
) -> tuple[list[BundledLibrary], dict[str, str]]:
    """Describe the distributions left in ``libs`` and copy their licence texts to ``licences``.

    ``accepts`` is the requirement's specifier when the plugin lists the library, else the
    exact version bundled. Return the libraries (sorted by name) and the module map.
    """
    libraries: list[BundledLibrary] = []
    modules: dict[str, str] = {}
    for dist_info, distribution in bundled_distributions(libs):
        name = distribution_name(distribution, dist_info)
        version = distribution.version
        line = lines.get(normalize_name(name))
        accepts = line.written if line is not None and line.written else f"=={version}"
        libraries.append(BundledLibrary(name, version, accepts, _licence_name(distribution)))
        for module in top_level_modules(dist_info):
            modules.setdefault(module, name)
        if not _copy_licences(dist_info, name, licences):
            print(f"Warning: no licence text found for {name}; it is packed without one.")
    libraries.sort(key=lambda library: library.name.casefold())
    return libraries, dict(sorted(modules.items()))


def pack(
    plugin_dir: Path,
    out_dir: Path,
    *,
    requirements: Path | None = None,
    wheels: Sequence[Path] = (),
    author: str = "",
    homepage: str = "",
    licence: str = "",
    platform: str | None = None,
    source_only: Sequence[str] = (),
) -> Path:
    """Build the package of ``plugin_dir`` in ``out_dir`` and return its path.

    ``source_only`` names the libraries that are published only as a source archive; uv builds
    them, and the packing refuses one whose build has compiled modules.

    Raise ``PackError`` with one sentence when the package cannot be built. Nothing is
    overwritten: an existing package of the same id and version stops the packing.
    """
    manifest = _load_manifest(plugin_dir)
    if plugin_dir.name != manifest.plugin_id:
        raise PackError(
            f"The folder {plugin_dir.name} must be named after the plugin id {manifest.plugin_id}."
        )
    chosen = platform or ("win_amd64" if requirements or wheels else "any")
    if (requirements or wheels) and chosen == "any":
        raise PackError(
            "Bundled libraries are installed for win_amd64; use --platform win_amd64 "
            "with --requirements or --wheel."
        )
    for wheel in wheels:
        if not wheel.is_file():
            raise PackError(f"The wheel {wheel} does not exist.")
    output = out_dir / f"{manifest.plugin_id}-{manifest.version}{PACKAGE_SUFFIX}"
    if output.exists():
        raise PackError(f"{output} already exists; choose another --out folder or move it away.")
    text = _read_requirements_file(requirements)
    lines = read_requirements(text)
    installed = mtee_runtime_libraries()
    plan = plan_requirements(lines, installed)
    for note in plan.notes:
        print(note)
    if not licence:
        print("Warning: no --licence given; plugin.json names no licence.")

    with tempfile.TemporaryDirectory(prefix="mtee-pack-") as temp:
        staging = Path(temp)
        libs = staging / LIBS_DIRECTORY
        licences = staging / LICENSES_DIRECTORY
        libs.mkdir()
        licences.mkdir()
        if plan.kept:
            wanted = staging / "requirements.txt"
            wanted.write_text("".join(f"{line.text}\n" for line in lines), encoding="utf-8")
            hashes = ["--require-hashes"] if "--hash=" in text else []
            print(f"Installing {len(lines)} requirement(s) for {chosen}.")
            _install(libs, chosen, ["-r", str(wanted), *hashes], source_only)
            _check_source_builds(libs, source_only)
        for index, wheel in enumerate(wheels):
            part = staging / "wheels" / str(index)
            _install(part, chosen, ["--no-deps", str(wheel)])
            _merge(part, libs, wheel)
        for note in prune_provided(libs, installed, frozenset(plan.provided)):
            print(note)
        libraries, modules = describe_libraries(libs, licences, {line.name: line for line in lines})
        if not _copy_licences(plugin_dir, manifest.plugin_id, licences):
            print(f"Warning: no licence text found for {manifest.plugin_id}.")
        description = PluginDescription(
            id=manifest.plugin_id,
            title=manifest.title,
            description=manifest.description,
            version=manifest.version,
            api_version=manifest.api_version,
            author=author,
            homepage=homepage,
            licence=licence,
            uses_network=manifest.uses_network,
            python=PYTHON_VERSION,
            platform=chosen,
            mtee=_mtee_range(),
            libraries=tuple(libraries),
            top_level_modules=modules,
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_archive(output, description.to_json(), plugin_dir, manifest.plugin_id, staging)
    return output


def main(argv: Sequence[str] | None = None) -> int:
    """Pack the plugin named on the command line; return the process exit code."""
    args = _parser().parse_args(argv)
    try:
        output = pack(
            args.plugin_dir,
            args.out,
            requirements=args.requirements,
            wheels=args.wheel or [],
            author=args.author,
            homepage=args.homepage,
            licence=args.licence,
            platform=args.platform,
            source_only=args.allow_source or [],
        )
    except PackError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    print(f"Packed {output}")
    print(f"Size: {output.stat().st_size:,} bytes")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pack a plugin into a .mteeplugin file.")
    parser.add_argument("plugin_dir", type=Path, help="the plugin package: holds manifest.py")
    parser.add_argument("--out", type=Path, required=True, help="the folder to write into")
    parser.add_argument("--requirements", type=Path, help="a requirements file to bundle")
    parser.add_argument(
        "--wheel",
        type=Path,
        action="append",
        help="a wheel to bundle, installed without its dependencies (repeatable)",
    )
    parser.add_argument("--author", default="", help="the plugin's author")
    parser.add_argument("--homepage", default="", help="the plugin's homepage")
    parser.add_argument("--licence", default="", help="the plugin's licence, as an SPDX name")
    parser.add_argument(
        "--allow-source",
        action="append",
        metavar="NAME",
        help="a library published only as a source archive, built here (repeatable)",
    )
    parser.add_argument(
        "--platform",
        choices=sorted(PLATFORMS),
        help="win_amd64 for bundled libraries (the default then), or any",
    )
    return parser


def _load_manifest(plugin_dir: Path) -> PluginManifest:
    """Read ``MANIFEST`` from ``manifest.py`` of the folder, without adding it to ``sys.path``."""
    path = plugin_dir / MANIFEST_FILE
    if not path.is_file():
        raise PackError(f"{plugin_dir} has no {MANIFEST_FILE}.")
    spec = importlib.util.spec_from_file_location("_packed_plugin_manifest", path)
    if spec is None or spec.loader is None:
        raise PackError(f"{path} cannot be loaded.")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        raise PackError(f"{path} cannot be loaded: {error}") from error
    manifest = getattr(module, "MANIFEST", None)
    if not isinstance(manifest, PluginManifest):
        raise PackError(f"{path} does not define MANIFEST as a PluginManifest.")
    return manifest


def _read_requirements_file(path: Path | None) -> str:
    if path is None:
        return ""
    if not path.is_file():
        raise PackError(f"The requirements file {path} does not exist.")
    return path.read_text(encoding="utf-8")


def _logical_lines(text: str) -> list[str]:
    """Join the continued lines of a requirements file, without comments and blank lines."""
    lines: list[str] = []
    pending = ""
    for raw in text.splitlines():
        stripped = re.sub(r"(^|\s+)#.*$", "", raw).strip()
        if not stripped:
            continue
        if stripped.endswith("\\"):
            pending += stripped[:-1] + " "
            continue
        lines.append((pending + stripped).strip())
        pending = ""
    if pending.strip():
        lines.append(pending.strip())
    return lines


def _check_accepted(name: str, specifier: SpecifierSet, version: str, who: str) -> None:
    """Refuse, with one sentence, a version MTEE ships that ``who`` does not accept."""
    if specifier.contains(version, prereleases=True):
        return
    raise PackError(
        f"MTEE ships {name} {version}, but {who} requires {name} {specifier}; "
        "the plugin cannot use MTEE's copy, so it is not packed."
    )


def _mtee_range() -> str:
    """Return the MTEE versions a package is built for: the same minor version."""
    try:
        version = Version(importlib.metadata.version("mtee"))
    except importlib.metadata.PackageNotFoundError as error:
        raise PackError(
            "MTEE is not installed in this environment; its version is unknown."
        ) from error
    major, minor = (*version.release, 0)[:2]
    return f">={major}.{minor},<{major}.{minor + 1}"


def _install(
    target: Path, platform: str, options: Sequence[str], source_only: Sequence[str] = ()
) -> None:
    """Install into ``target`` with uv, for the target platform, from binary wheels only.

    The libraries named in ``source_only`` may be built from their source archive instead.
    """
    uv = shutil.which("uv")
    if uv is None:
        raise PackError("uv is needed to install the libraries and is not on the PATH.")
    allowed = [part for name in source_only for part in ("--no-binary", name)]
    command = [
        uv,
        "pip",
        "install",
        "--target",
        str(target),
        "--python-platform",
        PLATFORMS[platform],
        "--python-version",
        PYTHON_VERSION,
        "--only-binary",
        ":all:",
        *allowed,
        *options,
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
    )
    if result.returncode != 0:
        lines = (result.stderr or result.stdout).strip().splitlines()
        reason = lines[-1] if lines else "no message"
        raise PackError(f"uv could not install the libraries: {reason}")
    # uv leaves its lock file and the launchers of console scripts in the target folder; a
    # plugin imports modules and never runs them, so neither is part of the package.
    (target / ".lock").unlink(missing_ok=True)
    shutil.rmtree(target / "bin", ignore_errors=True)


def _check_source_builds(libs: Path, source_only: Sequence[str]) -> None:
    """Refuse a library built from its source archive that has compiled modules.

    A pure-Python library built here is fine; a compiled one would be a build for this machine,
    not for the target, so its Windows wheel is needed instead.
    """
    wanted = {normalize_name(name) for name in source_only}
    for dist_info, distribution in bundled_distributions(libs):
        name = distribution_name(distribution, dist_info)
        if normalize_name(name) not in wanted:
            continue
        if any(path.endswith(COMPILED_SUFFIXES) for path in record_paths(dist_info)):
            raise PackError(
                f"{name} was built from its source archive and has compiled modules; "
                "the plugin needs a Windows wheel of it."
            )


def _merge(source: Path, libs: Path, wheel: Path) -> None:
    """Move the installed entries of one wheel into ``libs``; a name given twice is refused."""
    for entry in sorted(source.iterdir()):
        target = libs / entry.name
        if target.exists():
            raise PackError(
                f"{wheel.name} provides {entry.name}, which a requirement also provides; "
                "list that library in one place only."
            )
        shutil.move(str(entry), str(target))


def _pulled_requirements(
    bundled: Sequence[tuple[Path, importlib.metadata.PathDistribution]],
) -> dict[str, list[tuple[str, SpecifierSet]]]:
    """Map each library name to the requirements of the bundled distributions that name it."""
    pulled: dict[str, list[tuple[str, SpecifierSet]]] = {}
    for dist_info, distribution in bundled:
        pulling = distribution_name(distribution, dist_info)
        for text in distribution.requires or []:
            try:
                requirement = Requirement(text)
            except InvalidRequirement:
                continue
            if requirement.marker and not requirement.marker.evaluate(TARGET_ENVIRONMENT):
                continue
            pulled.setdefault(normalize_name(requirement.name), []).append(
                (pulling, requirement.specifier)
            )
    return pulled


def _remove_distribution(libs: Path, dist_info: Path) -> None:
    """Delete the files a distribution lists in ``libs``, its ``.dist-info`` and empty folders."""
    root = libs.resolve()
    info = dist_info.resolve()
    for relative in record_paths(dist_info):
        target = (libs / relative).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            continue
        target.unlink()
        # Empty folders go too, but the .dist-info folder is removed last, below.
        parent = target.parent
        while (
            parent not in (root, info) and parent.is_relative_to(root) and not any(parent.iterdir())
        ):
            parent.rmdir()
            parent = parent.parent
    shutil.rmtree(dist_info, ignore_errors=True)


def _licence_name(distribution: importlib.metadata.Distribution) -> str:
    """Return the licence a distribution names in its metadata, or an empty string."""
    expression = distribution.metadata.get("License-Expression")
    if expression:
        return expression.strip()
    licence = (distribution.metadata.get("License") or "").strip()
    if licence and "\n" not in licence and len(licence) < 100:
        return licence
    for classifier in distribution.metadata.get_all("Classifier") or []:
        if classifier.startswith("License ::"):
            return classifier.rsplit("::", 1)[-1].strip()
    return ""


def _licence_texts(root: Path) -> dict[str, Path]:
    """Return the licence texts under ``root``, by their path below ``LICENSES/<name>/``."""
    texts: dict[str, Path] = {}
    licences = root / "licenses"
    if licences.is_dir():
        for source in sorted(licences.rglob("*")):
            if source.is_file():
                texts[source.relative_to(licences).as_posix()] = source
    for source in sorted(root.iterdir()):
        if source.is_file() and LICENCE_FILE.match(source.name):
            texts.setdefault(source.name, source)
    return texts


def _copy_licences(root: Path, name: str, destination: Path) -> int:
    """Copy the licence texts of ``root`` to ``destination/<name>``; return how many there are."""
    texts = _licence_texts(root)
    for relative, source in texts.items():
        target = destination / name / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return len(texts)


def _write_archive(
    output: Path, plugin_json: str, package_dir: Path, plugin_id: str, staging: Path
) -> None:
    """Write the package archive; ``"x"`` mode refuses to replace an existing file."""
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(PLUGIN_JSON, plugin_json)
        _add_tree(archive, package_dir, plugin_id)
        _add_tree(archive, staging / LIBS_DIRECTORY, LIBS_DIRECTORY)
        _add_tree(archive, staging / LICENSES_DIRECTORY, LICENSES_DIRECTORY)
        readme = package_dir / README_FILE
        if readme.is_file():
            archive.write(readme, README_FILE)


def _add_tree(archive: zipfile.ZipFile, root: Path, prefix: str) -> None:
    """Add ``root`` under ``prefix``, with its folders, skipping ``__pycache__`` and ``.pyc``."""
    archive.mkdir(prefix)
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or path.suffix == ".pyc":
            continue
        arcname = PurePosixPath(prefix, *relative.parts).as_posix()
        if path.is_dir():
            archive.mkdir(arcname)
        elif path.is_file():
            archive.write(path, arcname)


if __name__ == "__main__":
    sys.exit(main())
