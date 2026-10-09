"""Disposable interaction model for the plan 110 user review.

It owns synthetic rows only. No genre, tag, review or move reaches the MTEE
database or the audio files; only an explicit Play uses the shared player.
"""

# Qt properties and slots keep the camelCase names consumed by QML.
# ruff: noqa: N802

from __future__ import annotations

import math
import wave
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.services.file_access import FileAccessCoordinator
from mtee.services.mpv_backend import MpvBackend
from mtee.services.player_backend import PlayerBackendError
from mtee.services.player_service import PlayerService

GENRES = ["House", "Deep House", "Minimal House", "Disco House", "UK Garage", "Breaks"]
TITLES = [
    "Midnight Transit",
    "Paper Lanterns",
    "Low Tide",
    "Satin Receiver",
    "After the Rain",
    "Quiet Signal",
    "Neon Steps",
    "Blue Hour",
    "Crossfade City",
    "First Light",
]


def create_audio_fixtures(data_dir: Path) -> list[Path]:
    """Generate ten short, quiet WAV clips within the isolated review directory."""
    audio_dir = data_dir / "synthetic-audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for index in range(10):
        path = audio_dir / f"review-{index + 1:02d}.wav"
        if not path.exists():
            with wave.open(str(path), "wb") as target:
                target.setnchannels(1)
                target.setsampwidth(2)
                target.setframerate(22_050)
                samples = bytearray()
                for sample in range(22_050 * 3):
                    fade = min(1.0, sample / 2205, (66_150 - sample) / 2205)
                    value = int(
                        3200 * fade * math.sin(2 * math.pi * (180 + index * 22) * sample / 22_050)
                    )
                    samples.extend(value.to_bytes(2, "little", signed=True))
                target.writeframes(samples)
        paths.append(path)
    return paths


