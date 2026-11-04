"""The Plugins view in the live window (plan 123.6): sidebar, detail tab and dialogs.

The states are driven through ``FakePluginsView`` (``tests/helpers/plugins_view_fake.py``), which
has the properties and slots of the real model. The real application is started once to check that
the Plugins activity is there with no plugin installed. It is not opened there, because opening the
Marketplace reads the plugin list from the network.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from tests.helpers.plugins_view_fake import FakePluginsView, use_fake_view
from tests.helpers.ui_plugin import find_item, start_app, visible_texts, window_of, workspace_of

from mtee.app import _build_runtime, _Runtime, _shutdown, create_application
from mtee.cli import AppOptions
from mtee.models.demo_workspace import DemoWorkspace


def pump(rounds: int = 12) -> None:
    """Let the queued signals, the bindings and the layouts of QML run.

    A positioner (Column, Row) lays its children out when the window polishes, which an offscreen
    window does on its frame timer; a short sleep between the event passes lets that frame come.
    """
    for _ in range(rounds):
        QCoreApplication.processEvents()
        time.sleep(0.01)


def click(window: QQuickWindow, item: QQuickItem) -> None:
    """A left click at the centre of ``item``."""
    centre = item.mapToScene(item.boundingRect().center()).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centre)
    pump()


def scroll_to_end_of_page(item: QQuickItem) -> None:
    """Scroll the nearest flickable above ``item`` to its end, so the item is on screen."""
    flickable = item.parentItem()
    while flickable is not None and flickable.property("contentY") is None:
        flickable = flickable.parentItem()
    assert flickable is not None, "no flickable above the item"
    flickable.setProperty(
        "contentY", float(flickable.property("contentHeight")) - float(flickable.property("height"))
    )
    pump()


def visible(window: QQuickWindow, name: str) -> bool:
    item = find_item(window, name)
    return item is not None and item.isVisible()


def text_of(window: QQuickWindow, name: str) -> str:
    item = find_item(window, name)
    assert item is not None, f"no QML item named {name}"
    return str(item.property("text"))


def active_tab(workspace: DemoWorkspace) -> str:
    """The id of the active tab of the focused group, such as ``plugin:spotify``."""
    untyped = cast(Any, workspace)
    return str(untyped.activeTabId)


class DemoContext:
    """The demo window with a Plugins view the test sets."""

    def __init__(self, application: Any, runtime: _Runtime, view: FakePluginsView) -> None:
        self.application = application
        self.runtime = runtime
        self.window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
        self.workspace = cast(DemoWorkspace, runtime.workspace)
        self.view = view


@pytest.fixture
def demo(
    qapp: QCoreApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[DemoContext]:
    use_fake_view(monkeypatch)
    application = create_application(["mtee"])
    runtime = _build_runtime(
        application, AppOptions(data_dir=tmp_path / "demo", demo=True, scenario="explorer")
    )
    assert runtime is not None
    window = window_of(runtime)
    window.resize(1440, 900)
    workspace = cast(DemoWorkspace, runtime.workspace)
    view = cast(FakePluginsView, workspace.pluginsView)
    workspace.setActivity("plugins")
    pump()
    context = DemoContext(application, runtime, view)
    yield context
    runtime.jobs.shutdown()
    for root in runtime.engine.rootObjects():
        root.deleteLater()
    runtime.engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    runtime.database.close()
    application.quit()


def test_the_plugins_activity_is_there_with_no_plugin_installed(qapp, tmp_path: Path) -> None:
    runtime = start_app(tmp_path / "data")
    try:
        window = window_of(runtime)
        workspace = workspace_of(runtime)
        button = find_item(window, "activity-plugins")
        assert button is not None and button.isVisible()
        assert cast(Any, workspace).pluginsView.property("installed") == []
    finally:
        _shutdown(runtime)


def test_the_pane_lists_the_installed_plugins_with_their_status_words(demo: DemoContext) -> None:
    window = demo.window
    for plugin_id in ("spotify", "sample", "genre_manager", "convert"):
        assert visible(window, f"pluginsInstalled_{plugin_id}"), plugin_id
    for plugin_id in ("artist_manager", "loudness_report"):
        assert visible(window, f"pluginsMarket_{plugin_id}@foliarn/mtee-plugins"), plugin_id
    texts = visible_texts(window)
    # A tag only on an installed plugin: Running, Failed (warning) or Installed (plan 132.6, P8).
    for word in ("Running", "Failed", "Installed"):
        assert word in texts, word
    for word in ("Disabled", "Restart needed", "Update to 1.2.0"):
        assert word not in texts, word


def test_each_plugin_is_listed_once_in_the_order_of_the_one_list(demo: DemoContext) -> None:
    window = demo.window
    # Convert is installed and also listed by the Marketplace: one row, the installed one.
    assert find_item(window, "pluginsMarket_convert@foliarn/mtee-plugins") is None
    names = [
        "pluginsInstalled_convert",
        "pluginsInstalled_genre_manager",
        "pluginsInstalled_sample",
        "pluginsInstalled_spotify",
        "pluginsMarket_artist_manager@foliarn/mtee-plugins",
        "pluginsMarket_loudness_report@foliarn/mtee-plugins",
    ]
    tops = [float(cast(QQuickItem, find_item(window, name)).property("y")) for name in names]
    assert tops == sorted(tops) and len(set(tops)) == len(tops)
    assert "Convert" in visible_texts(window)
    installed_rows = [name for name in names if name.startswith("pluginsInstalled_")]
    assert len(installed_rows) == 4


def test_the_marketplace_is_requested_when_the_pane_opens(demo: DemoContext) -> None:
    assert ("marketplaceRequested",) in demo.view.calls


def test_search_filters_the_one_list(demo: DemoContext) -> None:
    window = demo.window
    demo.view.set_search("spot")
    pump()
    assert visible(window, "pluginsInstalled_spotify")
    assert find_item(window, "pluginsInstalled_sample") is None
    assert find_item(window, "pluginsMarket_convert@foliarn/mtee-plugins") is None


def test_typing_in_the_search_field_sets_the_search(demo: DemoContext) -> None:
    window = demo.window
    field = find_item(window, "pluginsSearch")
    assert field is not None
    field.forceActiveFocus()
    pump()
    for letter in "spot":
        QTest.keyClick(window, getattr(Qt.Key, f"Key_{letter.upper()}"))
    pump()
    assert demo.view.property("search") == "spot"
    assert find_item(window, "pluginsInstalled_sample") is None


def test_a_row_opens_the_plugin_tab(demo: DemoContext) -> None:
    window = demo.window
    click(window, cast(QQuickItem, find_item(window, "pluginsInstalled_spotify")))
    assert active_tab(demo.workspace) == "plugin:spotify"
    assert text_of(window, "pluginDetailTitle") == "Spotify"
    assert "version 1.0.0" in text_of(window, "pluginDetailByline")


def test_the_detail_has_the_switch_and_the_uninstall(demo: DemoContext) -> None:
    window = demo.window
    demo.view.openDetail("spotify")
    pump()
    assert visible(window, "toggle_pluginDetailSwitch")
    uninstall = find_item(window, "action_pluginDetailUninstall")
    assert uninstall is not None and uninstall.isVisible()
    assert uninstall.property("text") == "Uninstall"
    assert "The plugin goes to the Recycle Bin. Its data stays." in visible_texts(window)


def test_the_switch_saves_through_the_view(demo: DemoContext) -> None:
    window = demo.window
    demo.view.openDetail("spotify")
    pump()
    click(window, cast(QQuickItem, find_item(window, "toggle_pluginDetailSwitch")))
    assert ("setEnabled", "spotify", False) in demo.view.calls


def test_uninstall_has_no_prompt_and_the_detail_says_so(demo: DemoContext) -> None:
    window = demo.window
    click(window, cast(QQuickItem, find_item(window, "pluginsInstalled_spotify")))
    button = cast(QQuickItem, find_item(window, "action_pluginDetailUninstall"))
    scroll_to_end_of_page(button)
    click(window, button)
    assert ("uninstall", "spotify") in demo.view.calls
    assert visible(window, "pluginDetailGone")
    assert text_of(window, "pluginDetailGone") == (
        "This plugin was uninstalled. Restart MTEE to finish."
    )


def test_a_marketplace_plugin_offers_install(demo: DemoContext) -> None:
    window = demo.window
    click(
        window,
        cast(QQuickItem, find_item(window, "pluginsMarket_artist_manager@foliarn/mtee-plugins")),
    )
    assert active_tab(demo.workspace) == "plugin:artist_manager@foliarn/mtee-plugins"
    action = find_item(window, "action_pluginDetailAction")
    assert action is not None and action.property("text") == "Install"
    assert not visible(window, "pluginDetailSwitch")
    click(window, action)
    assert ("install", "artist_manager@foliarn/mtee-plugins") in demo.view.calls


def test_an_installed_plugin_with_a_newer_version_offers_the_update(demo: DemoContext) -> None:
    window = demo.window
    click(window, cast(QQuickItem, find_item(window, "pluginsInstalled_convert")))
    action = find_item(window, "action_pluginDetailAction")
    assert action is not None and action.property("text") == "Update to 1.2.0"
    click(window, action)
    assert ("update", "convert@foliarn/mtee-plugins") in demo.view.calls


def test_an_install_waits_in_the_warning_dialog(demo: DemoContext) -> None:
    window = demo.window
    assert not visible(window, "pluginInstallSource")
    demo.view.set_pending(
        {
            "title": "Spotify",
            "version": "1.0.0",
            "author": "Axel Raux",
            "sizeText": "2 MB",
            "usesNetwork": True,
            "librariesCount": 6,
            "source": "file",
            "sourceText": "Local file: spotify-1.0.0.mteeplugin",
        }
    )
    pump()
    assert "Install Spotify 1.0.0?" in visible_texts(window)
    assert text_of(window, "pluginInstallSource") == "Local file: spotify-1.0.0.mteeplugin"
    assert visible(window, "pluginInstallWarning")
    click(window, cast(QQuickItem, find_item(window, "pluginInstallCancel")))
    assert ("cancelInstall",) in demo.view.calls
    assert not visible(window, "pluginInstallSource")


def test_a_refused_install_shows_the_reason_until_closed(demo: DemoContext) -> None:
    window = demo.window
    demo.view.set_refusal("Spotify 1.0.0 was not installed", "The plugin needs MTEE 0.3 or later.")
    pump()
    assert visible(window, "pluginRefusalText")
    assert text_of(window, "pluginRefusalText") == "The plugin needs MTEE 0.3 or later."
    assert "Spotify 1.0.0 was not installed" in visible_texts(window)
    click(window, cast(QQuickItem, find_item(window, "pluginRefusalClose")))
    assert ("dismissRefusal",) in demo.view.calls
    assert not visible(window, "pluginRefusalText")


def test_the_marketplace_empty_state_says_no_plugin_is_listed(demo: DemoContext) -> None:
    window = demo.window
    demo.view.set_marketplace("ready", rows=[])
    pump()
    assert visible(window, "marketplaceEmpty")
    assert text_of(window, "marketplaceEmpty") == "No plugins are listed yet."
    assert find_item(window, "pluginsMarket_convert@foliarn/mtee-plugins") is None


def test_the_marketplace_failure_says_why_and_offers_a_new_check(demo: DemoContext) -> None:
    window = demo.window
    demo.view.set_marketplace(
        "failed", rows=[], error="The plugin list could not be read: no connection."
    )
    pump()
    assert visible(window, "marketplaceFailed")
    assert "The plugin list could not be read: no connection." in visible_texts(window)
    click(window, cast(QQuickItem, find_item(window, "marketplaceCheckAgain")))
    assert ("checkMarketplace",) in demo.view.calls


def test_the_restart_footer_shows_only_when_a_restart_is_needed(demo: DemoContext) -> None:
    window = demo.window
    assert visible(window, "pluginsRestartNow")
    assert text_of(window, "pluginsRestartText") == "1 plugin needs a restart"
    demo.view.set_restart([])
    pump()
    assert not visible(window, "pluginsRestartNow")
    assert not visible(window, "pluginsRestartText")


def test_the_restart_button_calls_the_view(demo: DemoContext) -> None:
    window = demo.window
    click(window, cast(QQuickItem, find_item(window, "pluginsRestartNow")))
    assert ("restartNow",) in demo.view.calls


def test_the_pane_refreshes_the_plugin_list_after_an_uninstall(demo: DemoContext) -> None:
    window = demo.window
    demo.view.uninstall("sample")
    pump()
    assert find_item(window, "pluginsInstalled_sample") is None
    assert visible(window, "pluginsInstalled_spotify")
