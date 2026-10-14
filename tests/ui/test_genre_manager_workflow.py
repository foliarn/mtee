"""The real MTEE shell opens Genre Manager without loading it on startup."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from mtee.app import _build_runtime, create_application
from mtee.cli import AppOptions
from mtee.models.workspace_model import WorkspaceModel


def _find_item(root: QQuickItem, name: str) -> QQuickItem | None:
    pending = list(root.childItems())
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            return item
        pending.extend(item.childItems())
    return None


def test_real_shell_opens_classify_and_catalogue_lazily(qapp, tmp_path: Path, monkeypatch) -> None:
    # v0.1 hides the plugins: this test checks the Genre Manager as the plugin switch enables it.
    monkeypatch.setattr("mtee.plugins.registry.PLUGIN_UI_ENABLED", True)
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "genre-ui", demo=False))
    assert runtime is not None
    window = runtime.engine.rootObjects()[0]
    assert isinstance(window, QQuickWindow)
    workspace = runtime.workspace
    assert isinstance(workspace, WorkspaceModel)
    diagnostics: list[str] = []
    runtime.engine.warnings.connect(lambda warnings: diagnostics.extend(str(w) for w in warnings))
    try:
        assert workspace.genreManager is None
        workspace.openGenreManagerView("classify", "Genre Manager")
        QCoreApplication.processEvents()
        assert workspace.genreManager is not None
        assert _find_item(window.contentItem(), "genreClassifyPage") is not None
        QTest.qWait(100)
        workspace.openGenreManagerView("genres", "Genres & tags")
        QCoreApplication.processEvents()
        assert _find_item(window.contentItem(), "genreCataloguePage") is not None
        QTest.qWait(100)
        workspace.openGenreManagerView("organize", "Organize files")
        QCoreApplication.processEvents()
        assert _find_item(window.contentItem(), "genreOrganizePage") is not None
        QTest.qWait(100)
        workspace.openGenreManagerView("uncertain", "Uncertain")
        QCoreApplication.processEvents()
        assert _find_item(window.contentItem(), "genreUncertainPage") is not None
        assert not diagnostics
    finally:
        runtime.jobs.shutdown()
        workspace.flush_session()
        for item in runtime.engine.rootObjects():
            item.deleteLater()
        runtime.engine.deleteLater()
        QCoreApplication.processEvents()
        runtime.database.close()
        application.quit()