class GenreReviewPrototype(QObject):
    changed = Signal()

    def __init__(
        self, data_dir: Path, variant: str, scenario: str, *, silent_audio: bool = False
    ) -> None:
        super().__init__()
        self._audio_paths = create_audio_fixtures(data_dir)
        self._variant = variant
        self._scenario = scenario
        self._section = "Classify"
        self._view = "All tracks"
        self._search = ""
        self._include_subfolders = False
        self._selected: list[str] = []
        self._anchor = 0
        self._brush_kind = "genre"
        self._brush_value = "Deep House"
        self._genres = list(GENRES)
        self._archived_genres: list[str] = []
        self._tags: list[str] = []
        self._tracks = self._make_tracks()
        self._history: list[tuple[list[dict[str, Any]], list[str], list[str], list[str]]] = []
        self._message = "Choose a source, then select tracks or a brush. Play is always explicit."
        self._error = ""
        self._fail_next = False
        self._pending: tuple[str, str, list[str], bool] | None = None
        self._preview: list[dict[str, str]] = []
        self._player: PlayerService | None = None
        self._player_error = ""
        self._silent_audio = silent_audio
        self._setup_player()

    def _make_tracks(self) -> list[dict[str, Any]]:
        count = 10 if self._scenario == "new" else 18 if self._scenario == "playlist" else 100
        tracks = []
        for index in range(count):
            identity = str(uuid5(NAMESPACE_URL, f"mtee-110-review-{index}"))
            genres = [] if self._scenario == "new" else (["House"] if index % 7 else [])
            if index % 11 == 0 and self._scenario != "new":
                genres = ["Deep House", "UK Garage"]
            if self._scenario == "batch" and index < 80 and not genres:
                genres = ["House"]
            tracks.append(
                {
                    "id": identity,
                    "title": TITLES[index % 10] + (f" {index // 10 + 1}" if index >= 10 else ""),
                    "artist": "Sample Artist" if index % 4 else "Guest Producer",
                    "source": "House" if index % 9 else "Inbox",
                    "path": str(self._audio_paths[index % 10]),
                    "genres": genres,
                    "tags": [],
                    "reviewed": index < 80 and self._scenario == "batch",
                }
            )
        return tracks

    def _setup_player(self) -> None:
        try:
            backend = MpvBackend(audio_output="null" if self._silent_audio else "wasapi")
        except PlayerBackendError as error:
            backend = None
            self._player_error = str(error)

        def resolve(identity: str) -> dict[str, Any]:
            row = next(item for item in self._tracks if item["id"] == identity)
            return {**row, "status": "readable", "seconds": 3}

        self._player = PlayerService(
            resolve,
            FileAccessCoordinator(),
            backend,
            backend_error=self._player_error,
            parent=self,
        )
        self._player.stateChanged.connect(self.changed.emit)

    def _visible_tracks(self) -> list[dict[str, Any]]:
        result = []
        for row in self._tracks:
            if self._view == "To review" and row["reviewed"]:
                continue
            if self._search and self._search not in (row["title"] + " " + row["artist"]).casefold():
                continue
            result.append({**row, "selected": row["id"] in self._selected})
        return result

    @Property(list, notify=changed)
    def tracks(self) -> list[dict[str, Any]]:
        return self._visible_tracks()

    @Property(str, notify=changed)
    def variant(self) -> str:
        return self._variant

    @Property(str, notify=changed)
    def scenario(self) -> str:
        return self._scenario

    @Property(str, notify=changed)
    def section(self) -> str:
        return self._section

    @Property(str, notify=changed)
    def view(self) -> str:
        return self._view

    @Property(bool, notify=changed)
    def includeSubfolders(self) -> bool:
        return self._include_subfolders

    @Property(str, notify=changed)
    def message(self) -> str:
        return self._message

    @Property(str, notify=changed)
    def error(self) -> str:
        return self._error

    @Property(str, notify=changed)
    def brushLabel(self) -> str:
        return f"{self._brush_kind}: {self._brush_value}"

    @Property(list, notify=changed)
    def tags(self) -> list[str]:
        return list(self._tags)

    @Property(list, notify=changed)
    def genres(self) -> list[str]:
        return list(self._genres)

    @Property(list, notify=changed)
    def archivedGenres(self) -> list[str]:
        return list(self._archived_genres)

    @Property(list, notify=changed)
    def preview(self) -> list[dict[str, str]]:
        return self._preview

    @Property(int, notify=changed)
    def selectedCount(self) -> int:
        return len(self._selected)

    @Property(int, notify=changed)
    def reviewedCount(self) -> int:
        return sum(bool(row["reviewed"]) for row in self._tracks)

    @Property(int, notify=changed)
    def totalCount(self) -> int:
        return len(self._tracks)

    @Property(str, notify=changed)
    def playingTitle(self) -> str:
        if self._player is None:
            return ""
        identity = str(self._player.state.current_id or "")
        row = next((row for row in self._tracks if row["id"] == identity), None)
        return str(row["title"]) if row else ""

    @Property(str, notify=changed)
    def playerError(self) -> str:
        return self._player_error

    @Slot(str)
    def setVariant(self, variant: str) -> None:
        if variant in {"selection", "brush"}:
            self._variant = variant
            self._message = f"{variant.capitalize()} mode. Classification state was kept."
            self.changed.emit()

    @Slot(str)
    def setScenario(self, scenario: str) -> None:
        if scenario not in {"house", "playlist", "batch", "new"}:
            return
        self._scenario = scenario
        self._tracks = self._make_tracks()
        self._selected = []
        self._history = []
        self._preview = []
        self._message = (
            "Synthetic source loaded. This prototype resets decisions when source changes."
        )
        self._error = ""
        self.changed.emit()

    @Slot(str)
    def setSection(self, section: str) -> None:
        if section in {"Classify", "Genres", "Uncertain", "Organize", "Plugins"}:
            self._section = section
            self.changed.emit()

    @Slot(str)
    def setView(self, view: str) -> None:
        if view in {"All tracks", "To review"}:
            self._view = view
            visible = {row["id"] for row in self._visible_tracks()}
            self._selected = [identity for identity in self._selected if identity in visible]
            self.changed.emit()

    @Slot(str)
    def setSearch(self, query: str) -> None:
        self._search = query.strip().casefold()
        visible = {row["id"] for row in self._visible_tracks()}
        self._selected = [identity for identity in self._selected if identity in visible]
        self.changed.emit()

    @Slot()
    def toggleSubfolders(self) -> None:
        self._include_subfolders = not self._include_subfolders
        self._message = "This synthetic folder has no nested tracks; the scope choice is visible."
        self.changed.emit()

    @Slot(str, int)
    def selectTrack(self, identity: str, modifiers: int) -> None:
        visible = [row["id"] for row in self._visible_tracks()]
        if identity not in visible:
            return
        index = visible.index(identity)
        if modifiers & 0x02000000:  # ShiftModifier
            start = min(self._anchor, index)
            end = max(self._anchor, index) + 1
            self._selected = list(dict.fromkeys([*self._selected, *visible[start:end]]))
        elif modifiers & 0x04000000:  # ControlModifier
            self._selected = (
                [item for item in self._selected if item != identity]
                if identity in self._selected
                else [*self._selected, identity]
            )
            self._anchor = index
        else:
            self._selected = [identity]
            self._anchor = index
        self.changed.emit()

    def _save_state(self) -> None:
        self._history.append(
            (
                deepcopy(self._tracks),
                list(self._tags),
                list(self._genres),
                list(self._archived_genres),
            )
        )
        if len(self._history) > 30:
            self._history.pop(0)

    def _apply(self, kind: str, value: str, identities: list[str], *, remove: bool = False) -> None:
        if not identities:
            self._message = "Select visible tracks first."
            self.changed.emit()
            return
        if self._fail_next:
            self._fail_next = False
            self._pending = (kind, value, identities, remove)
            self._error = f"Could not save {value}. Retry keeps the same target tracks."
            self.changed.emit()
            return
        self._save_state()
        changed = 0
        for row in self._tracks:
            if row["id"] not in identities:
                continue
            values = row["genres"] if kind == "genre" else row["tags"]
            row_changed = False
            if remove and value in values:
                values.remove(value)
                changed += 1
                row_changed = True
            elif not remove and value not in values:
                if kind == "genre" and values == ["House"] and value.endswith("House"):
                    values[:] = [value]
                else:
                    values.append(value)
                changed += 1
                row_changed = True
            if kind == "genre" and row_changed:
                row["reviewed"] = False
        self._error = ""
        self._pending = None
        self._message = (
            f"{value} {'removed from' if remove else 'added to'} {changed} track(s)."
            if changed
            else "No changes needed."
        )
        self.changed.emit()

    @Slot(str, str)
    def paletteAction(self, kind: str, value: str) -> None:
        if self._variant == "brush":
            self._brush_kind, self._brush_value = kind, value
            self._message = f"Brush ready: {value}. Click a row marker to add or remove it."
            self.changed.emit()
        else:
            self._apply(kind, value, list(self._selected))

    @Slot(str)
    def paintTrack(self, identity: str) -> None:
        row = next((item for item in self._tracks if item["id"] == identity), None)
        if row is None:
            return
        values = row["genres"] if self._brush_kind == "genre" else row["tags"]
        self._apply(
            self._brush_kind, self._brush_value, [identity], remove=self._brush_value in values
        )

    @Slot(str, str)
    def removeFromSelection(self, kind: str, value: str) -> None:
        self._apply(kind, value, list(self._selected), remove=True)

    @Slot(str, str)
    def makePrimary(self, identity: str, genre: str) -> None:
        row = next((item for item in self._tracks if item["id"] == identity), None)
        if row is None or genre not in row["genres"] or row["genres"][0] == genre:
            return
        self._save_state()
        row["genres"].remove(genre)
        row["genres"].insert(0, genre)
        row["reviewed"] = False
        self._message = f"{genre} is primary. Review is required again."
        self.changed.emit()

    @Slot()
    def markReviewed(self) -> None:
        if not self._selected:
            self._message = "Select tracks to mark as reviewed."
        else:
            self._save_state()
            for row in self._tracks:
                if row["id"] in self._selected:
                    row["reviewed"] = True
            self._message = f"Marked {len(self._selected)} track(s) as reviewed."
            self._selected = []
        self.changed.emit()

    @Slot(str)
    def createTag(self, name: str) -> None:
        name = name.strip()
        if name and name not in self._tags:
            self._save_state()
            self._tags.append(name)
            self._message = f"Tag {name} created. No tracks were tagged yet."
            self.changed.emit()

    @Slot(str, str)
    def createGenre(self, name: str, parent: str) -> None:
        name = name.strip()
        if parent == "House" and name and not name.casefold().endswith("house"):
            name += " House"
        if name and name not in self._genres and name not in self._archived_genres:
            self._save_state()
            self._genres.append(name)
            self._message = f"Genre {name} created in the prototype catalogue."
            self.changed.emit()

    @Slot(str, str)
    def renameGenre(self, old: str, new: str) -> None:
        new = new.strip()
        if old not in self._genres or not new or new in self._genres:
            return
        self._save_state()
        self._genres[self._genres.index(old)] = new
        for row in self._tracks:
            if old in row["genres"]:
                row["genres"][row["genres"].index(old)] = new
        self._message = f"Genre {old} renamed to {new} in this prototype."
        self.changed.emit()

    @Slot(str)
    def archiveGenre(self, name: str) -> None:
        if name in self._genres:
            self._save_state()
            self._genres.remove(name)
            self._archived_genres.append(name)
            self._message = f"{name} archived. Existing assignments remain visible."
            self.changed.emit()

    @Slot(str)
    def restoreGenre(self, name: str) -> None:
        if name in self._archived_genres:
            self._save_state()
            self._archived_genres.remove(name)
            self._genres.append(name)
            self._message = f"{name} restored."
            self.changed.emit()

    @Slot()
    def failNext(self) -> None:
        self._fail_next = True
        self._message = "The next genre or tag save will fail for review."
        self.changed.emit()

    @Slot()
    def retry(self) -> None:
        if self._pending:
            kind, value, identities, remove = self._pending
            self._apply(kind, value, identities, remove=remove)

    @Slot()
    def undo(self) -> None:
        if not self._history:
            self._message = "Nothing to undo."
        else:
            self._tracks, self._tags, self._genres, self._archived_genres = self._history.pop()
            self._message = "Last prototype action undone."
            self._error = ""
        self.changed.emit()

    @Slot()
    def preparePreview(self) -> None:
        self._preview = []
        for row in self._tracks:
            if row["reviewed"] and row["genres"]:
                primary = row["genres"][0]
                destination = (
                    f"House/{primary}"
                    if primary.endswith("House") and primary != "House"
                    else primary
                )
                self._preview.append(
                    {"title": row["title"], "from": row["source"], "to": destination}
                )
        self._section = "Organize"
        self._message = f"Preview only: {len(self._preview)} reviewed track(s), no file moved."
        self.changed.emit()

    @Slot(str)
    def playTrack(self, identity: str) -> None:
        if self._player is None:
            return
        index = next((index for index, row in enumerate(self._tracks) if row["id"] == identity), -1)
        if index < 0:
            return
        rows = [{**row, "status": "readable", "seconds": 3} for row in self._tracks]
        self._player.play_queue(
            [row["id"] for row in self._tracks],
            index,
            source="genre-review-110",
            source_title="Synthetic review",
            tracks=rows,
        )
        self._message = "Explicit Play sent to MTEE's native player. Classification did not change."
        self.changed.emit()

    @Slot()
    def togglePause(self) -> None:
        if self._player is not None:
            self._player.toggle_play()

    def close(self) -> None:
        if self._player is not None:
            self._player.close()

    def playback_status(self) -> str:
        return str(self._player.state.status) if self._player is not None else "Unavailable"
