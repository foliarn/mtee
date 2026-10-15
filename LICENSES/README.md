# Licence texts of distributed components

This directory holds the licence texts of the third-party components that MTEE actually ships.
`THIRD_PARTY_NOTICES.md`, at the root, lists them with their verification state.

## Interface font

`src/mtee/resources/fonts/` is meant for the Geist Sans files. The font files are not versioned
yet. Until they are added, MTEE uses the first fallback font available on the system and the
window stays usable.

To add them:

1. Fetch the officially distributed version and its licence text.
2. Place the `.ttf` or `.otf` files in `src/mtee/resources/fonts/`.
3. Copy the licence text here as `Geist-OFL.txt`, or under the exact name of the supplied file.
4. Update `THIRD_PARTY_NOTICES.md` with the version, source and observed licence.

`src/mtee/fonts.py` registers every font file found in that directory at start-up. No other code
change is needed.

## MTEE licence

MTEE is distributed under the GNU General Public License version 3 or later
(`GPL-3.0-or-later`). The official text is `LICENSE` at the root of the repository (identical to
<https://www.gnu.org/licenses/gpl-3.0.txt>, SHA-256
`3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986`). This directory contains only
the licences of third-party components.
