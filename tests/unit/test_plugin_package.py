"""The plugin package format: the plugin.json round trip, its refusals and its manifest match."""

from __future__ import annotations

import json
import re

import pytest

from mtee.plugins.api import PluginManifest
from mtee.plugins.package import (
    BundledLibrary,
    PackageError,
    PluginDescription,
    description_matches_manifest,
    mtee_runtime_libraries,
    normalize_name,
)


def _data() -> dict[str, object]:
    """Return the JSON object of a valid plugin.json."""
    return {
        "schema": 1,
        "id": "sample",
        "title": "Sample plugin",
        "description": "One sentence for the user.",
        "version": "0.1.0",
        "api_version": 1,
        "author": "Ada",
        "homepage": "https://example.test/sample",
        "licence": "GPL-3.0-or-later",
        "uses_network": False,
        "python": "3.12",
        "platform": "win_amd64",
        "mtee": ">=0.1,<0.2",
        "libraries": [
            {
                "name": "requests",
                "version": "2.31.0",
                "accepts": "==2.31.0",
                "licence": "Apache-2.0",
            }
        ],
        "top_level_modules": {"requests": "requests"},
    }


def _text(**changes: object) -> str:
    data = _data()
    data.update(changes)
    return json.dumps(data)


def _description() -> PluginDescription:
    return PluginDescription.from_json(_text())


def _manifest(
    *, plugin_id: str = "sample", version: str = "0.1.0", api_version: int = 1
) -> PluginManifest:
    return PluginManifest(
        plugin_id=plugin_id,
        title="Sample plugin",
        description="One sentence for the user.",
        version=version,
        api_version=api_version,
        factory=f"mtee.plugins.{plugin_id}:create",
    )


def test_plugin_json_round_trips_through_its_text() -> None:
    description = _description()

    again = PluginDescription.from_json(description.to_json())

    assert again == description
    assert description.libraries == (
        BundledLibrary("requests", "2.31.0", "==2.31.0", "Apache-2.0"),
    )
    assert description.top_level_modules == {"requests": "requests"}


def test_plugin_json_is_written_with_sorted_keys_and_an_indent_of_two() -> None:
    text = _description().to_json()

    assert text.startswith('{\n  "api_version": 1,\n  "author": "Ada",\n')
    assert text.endswith("}\n")
    assert json.loads(text) == _data()


@pytest.mark.parametrize("key", sorted(_data()))
def test_a_missing_field_is_refused_with_a_sentence(key: str) -> None:
    data = _data()
    del data[key]

    with pytest.raises(PackageError, match=f"plugin.json has no {key} field."):
        PluginDescription.from_json(json.dumps(data))


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("id", 3),
        ("api_version", "1"),
        ("api_version", True),
        ("uses_network", "yes"),
        ("uses_network", 1),
        ("libraries", {}),
        ("top_level_modules", []),
        ("schema", "1"),
    ],
)
def test_a_field_of_the_wrong_type_is_refused(key: str, value: object) -> None:
    with pytest.raises(PackageError, match=f"The {key} field of plugin.json must be"):
        PluginDescription.from_json(_text(**{key: value}))


def test_an_unknown_schema_is_refused() -> None:
    with pytest.raises(
        PackageError, match=re.escape("plugin.json has schema 2, but this MTEE reads schema 1.")
    ):
        PluginDescription.from_json(_text(schema=2))


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("{", "is not valid JSON"),
        ("[]", "must hold one JSON object"),
    ],
)
def test_text_that_is_not_a_plugin_json_object_is_refused(text: str, reason: str) -> None:
    with pytest.raises(PackageError, match=reason):
        PluginDescription.from_json(text)


def test_a_library_without_its_version_is_refused() -> None:
    libraries = [{"name": "requests", "accepts": "==2.31.0", "licence": "Apache-2.0"}]

    with pytest.raises(
        PackageError, match=re.escape("library 1 of plugin.json has no version field.")
    ):
        PluginDescription.from_json(_text(libraries=libraries))


