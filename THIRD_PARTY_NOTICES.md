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
| packaging 26.3 | Version comparisons of plugin packages and the Marketplace | Apache-2.0 OR BSD-2-Clause (wheel metadata `License-Expression`); MTEE uses it under BSD-2-Clause | Locked version; BSD text in `LICENSES/packaging-BSD-2-Clause.txt`, taken from the 26.3 wheel; not checked in a built distribution |
| pywinrt: winrt-runtime, winrt-Windows.Foundation, winrt-Windows.Media, winrt-Windows.Media.Playback, winrt-Windows.Storage, winrt-Windows.Storage.Streams, 3.2.1 | Python projection of the Windows Runtime, system media controls (Windows only) | MIT (wheel metadata: `License-Expression: MIT`) | Locked version; MIT text in `LICENSES/pywinrt-MIT.txt`, taken from the pywinrt repository rather than from the wheel; not checked in a built distribution |
| Visual C++ runtime `msvcp140.dll` | Dependency of the pywinrt extensions; the `winrt-runtime` wheel ships a copy in `winrt/` | Microsoft Visual C++ redistribution terms | **Unverified.** See the findings below |
| libmpv (`vendor/mpv/libmpv-2.dll`) | Playback engine | LGPL-2.1-or-later per the manifest | **Partly verified.** See the findings below |
| FFmpeg runtime (`vendor/ffmpeg/bin`, `resources/native/ffmpeg/manifest.json`) | Conversion and analysis of audio | LGPL-3.0-or-later (build configuration and encoder list checked) | **Verified** on 2026-10-26. See the findings below |
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

**FFmpeg runtime, `vendor/ffmpeg/bin`** (checked on 2026-10-26).

- All nine binaries and the licence text match their SHA-256 in `resources/native/ffmpeg/manifest.json`.
- `ffmpeg.exe -buildconf` shows `--enable-version3` and `--enable-shared`, and no `--enable-gpl` or
  `--enable-nonfree`. The build is therefore LGPL-3.0-or-later, as the manifest states.
- `ffmpeg.exe -encoders` lists no `libx264`, `libx265` or `libxvid`. The strings found in the DLL
  in an earlier byte search do not correspond to compiled-in encoders. The remaining
  third-party encoders (`libkvazaar`, `libopenh264`, `libvpx`, `libopus`, `libmp3lame`) are
  permissively licensed or LGPL.

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

## MTEE Remote server (server/)

The server in `server/` is licensed AGPL-3.0-or-later (`server/LICENSE`). It is distributed as
source only for now, so the licence texts of the packages below are not copied into `LICENSES/`
yet; this must be done before any binary or image is published. Versions are those locked in
`server/uv.lock` (development tools excluded); licences are the ones announced in the package
metadata installed in `server/.venv` on 2026-10-31. Nothing was checked against the licence
texts themselves.

| Package | Locked version | Announced licence | Role |
|---|---|---|---|
| mtee (this repository, `src/mtee`) | 0.3.0 | GPL-3.0-or-later | Qt-free modules `mtee.domain.metadata` and `mtee.services.metadata_reader`; installed without PySide6 |
| starlette | 1.10.0 | BSD-3-Clause | HTTP framework |
| uvicorn | 0.54.0 | BSD-3-Clause | HTTP server |
| anyio | 4.15.1 | MIT | Async runtime layer of Starlette |
| idna | 3.20 | BSD-3-Clause | Dependency of anyio |
| click | 8.5.0 | BSD-3-Clause | Dependency of uvicorn |
| h11 | 0.16.0 | MIT | Dependency of uvicorn |
| typing-extensions | 4.16.0 | PSF-2.0 | Dependency of anyio and Starlette |
| argon2-cffi | 25.1.0 | MIT | Argon2id password hashes |
| argon2-cffi-bindings | 26.1.0 | MIT | Dependency of argon2-cffi |
| cffi | 2.1.1 | MIT-0 | Dependency of argon2-cffi-bindings |
| pycparser | 3.12 | BSD-3-Clause | Dependency of cffi |
| mutagen | 1.48.1 | GPL-2.0-or-later | Audio tag reading, through `mtee` |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 (wheel metadata) | Dependency of `mtee` |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | Dependency of `mtee` |
| winrt-runtime and five winrt-Windows.* packages | 3.2.1 | MIT | Dependencies of `mtee`; installed on Windows only, absent from a Linux image |

The admin program in `server/admin/` (`mtee-remote-admin`, AGPL-3.0-or-later) depends on Textual
(`textual>=8.2,<9`; 8.2.8 when written, MIT) and what it needs: rich, markdown-it-py,
mdit-py-plugins, linkify-it-py, mdurl and platformdirs (MIT), pygments (BSD-2-Clause) and
typing-extensions (PSF-2.0), as announced in their package metadata on 2026-11-04. `uv tool install`
installs them from PyPI on the server host, in the range of `server/admin/pyproject.toml` (the
lock file pins the development environment only); they are not distributed with this repository.

`uv.lock` also lists `pyside6-essentials` and `shiboken6` under the marker
`sys_platform == 'never'`. A uv override in `server/pyproject.toml` removes PySide6 from the
server environment, so neither package is installed or distributed with the server. The test
`server/tests/test_no_qt.py` fails if a server module imports PySide6.
