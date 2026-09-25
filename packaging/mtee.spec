# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification of the single-file Windows distribution.

The QML resources and native runtimes are embedded in MTEE.exe and extracted
into PyInstaller's temporary bundle directory while the application runs. Set
MTEE_BUILD_CONSOLE to 1 for a diagnostic build that keeps its console.
"""

import hashlib
import json
import os
from pathlib import Path

project_root = Path(SPECPATH).resolve().parent
package_dir = project_root / "src" / "mtee"
mpv_library = project_root / "vendor" / "mpv" / "libmpv-2.dll"
ffmpeg_manifest_path = project_root / "resources" / "native" / "ffmpeg" / "manifest.json"
if not ffmpeg_manifest_path.is_file():
    raise SystemExit(f"The FFmpeg manifest is missing: {ffmpeg_manifest_path}")
ffmpeg_manifest = json.loads(ffmpeg_manifest_path.read_text(encoding="utf-8"))
ffmpeg_bin = project_root / "vendor" / "ffmpeg" / "bin"
for entry in ffmpeg_manifest["binaries"]:
    source = ffmpeg_bin / entry["name"]
    if not source.is_file():
        raise SystemExit(
            f"The verified FFmpeg runtime is missing: {source}. "
            "Run scripts/fetch_ffmpeg.ps1 before building the Windows distribution."
        )
    if source.stat().st_size != entry["size_bytes"]:
        raise SystemExit(f"The FFmpeg runtime size does not match its manifest: {source}")
    if hashlib.sha256(source.read_bytes()).hexdigest() != entry["sha256"]:
        raise SystemExit(f"The FFmpeg runtime SHA-256 does not match its manifest: {source}")
ffmpeg_license = project_root / "vendor" / "ffmpeg" / "LICENSE.txt"
if not ffmpeg_license.is_file():
    raise SystemExit(f"The FFmpeg license text is missing: {ffmpeg_license}")
if ffmpeg_license.stat().st_size != ffmpeg_manifest["license"]["size_bytes"]:
    raise SystemExit(f"The FFmpeg license size does not match its manifest: {ffmpeg_license}")
if hashlib.sha256(ffmpeg_license.read_bytes()).hexdigest() != ffmpeg_manifest["license"]["sha256"]:
    raise SystemExit(f"The FFmpeg license SHA-256 does not match its manifest: {ffmpeg_license}")
if not mpv_library.is_file():
    raise SystemExit(
        f"The verified libmpv runtime is missing: {mpv_library}. "
        "Run scripts/fetch_mpv.ps1 before building the Windows distribution."
    )

datas = [
    (str(package_dir / "qml"), "mtee/qml"),
    (str(package_dir / "resources"), "mtee/resources"),
    (str(package_dir / "persistence" / "migrations"), "mtee/persistence/migrations"),
    (str(ffmpeg_license), "mtee/resources"),
]
ffmpeg_binaries = [
    (str(ffmpeg_bin / entry["name"]), "mtee/native/ffmpeg/bin")
    for entry in ffmpeg_manifest["binaries"]
]

# Modules that MTEE does not use at this step. QtMultimedia is deliberately
# absent: the playback of the next step uses libmpv, not the Qt player.
excludes = [
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebChannel",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtBluetooth",
    "PySide6.QtSerialPort",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "tkinter",
    "pytest",
]

keep_console = os.environ.get("MTEE_BUILD_CONSOLE", "0") == "1"

analysis = Analysis(
    [str(package_dir / "__main__.py")],
    pathex=[str(project_root / "src")],
    binaries=[(str(mpv_library), "mtee/native/mpv"), *ffmpeg_binaries],
    datas=datas,
    hiddenimports=["mtee.app"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    exclude_binaries=False,
    name="MTEE",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=keep_console,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
