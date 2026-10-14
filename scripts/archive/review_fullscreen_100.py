"""Open or capture the illustrative fullscreen player review (plan 100.0).

The mock-up is self-contained: simulated clock, no audio output, no service. The
optional ``--audio`` and ``--covers`` arguments read local files to judge the
design with real material; they are never copied and never used by ``--capture``.
The two prototypes below are references for milestones 100.1 and 100.4 and are not
imported by the application.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow

from mtee.fonts import register_fonts, resolve_ui_family
from mtee.models.icon_provider import IconProvider

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/ux/fullscreen-100-2026-10-01"
SCENES = {
    "page1": (1440, 900),
    "page1-long-title": (1440, 900),
    "page1-pale-cover": (1440, 900),
    "page1-no-cover": (1440, 900),
    "page1-narrow": (880, 600),
    "page1-empty": (1440, 900),
    "page1-generating": (1440, 900),
    "page1-error": (1440, 900),
    "waveform-variants": (1440, 900),
    "waveform-hover-ahead": (1440, 900),
    "waveform-hover-behind": (1440, 900),
    "play-variants": (1440, 900),
    "page2": (1440, 900),
    "page2-narrow": (880, 600),
    "queue-hover-menu": (1440, 900),
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
WAVEFORM_POINTS = 1200
SAMPLE_RATE = 22_050
BIN_FRAMES = 441  # 20 ms at 22 050 Hz, as in services/analysis/features.py
MAX_EXTERNAL_COVERS = 4


def settle(app: QGuiApplication) -> None:
    until = time.monotonic() + 0.4
    while time.monotonic() < until:
        app.processEvents()
        time.sleep(0.01)


def audio_prototype(path: Path) -> dict[str, list[float]]:
    """Return min, max and RMS in 1200 points (prototype of milestone 100.1).

    The audio is decoded with the project decoder, cut in 20 ms bins, and each
    bin keeps its minimum, maximum and sum of squares. ``rms`` is the square
    root of the mean square of the bins grouped in each point, scaled to 0..1.
    """
    from mtee.services.file_access import FileAccessCoordinator
    from mtee.services.media_decode_service import MediaDecodeService

    stream = MediaDecodeService(FileAccessCoordinator()).stream_pcm(
        path, sample_rate=SAMPLE_RATE, channels=2
    )
    lows: list[float] = []
    highs: list[float] = []
    sumsq: list[float] = []
    counts: list[int] = []
    carry = np.zeros((0, 2), dtype=np.int16)

    def add_bins(frames: np.ndarray) -> None:
        lows.append(float(frames.min()))
        highs.append(float(frames.max()))
        sumsq.append(float(np.square(frames.astype(np.float64)).sum()))
        counts.append(frames.size)

    for block in stream:
        samples = np.frombuffer(block, dtype="<i2").reshape(-1, 2)
        carry = np.concatenate((carry, samples))
        while carry.shape[0] >= BIN_FRAMES:
            add_bins(carry[:BIN_FRAMES])
            carry = carry[BIN_FRAMES:]
    if carry.shape[0]:
        add_bins(carry)
    if not lows:
        raise RuntimeError("No decodable audio frames were found")
    count = min(WAVEFORM_POINTS, len(lows))
    edges = np.linspace(0, len(lows), count + 1).astype(np.int64)[:-1]
    low = np.minimum.reduceat(np.array(lows), edges) / 32768.0
    high = np.maximum.reduceat(np.array(highs), edges) / 32768.0
    energy = np.add.reduceat(np.array(sumsq), edges)
    total = np.add.reduceat(np.array(counts, dtype=np.float64), edges)
    rms = np.sqrt(energy / total) / 32768.0
    return {"low": low.tolist(), "high": high.tolist(), "rms": rms.tolist()}


def cover_accent(path: Path) -> str | None:
    """Return the vivid colour of a cover as ``#RRGGBB``, or ``None`` (prototype).

    Steps 1 to 4 of the plan 100 algorithm: 64x64 reduction, HSV quantisation
    (36 hues, 4 saturations, 4 values), rejection of grey and extreme pixels, and
    the bin that maximises ``pixel count x mean saturation``. Darkening for the
    white text contrast (steps 5 and 6) is done by the mock-up itself.
    """
    image = QImage(str(path))
    if image.isNull():
        return None
    image = image.scaled(
        64, 64, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
    ).convertToFormat(QImage.Format.Format_RGB888)
    stride = image.bytesPerLine()
    raw = np.frombuffer(image.constBits(), dtype=np.uint8, count=stride * 64)
    pixels = raw.reshape(64, stride)[:, : 64 * 3].reshape(-1, 3).astype(np.float64) / 255.0
    high = pixels.max(axis=1)
    delta = high - pixels.min(axis=1)
    saturation = np.divide(delta, high, out=np.zeros_like(high), where=high > 0)
    keep = (saturation >= 0.25) & (high >= 0.20) & (high <= 0.95)
    if keep.sum() < 0.05 * pixels.shape[0]:
        return None
    colours = pixels[keep]
    delta, high, saturation = delta[keep], high[keep], saturation[keep]
    red, green, blue = colours[:, 0], colours[:, 1], colours[:, 2]
    safe = np.where(delta == 0, 1.0, delta)
    hue = np.where(
        high == red,
        ((green - blue) / safe) % 6,
        np.where(high == green, (blue - red) / safe + 2, (red - green) / safe + 4),
    )
    hue_bin = np.floor(hue / 6 * 36).astype(int) % 36
    sat_bin = np.minimum(np.floor(saturation * 4), 3).astype(int)
    val_bin = np.minimum(np.floor(high * 4), 3).astype(int)
    key = hue_bin * 16 + sat_bin * 4 + val_bin
    best, best_score = -1, 0.0
    for candidate in np.unique(key):
        members = key == candidate
        score = members.sum() * saturation[members].mean()
        if score > best_score:
            best, best_score = int(candidate), float(score)
    mean = colours[key == best].mean(axis=0)
    return "#" + "".join(f"{round(value * 255):02X}" for value in mean)


def external_covers(folder: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    for path in files[:MAX_EXTERNAL_COVERS]:
        accent = cover_accent(path)
        print(f"{path.name}: {accent or 'no usable colour (grey fallback)'}")
        entries.append(
            {
                "title": path.stem,
                "artist": "Local cover",
                "file": QUrl.fromLocalFile(str(path)).toString(),
                "coverColor": accent or "",
            }
        )
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--scene", choices=SCENES, default="page1")
    parser.add_argument("--audio", type=Path, help="local audio file used for the waveform")
    parser.add_argument("--covers", type=Path, help="local folder of images for the accent")
    args = parser.parse_args()
    if args.capture and (args.audio or args.covers):
        parser.error("--capture only uses generated data; drop --audio and --covers")
    if args.capture and not args.native:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    app = QGuiApplication(sys.argv[:1])
    families = register_fonts()
    if resolve_ui_family(families) == "sans-serif" and os.name == "nt":
        for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
            path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont(resolve_ui_family(families)))
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(ROOT / "src/mtee/qml"))
    engine.addImageProvider("icon", IconProvider())
    warnings: list[str] = []

    def record_warnings(items: list) -> None:
        for item in items:
            message = item.toString()
            warnings.append(message)
            print(message, file=sys.stderr)

    engine.warnings.connect(record_warnings)
    engine.load(QUrl.fromLocalFile(str(ROOT / "docs/ux/mockups/Fullscreen100Review.qml")))
    if not engine.rootObjects():
        return 1
    window = engine.rootObjects()[0]
    if not isinstance(window, QQuickWindow):
        raise RuntimeError("Fullscreen review did not create a Qt Quick window")
    if args.audio:
        prototype = audio_prototype(args.audio)
        window.setProperty("audioTitle", args.audio.stem)
        window.setProperty("audioRms", prototype["rms"])
    if args.covers:
        window.setProperty("extraTracks", external_covers(args.covers))
    if args.capture:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        for scene, dimensions in SCENES.items():
            window.setProperty("scene", scene)
            window.resize(*dimensions)
            settle(app)
            path = OUTPUT / f"{scene}-{dimensions[0]}x{dimensions[1]}.png"
            if not window.grabWindow().save(str(path)):
                raise RuntimeError(f"Capture failed: {scene}")
            print(path.relative_to(ROOT))
        window.close()
        return 2 if warnings else 0
    window.setProperty("scene", args.scene)
    window.resize(*SCENES[args.scene])
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
