"""Qt bridge for the deterministic UX prototype.

Actions in this object only change memory. The prototype intentionally has no
path access, metadata writer, player or converter behind its controls.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.demo.scenarios import SCENARIO_NAMES, DemoScenario, load_scenario

__all__ = ["DemoWorkspace"]


_TRACKS = (
    {
        "title": "Carrier Wave",
        "artist": "Loop Foundry",
        "genre": "Techno",
        "bpm": "134",
        "key": "5A",
        "duration": "7:12",
        "format": "FLAC",
        "filename": "carrier_wave.flac",
        "folder": "Collection / Sets 2026",
        "artwork": True,
    },
    {
        "title": "Night Drive / Extended Instrumental Mix",
        "artist": "Mira Kline",
        "genre": "",
        "bpm": "128",
        "key": "8A",
        "duration": "6:48",
        "format": "MP3",
        "filename": "night_drive_extended.mp3",
        "folder": "Downloads",
        "artwork": True,
    },
    {
        "title": "Ritual Signal",
        "artist": "North Terminal",
        "genre": "Electro",
        "bpm": "126",
        "key": "11A",
        "duration": "5:03",
        "format": "WAV",
        "filename": "ritual_signal.wav",
        "folder": "Collection / Sets 2026",
        "artwork": False,
    },
    {
        "title": "Soft Errors (Live at Le Sucre, Lyon)",
        "artist": "Aster & Vale",
        "genre": "Ambient",
        "bpm": "—",
        "key": "—",
        "duration": "9:41",
        "format": "FLAC",
        "filename": "soft_errors_live.flac",
        "folder": "Collection / Live",
        "artwork": True,
    },
    {
        "title": "Untitled field recording 04",
        "artist": "",
        "genre": "Field recording",
        "bpm": "—",
        "key": "—",
        "duration": "2:26",
        "format": "WAV",
        "filename": "04_été_ambiance.wav",
        "folder": "Samples / Échantillons",
        "artwork": False,
    },
    {
        "title": "Low Orbit",
        "artist": "Distant Objects",
        "genre": "Breaks",
        "bpm": "140",
        "key": "2B",
        "duration": "4:38",
        "format": "MP3",
        "filename": "low_orbit.mp3",
        "folder": "Downloads",
        "artwork": True,
    },
)


class DemoWorkspace(QObject):
    """State and actions exposed to QML for one demo session."""

    scenarioChanged = Signal()
    screenChanged = Signal()
    tracksChanged = Signal()
    selectionChanged = Signal()
    playingChanged = Signal()
    inspectorVisibleChanged = Signal()
    splitViewChanged = Signal()
    artworkViewChanged = Signal()
    saveStateChanged = Signal()
    conversionErrorChanged = Signal()

    def __init__(self, scenario: str = "browser", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._scenario: DemoScenario = load_scenario(scenario)
        self._tracks = [deepcopy(track) for track in _TRACKS]
        self._selected_rows = list(self._scenario.selected_rows)
        self._playing_row = self._scenario.playing_row
        self._save_state = self._scenario.save_state

    @Property(str, notify=scenarioChanged)
    def scenarioName(self) -> str:
        return self._scenario.name

    @Property(str, notify=screenChanged)
    def screen(self) -> str:
        return self._scenario.screen

    @Property(list, notify=tracksChanged)
    def tracks(self) -> list[dict[str, object]]:
        return deepcopy(self._tracks)

    @Property(list, notify=selectionChanged)
    def selectedRows(self) -> list[int]:
        return list(self._selected_rows)

    @Property(int, notify=playingChanged)
    def playingRow(self) -> int:
        return self._playing_row

    @Property(bool, notify=inspectorVisibleChanged)
    def inspectorVisible(self) -> bool:
        return self._scenario.inspector_visible

    @Property(bool, notify=splitViewChanged)
    def splitView(self) -> bool:
        return self._scenario.split_view

    @Property(bool, notify=artworkViewChanged)
    def artworkView(self) -> bool:
        return self._scenario.artwork_view

    @Property(bool, constant=True)
    def multiSelection(self) -> bool:
        return self._scenario.multi_selection

    @Property(bool, constant=True)
    def noArtwork(self) -> bool:
        return self._scenario.no_artwork

    @Property(str, notify=saveStateChanged)
    def saveState(self) -> str:
        return self._save_state

    @Property(bool, notify=conversionErrorChanged)
    def conversionError(self) -> bool:
        return self._scenario.conversion_error

    @Property(list, constant=True)
    def queue(self) -> list[dict[str, str]]:
        return [
            {"position": "01", "title": "Carrier Wave", "artist": "Loop Foundry"},
            {"position": "02", "title": "Ritual Signal", "artist": "North Terminal"},
            {"position": "03", "title": "Low Orbit", "artist": "Distant Objects"},
        ]

    @Slot(str)
    def loadScenario(self, name: str) -> None:
        """Replace all in-memory state with a deterministic scenario."""
        scenario = load_scenario(name)
        previous_screen = self._scenario.screen
        previous_inspector = self._scenario.inspector_visible
        previous_split = self._scenario.split_view
        previous_artwork = self._scenario.artwork_view
        self._scenario = scenario
        self._selected_rows = list(scenario.selected_rows)
        self._playing_row = scenario.playing_row
        self._save_state = scenario.save_state
        self.scenarioChanged.emit()
        self.selectionChanged.emit()
        self.playingChanged.emit()
        self.saveStateChanged.emit()
        if previous_screen != scenario.screen:
            self.screenChanged.emit()
        if previous_inspector != scenario.inspector_visible:
            self.inspectorVisibleChanged.emit()
        if previous_split != scenario.split_view:
            self.splitViewChanged.emit()
        if previous_artwork != scenario.artwork_view:
            self.artworkViewChanged.emit()

    @Slot(str)
    def setScreen(self, screen: str) -> None:
        """Switch between the three prototype spaces."""
        if screen not in {"browser", "listening", "convert"}:
            raise ValueError(f"Unsupported demo screen: {screen}")
        if screen == self._scenario.screen:
            return
        self._scenario = replace(self._scenario, screen=screen)
        self.screenChanged.emit()

    @Slot(int, bool)
    def selectRow(self, row: int, additive: bool = False) -> None:
        """Change the fictitious selection, preserving multi-select semantics."""
        if not 0 <= row < len(self._tracks):
            return
        if additive and self._scenario.multi_selection:
            if row in self._selected_rows:
                self._selected_rows.remove(row)
            else:
                self._selected_rows.append(row)
        else:
            self._selected_rows = [row]
        self.selectionChanged.emit()

    @Slot(int)
    def playRow(self, row: int) -> None:
        """Set a fictitious playing row independently from selection."""
        if 0 <= row < len(self._tracks) and row != self._playing_row:
            self._playing_row = row
            self.playingChanged.emit()

    @Slot(bool)
    def setInspectorVisible(self, visible: bool) -> None:
        if bool(visible) == self._scenario.inspector_visible:
            return
        self._scenario = replace(self._scenario, inspector_visible=bool(visible))
        self.inspectorVisibleChanged.emit()

    @Slot(bool)
    def setSplitView(self, enabled: bool) -> None:
        if bool(enabled) == self._scenario.split_view:
            return
        self._scenario = replace(self._scenario, split_view=bool(enabled))
        self.splitViewChanged.emit()

    @Slot(bool)
    def setArtworkView(self, enabled: bool) -> None:
        if bool(enabled) == self._scenario.artwork_view:
            return
        self._scenario = replace(self._scenario, artwork_view=bool(enabled))
        self.artworkViewChanged.emit()

    @Slot(str)
    def setSaveState(self, state: str) -> None:
        """Set the visual save state without writing metadata."""
        if state not in {"idle", "saving", "saved", "error"}:
            raise ValueError(f"Unsupported save state: {state}")
        if state != self._save_state:
            self._save_state = state
            self.saveStateChanged.emit()

    @Slot()
    def retryConversion(self) -> None:
        """Clear only the visible conversion error in the prototype."""
        if self._scenario.conversion_error:
            self._scenario = replace(self._scenario, conversion_error=False)
            self.conversionErrorChanged.emit()

    @staticmethod
    def scenarioNames() -> list[str]:
        """Return all names for command-line and test discovery."""
        return list(SCENARIO_NAMES)