def test_a_library_that_is_not_an_object_is_refused() -> None:
    library = {"name": "requests", "version": "2.31.0", "accepts": "==2.31.0", "licence": "x"}

    with pytest.raises(
        PackageError, match=re.escape("Library 2 of plugin.json must be an object.")
    ):
        PluginDescription.from_json(_text(libraries=[library, "requests"]))


def test_a_module_mapped_to_a_non_text_is_refused() -> None:
    with pytest.raises(PackageError, match=re.escape("top_level_modules of plugin.json must map")):
        PluginDescription.from_json(_text(top_level_modules={"requests": 2}))


def test_a_plugin_json_that_matches_the_manifest_gives_no_problem() -> None:
    assert description_matches_manifest(_description(), _manifest()) == ""


def test_a_different_id_is_named_in_one_sentence() -> None:
    problem = description_matches_manifest(_description(), _manifest(plugin_id="other"))

    assert problem == ("plugin.json names the plugin 'sample', but manifest.py names 'other'.")


def test_a_different_version_is_named_in_one_sentence() -> None:
    problem = description_matches_manifest(_description(), _manifest(version="0.2.0"))

    assert problem == "plugin.json says version 0.1.0, but manifest.py says version 0.2.0."


def test_a_different_interface_version_is_named_in_one_sentence() -> None:
    problem = description_matches_manifest(_description(), _manifest(api_version=2))

    assert problem == "plugin.json says plugin interface 1, but manifest.py says 2."


_TREE: dict[str, list[str]] = {
    "mtee": ["Alpha_Lib>=1", "beta; extra == 'dev'", "gamma; sys_platform == 'linux'"],
    "alpha-lib": ["delta>=2", "absent"],
    "delta": ["alpha-lib", "epsilon; sys_platform == 'win32'"],
    "epsilon": [],
    "absent": ["hidden"],
    "hidden": [],
}
_VERSIONS = {"alpha-lib": "1.5", "delta": "2.0", "epsilon": "0.3", "gamma": "3.0", "beta": "9.0"}


def _lookup_requires(name: str) -> list[str] | None:
    return _TREE.get(name)


def _lookup_version(name: str) -> str | None:
    return _VERSIONS.get(name)


def test_the_runtime_closure_follows_requirements_and_keeps_names_normalized() -> None:
    shipped = mtee_runtime_libraries(
        requires=_lookup_requires,
        version=_lookup_version,
        environment={"sys_platform": "win32"},
    )

    assert shipped == {"alpha-lib": "1.5", "delta": "2.0", "epsilon": "0.3"}


def test_extras_and_markers_that_are_false_here_are_left_out() -> None:
    shipped = mtee_runtime_libraries(
        requires=_lookup_requires,
        version=_lookup_version,
        environment={"sys_platform": "linux"},
    )

    assert "beta" not in shipped
    assert "epsilon" not in shipped
    assert "gamma" in shipped


def test_a_requirement_that_is_not_installed_is_left_out_with_its_own_requirements() -> None:
    shipped = mtee_runtime_libraries(
        requires=_lookup_requires,
        version=_lookup_version,
        environment={"sys_platform": "win32"},
    )

    assert "absent" not in shipped
    assert "hidden" not in shipped


def test_a_distribution_that_is_not_installed_gives_an_empty_closure() -> None:
    assert mtee_runtime_libraries(requires=lambda name: None, version=lambda name: None) == {}


def test_the_closure_terminates_on_a_cycle() -> None:
    cycle = {"mtee": ["alpha"], "alpha": ["beta"], "beta": ["alpha"]}

    shipped = mtee_runtime_libraries(
        requires=lambda name: cycle.get(name),
        version=lambda name: "1.0",
        environment={},
    )

    assert shipped == {"alpha": "1.0", "beta": "1.0"}


def test_the_default_lookup_reads_the_installed_metadata() -> None:
    shipped = mtee_runtime_libraries()

    assert "pytest" not in shipped
    assert all(name == normalize_name(name) for name in shipped)


def test_normalize_name_follows_pep_503() -> None:
    assert normalize_name("PySide6_Essentials") == "pyside6-essentials"
    assert normalize_name("zope.interface") == "zope-interface"
