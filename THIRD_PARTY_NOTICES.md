# Third-party components

This file lists the third-party components that MTEE ships or fetches, with the licence
announced by their authors and the state of the verification. A component that is not part of
a distribution is not listed for that distribution. "Unverified" means that the statement has not
been checked against the binary or the text, and must be checked before a binary release.

| Component | Role | Announced licence | Verification state |
|---|---|---|---|
| Python 3.12 | Interpreter embedded by PyInstaller | PSF License | Licence known; text not yet copied into `LICENSES/` |
| PySide6 and Qt 6 | QML interface, plugins and Qt DLLs | LGPL v3 for Qt and PySide6 | To confirm against the version locked in `uv.lock` |
| Mutagen | Audio metadata reading and writing | GPL v2 or later | To confirm against the locked version; compatible with GPL-3.0-or-later |
| NumPy | Tempo, key and waveform computation | BSD-3-Clause; the wheel metadata of 2.5.3 declares BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Version 2.5.3 locked; main licence text embedded by `packaging/mtee.spec` (not built in this review) |
| pywinrt: winrt-runtime, winrt-Windows.Foundation, winrt-Windows.Media, winrt-Windows.Media.Playback, winrt-Windows.Storage, winrt-Windows.Storage.Streams, 3.2.1 | Python projection of the Windows Runtime, system media controls (Windows only) | MIT (wheel metadata: `License-Expression: MIT`) | Locked version; MIT text in `LICENSES/pywinrt-MIT.txt`, taken from the pywinrt repository rather than from the wheel; not checked in a built distribution |
| Visual C++ runtime `msvcp140.dll` | Dependency of the pywinrt extensions; the `winrt-runtime` wheel ships a copy in `winrt/` | Microsoft Visual C++ redistribution terms | **Unverified.** See the findings below |
| libmpv (`vendor/mpv/libmpv-2.dll`) | Playback engine | LGPL-2.1-or-later per the manifest | **Partly verified.** See the findings below |
| FFmpeg runtime (`vendor/ffmpeg/bin`, `resources/native/ffmpeg/manifest.json`) | Conversion and analysis of audio | LGPL-3.0-or-later per the manifest (archive name `lgpl-shared`) | **Open question.** See the findings below |
| PyInstaller | Build tool, not redistributed | GPL v2 with an exception for the executables it produces | To confirm against the locked version |
| Plus Jakarta Sans | Display font (Bold, ExtraBold) | SIL Open Font License 1.1 | Licence text in `LICENSES/PlusJakartaSans-OFL.txt` |
| Geist Sans | Interface font | Expected under the SIL Open Font License | Unverified: font files are not versioned in the repository |

## Findings of the release review

Each finding comes from a read of the file in `vendor/`, not from its manifest alone. The
commands used were byte searches of the binaries; no build was run.

**libmpv, `vendor/mpv/libmpv-2.dll`** (SHA-256 `85071ee7c8bfc9f3690aeb140f15bbb697cdf81bc96e9c905dc8a54cfff8c10d`, 100 392 960 bytes).

- The version string is `mpv v0.41.0-1055-g6fd80b200`, which matches the commit pinned in
  `resources/native/mpv/manifest.json`.
- The embedded build configuration contains `-Dgpl=false` and `-Dlibmpv=true`. This is the
  LGPL build of the upstream mpv, as the manifest states.
- No GPL-only codec name (`libx264`, `libx265`, `libxvid`) was found in this file.
- Not verified: the FFmpeg configuration that the manifest says is statically linked into this
  DLL. No FFmpeg configuration string was found in it, so the LGPL-3.0-or-later status of that
  part stays unverified.

**FFmpeg runtime, `vendor/ffmpeg/bin/avcodec-63.dll`** (and the other DLLs of the same build).

- The configuration string contains `--enable-version3` and `--enable-shared`, and does not
  contain `--enable-gpl`. That combination is consistent with an LGPL-3.0-or-later build.
- However, the names `libx264`, `libx265` and `libxvid` also occur in `avcodec-63.dll`. Whether
  these encoders are compiled in was not established. If they are, the build is governed by
  the GPL, and the notice above, the manifest and the packaged licence text
  (`mtee/resources/LICENSE.txt`, LGPL-3.0) would all be wrong for that build.
- Action before any binary release: check the encoder list (for example with `ffmpeg -encoders`)
  of the pinned `ffmpeg.exe`. If a GPL encoder is present, ship the GPL licence text and correct
  the manifest.

**msvcp140.dll.**

- The file is `winrt/msvcp140.dll` in the `winrt-runtime` 3.2.1 wheel (567 352 bytes). It is
  signed by Microsoft Corporation. PySide6 and NumPy ship their own copies, under other names.
- Its redistribution terms are those of the Microsoft Visual C++ redistributable, but the
  licence text is not stored in this repository and was not checked. This stays **unverified**.
  Keep it out of a public binary release until the Microsoft terms have been read and recorded
  in `LICENSES/`.

MTEE is distributed under the GNU General Public License version 3 or later (`GPL-3.0-or-later`).
The text is in `LICENSE` at the root and is embedded in the distribution. This choice is
compatible with Mutagen (GPL v2 or later) and with the LGPL components (Qt, PySide6, libmpv,
FFmpeg).

The licence texts of the components that are actually shipped are collected in `LICENSES/`. This
file must be updated with each change of a distributed dependency, and it records the version
observed, not an assumed one.
