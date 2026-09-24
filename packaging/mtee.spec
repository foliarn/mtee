# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification of the Windows distribution.

The build is a directory: the QML resources, the migrations and the Qt plugins
stay visible, which makes a loading failure diagnosable. Set MTEE_BUILD_CONSOLE
to 1 to obtain a build that keeps its console output for such a diagnosis.
"""

import os
from pathlib import Path

project_root = Path(SPECPATH).resolve().parent
package_dir = project_root / "src" / "mtee"
mpv_library = project_root / "vendor" / "mpv" / "libmpv-2.dll"
if not mpv_library.is_file():
    raise SystemExit(
        f"The verified libmpv runtime is missing: {mpv_library}. "
        "Run scripts/fetch_mpv.ps1 before building the Windows distribution."
    )

datas = [
    (str(package_dir / "qml"), "mtee/qml"),
    (str(package_dir / "resources"), "mtee/resources"),
    (str(package_dir / "persistence" / "migrations"), "mtee/persistence/migrations"),
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
    binaries=[(str(mpv_library), "mtee/native/mpv")],
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
    [],
    exclude_binaries=True,
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

collect = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MTEE",
)
