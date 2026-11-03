"""The core contract tests (docs/plugins.md, Contract tests), run on the remote plugin.

The functions are the ones of ``tests/plugins/test_contract.py`` that take a ``plugin``; they
run here with the remote plugin folder. The migration checks skip: the plugin has no tables yet.
"""

from __future__ import annotations

from pathlib import Path

from tests.plugins import test_contract as contract
from tests.plugins.test_contract import ContractPlugin

PLUGIN_DIR = Path(__file__).resolve().parents[3] / "plugins"
REMOTE = ContractPlugin("remote", PLUGIN_DIR)

harness = contract.harness
test_it_loads_and_unloads_cleanly = contract.test_it_loads_and_unloads_cleanly
test_a_load_failure_disables_only_that_plugin = (
    contract.test_a_load_failure_disables_only_that_plugin
)
test_a_broken_contribution_disables_only_that_plugin = (
    contract.test_a_broken_contribution_disables_only_that_plugin
)
test_its_migrations_apply_on_an_empty_database = (
    contract.test_its_migrations_apply_on_an_empty_database
)
test_its_migrations_apply_on_a_copy_of_a_current_database = (
    contract.test_its_migrations_apply_on_a_copy_of_a_current_database
)
test_its_ui_entries_are_hidden_when_it_is_disabled = (
    contract.test_its_ui_entries_are_hidden_when_it_is_disabled
)
test_its_library_scan_hooks_take_the_scanned_folder_and_fail_nothing = (
    contract.test_its_library_scan_hooks_take_the_scanned_folder_and_fail_nothing
)
test_its_waiting_items_are_complete_and_hidden_with_the_plugin = (
    contract.test_its_waiting_items_are_complete_and_hidden_with_the_plugin
)
test_a_refused_manifest_never_imports_the_factory_module = (
    contract.test_a_refused_manifest_never_imports_the_factory_module
)


def pytest_generate_tests(metafunc: object) -> None:
    """Parametrize ``plugin`` with the remote plugin, as ``docs/plugins.md`` describes."""
    fixturenames = getattr(metafunc, "fixturenames", ())
    if "plugin" in fixturenames:
        metafunc.parametrize("plugin", [REMOTE], ids=["remote"])  # type: ignore[attr-defined]
