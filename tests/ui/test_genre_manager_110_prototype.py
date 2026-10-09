"""Checks for the isolated comparison shown to the user before plan 110.2."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow

from mtee.assets import qml_dir
from mtee.models.icon_provider import ICON_PROVIDER_ID, IconProvider
from mtee.prototypes import genre_manager_110 as review_module
from mtee.services.player_backend import PlayerBackendError


def _prototype(monkeypatch, tmp_path: Path, scenario: str = "house"):
    def no_audio(**_kwargs):
        raise PlayerBackendError("Audio disabled for this test")

    monkeypatch.setattr(review_module, "MpvBackend", no_audio)
    return review_module.GenreReviewPrototype(tmp_path, "selection", scenario)


def test_house_refinement_and_review_are_explicit(qapp, monkeypatch, tmp_path: Path) -> None:
    prototype = _prototype(monkeypatch, tmp_path)
    try:
        row = prototype._tracks[1]
        assert row["genres"] == []
        prototype.selectTrack(row["id"], 0)
        prototype.paletteAction("genre", "Deep House")
        assert row["genres"] == ["Deep House"]
        assert not row["reviewed"]
        prototype.markReviewed()
        assert row["reviewed"]
        prototype.createTag("banger")
        prototype.selectTrack(row["id"], 0)
        prototype.paletteAction("tag", "banger")
        assert row["reviewed"]
        prototype.paletteAction("genre", "Minimal House")
        assert not row["reviewed"]
        prototype.makePrimary(row["id"], "Minimal House")
        assert row["genres"] == ["Minimal House", "Deep House"]
    finally:
        prototype.close()


def test_source_selection_does_not_infer_genre_and_bulk_choice_is_explicit(
    qapp, monkeypatch, tmp_path: Path
) -> None:
    prototype = _prototype(monkeypatch, tmp_path)
    try:
        assert prototype.sourceName == "House"
        assert prototype.sourceKind == "folder"
        assert all(not row["genres"] for row in prototype._tracks)
        assert len([row for row in prototype.sourceOptions if row["kind"] == "folder"]) == 3
        prototype.setScenario("playlist")
        assert prototype.sourceKind == "playlist"
        assert all(not row["genres"] for row in prototype._tracks)
        prototype.tagFolderSongs("House")
        assert all(not row["genres"] for row in prototype._tracks)
        prototype.setScenario("house")
        prototype.tagFolderSongs("Deep House")
        assert all(row["genres"] == ["Deep House"] for row in prototype._tracks)
        assert prototype.reviewedCount == 0
        assert (
            next(source for source in prototype.sourceOptions if source["id"] == "house")[
                "completion"
            ]
            == 0
        )
        prototype.selectTrack(prototype._tracks[0]["id"], 0)
        prototype.markReviewed()
        assert (
            next(source for source in prototype.sourceOptions if source["id"] == "house")[
                "completion"
            ]
            == 1
        )
        prototype.undo()
        prototype.undo()
        assert all(not row["genres"] for row in prototype._tracks)
    finally:
        prototype.close()


def test_catalogue_scales_and_creates_under_selected_root(
    qapp, monkeypatch, tmp_path: Path
) -> None:
    prototype = _prototype(monkeypatch, tmp_path)
    try:
        assert len(prototype.genreRows) > 20
        assert {row["name"] for row in prototype.genreRows if row["root"]} >= {"House", "Techno"}
        prototype.archiveGenre("House")
        assert "House" in prototype.genres
        prototype.createGenre("Electro", "")
        prototype.createGenre("Electro Swing", "Electro")
        child = next(row for row in prototype.genreRows if row["name"] == "Electro Swing")
        assert child["parent"] == "Electro"
        prototype.undo()
        assert "Electro Swing" not in prototype.genres
    finally:
        prototype.close()


def test_brush_retries_once_and_never_selects_or_plays(qapp, monkeypatch, tmp_path: Path) -> None:
    prototype = _prototype(monkeypatch, tmp_path)
    try:
        row = prototype._tracks[2]
        prototype.setVariant("brush")
        prototype.paletteAction("tag", "banger")
        prototype.failNext()
        prototype.paintTrack(row["id"])
        assert row["tags"] == []
        assert prototype._selected == []
        assert prototype._player is not None
        assert not prototype._player.state.current_id
        prototype.retry()
        assert row["tags"] == ["banger"]
        prototype.paintTrack(row["id"])
        assert row["tags"] == []
        prototype.undo()
        assert prototype._tracks[2]["tags"] == ["banger"]
        prototype.failNext()
        prototype.paintTrack(row["id"])
        assert prototype._tracks[2]["tags"] == ["banger"]
        prototype.retry()
        assert prototype._tracks[2]["tags"] == []
    finally:
        prototype.close()


def test_batch_preview_has_only_the_eighty_reviewed_tracks(
    qapp, monkeypatch, tmp_path: Path
) -> None:
    prototype = _prototype(monkeypatch, tmp_path, "batch")
    try:
        assert sum(row["reviewed"] for row in prototype._tracks) == 80
        prototype.preparePreview()
        assert len(prototype._preview) == 80
        assert all(row["to"] for row in prototype._preview)
        assert not (tmp_path / "synthetic-library").exists()
    finally:
        prototype.close()


def test_qml_sections_load_at_reference_and_reduced_widths(
    qapp, monkeypatch, tmp_path: Path
) -> None:
    prototype = _prototype(monkeypatch, tmp_path)
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(qml_dir()))
    engine.addImageProvider(ICON_PROVIDER_ID, IconProvider())
    engine.rootContext().setContextProperty("prototype", prototype)
    engine.load(
        QUrl.fromLocalFile(str(qml_dir() / "prototypes/genre_manager_110/ReviewWindow.qml"))
    )
    try:
        assert engine.rootObjects()
        window = engine.rootObjects()[0]
        assert isinstance(window, QQuickWindow)
        window.setWidth(1440)
        window.setHeight(900)
        for section in ("Classify", "Genres", "Uncertain", "Organize", "Plugins"):
            prototype.setSection(section)
            QCoreApplication.processEvents()
        window.setWidth(1100)
        window.setHeight(760)
        prototype.setSection("Genres")
        QCoreApplication.processEvents()
        genre_list = window.findChild(QObject, "genreTreeList")
        assert genre_list is not None
        assert genre_list.property("contentHeight") > genre_list.property("height")
        prototype.setVariant("brush")
        prototype.setSection("Classify")
        QCoreApplication.processEvents()
        assert window.findChild(QObject, "sourceButton") is not None
        window.openSourcePicker()
        QCoreApplication.processEvents()
        picker = window.findChild(QObject, "sourcePicker")
        assert picker is not None and picker.property("visible")
        assert window.objectName() == "genreManager110Review"
    finally:
        prototype.close()
        for root in engine.rootObjects():
            root.deleteLater()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
