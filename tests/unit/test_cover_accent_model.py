from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QImage

from mtee.domain.tracks import SourceRevision
from mtee.models.cover_accent_model import CoverAccentModel


@dataclass
class _State:
    current_id: str = ""


class _Player(QObject):
    stateChanged = Signal()  # noqa: N815 - Qt naming

    def __init__(self) -> None:
        super().__init__()
        self.state = _State()

    def play(self, track_id: str) -> None:
        self.state = _State(track_id)
        self.stateChanged.emit()


class _Library:
    def __init__(self) -> None:
        self.paths: dict[str, Path] = {}

    def artwork_source(self, track_id: str):
        path = self.paths.get(track_id)
        return None if path is None else (path, SourceRevision(1, 1, None, 3))


class _Artwork:
    """Stand-in artwork reader: files named ``*.png`` in the test hold a solid colour."""

    def __init__(self, colours: dict[str, str]) -> None:
        self.colours = colours
        self.reads: list[str] = []

    def image_bytes(self, path: Path | str) -> bytes | None:
        colour = self.colours.get(Path(path).stem)
        return b"image" if colour else None

    def thumbnail(self, path: Path | str, size: int) -> QImage:
        self.reads.append(Path(path).stem)
        image = QImage(size, size, QImage.Format.Format_RGB32)
        image.fill(QColor(self.colours[Path(path).stem]))
        return image


def _near(first: str, second: str) -> bool:
    one, two = QColor(first), QColor(second)
    return (
        max(
            abs(one.red() - two.red()), abs(one.green() - two.green()), abs(one.blue() - two.blue())
        )
        <= 2
    )


def _model(qapp, colours: dict[str, str]):
    player, library, artwork = _Player(), _Library(), _Artwork(colours)
    for name in ("vivid", "green", "plain"):
        library.paths[name] = Path(f"{name}.mp3")
    model = CoverAccentModel(player, library, qapp, artwork=artwork)  # type: ignore[arg-type]
    return player, model, artwork


def test_the_accent_follows_the_playing_cover_off_the_interface_thread(qapp, qtbot) -> None:
    player, model, _artwork = _model(qapp, {"vivid": "#E0245E", "green": "#1FA34A"})
    assert not model.hasAccent and model.baseColor == ""
    player.play("vivid")
    qtbot.waitUntil(lambda: model.hasAccent)
    assert _near(cast(str, model.baseColor), "#E0245E")
    assert QColor(model.darkColor).valueF() < QColor(model.baseColor).valueF()
    assert model.foregroundColor == "#FFFFFF" and not model.isLight


def test_a_track_without_artwork_or_in_no_library_has_no_accent(qapp, qtbot) -> None:
    player, model, _artwork = _model(qapp, {"vivid": "#E0245E"})
    player.play("vivid")
    qtbot.waitUntil(lambda: model.hasAccent)
    player.play("plain")  # known to the library, but its file holds no cover
    qtbot.waitUntil(lambda: not model.hasAccent)
    player.play("vivid")
    qtbot.waitUntil(lambda: model.hasAccent)
    player.play("unknown")  # not in the library at all
    assert not model.hasAccent


def test_the_previous_accent_stays_until_the_next_one_is_known(qapp, qtbot) -> None:
    player, model, _artwork = _model(qapp, {"vivid": "#E0245E", "green": "#1FA34A"})
    player.play("vivid")
    qtbot.waitUntil(lambda: model.hasAccent)
    changes: list[str] = []
    model.accentChanged.connect(lambda: changes.append(cast(str, model.baseColor)))
    player.play("green")
    old = cast(str, model.baseColor)
    assert _near(old, "#E0245E")  # still the old one while computing
    qtbot.waitUntil(lambda: model.baseColor != old)
    assert changes and "" not in changes  # a direct change, never through "no accent"


def test_the_result_of_a_track_that_is_no_longer_playing_is_ignored(qapp, qtbot) -> None:
    player, model, artwork = _model(qapp, {"vivid": "#E0245E", "green": "#1FA34A"})
    player.play("vivid")
    player.play("green")  # before the first computation is delivered
    qtbot.waitUntil(lambda: model.hasAccent)
    qtbot.waitUntil(lambda: set(artwork.reads) >= {"vivid", "green"}, timeout=3000)
    qtbot.wait(100)
    assert abs(QColor(model.baseColor).hue() - QColor("#1FA34A").hue()) <= 8  # green, not red


def test_a_cover_is_decoded_once_and_then_served_from_memory(qapp, qtbot) -> None:
    player, model, artwork = _model(qapp, {"vivid": "#E0245E", "green": "#1FA34A"})
    player.play("vivid")
    qtbot.waitUntil(lambda: model.hasAccent)
    player.play("green")
    qtbot.waitUntil(lambda: model.baseColor != "#E0245E")
    reads = len(artwork.reads)
    player.play("vivid")
    assert model.baseColor == "#E0245E"  # immediately, from the cache
    assert len(artwork.reads) == reads


def test_a_white_cover_gives_a_light_card_with_dark_text(qapp, qtbot) -> None:
    player, model, _artwork = _model(qapp, {"vivid": "#FFFFFF"})
    assert model.foregroundColor == "#FFFFFF" and not model.isLight  # nothing yet
    player.play("vivid")
    qtbot.waitUntil(lambda: model.hasAccent)
    assert _near(cast(str, model.baseColor), "#FFFFFF")
    assert model.isLight and model.foregroundColor == "#0A0A0A"
