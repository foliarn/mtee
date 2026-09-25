# Validation — Étape 07 (runtime, conversion et fichiers dérivés)

État au 2026-09-25 : runtime FFmpeg/ffprobe et fixtures créés, B de
`06b-correctifs-recette.md` exécuté sur copies synthétiques, puis service de
conversion implémenté, exercé et empaqueté. Ce rapport distingue les contrôles
automatisés observés des gestes de recette encore non réalisés.

## Environnement et provenance

| Élément | Résultat observé |
| --- | --- |
| OS de développement/recette | Windows 11 x64, build 10.0.26200 |
| Python / PyInstaller | Python 3.12.14 / PyInstaller 6.22.2 |
| Fournisseur FFmpeg | BtbN/FFmpeg-Builds, release `autobuild-2026-09-24-14-14`, variante `win64-lgpl-shared` |
| Version rapportée | `n9.0.2-3-ga5923073bf-20260924` |
| Archive | `ffmpeg-n9.0.2-3-ga5923073bf-win64-lgpl-shared-9.0.zip`, 76 974 101 octets |
| SHA-256 archive | `735bae484ba2c3342bfb34df477b9c6b0f43f9819f4d2fde011be293ee1b6517` |
| SHA-256 du texte LGPL livré | `da7eabb7bafdf7d3ae5e9f223aa5bdc1eece45ac569dc21b3b037520b4464768` |
| Installation | `pwsh -NoProfile -File scripts/fetch_ffmpeg.ps1` — téléchargée et hashée; runtime réinstallable sans remplacement |
| Version FFmpeg | `ffmpeg.exe -version` → `ffmpeg version n9.0.2-3-ga5923073bf-20260924` |
| Version ffprobe | `ffprobe.exe -version` → même version |
| Licence fournie par l'archive | LGPL-3.0 (`vendor/ffmpeg/LICENSE.txt`, incluse dans les ressources du paquet) |

La compilation inspectée annonce `--enable-version3`, active AAC, ALAC, FLAC,
`libmp3lame`, `libvorbis` et `libopus`, et désactive `libx264`/`libx265`.
L'appellation `lgpl-shared` et la configuration observée ne remplacent pas un
audit de dépendances transitives ou de redistribution; aucun avis juridique
n'est revendiqué. Les exécutables FFmpeg lancés en développement passent par
`FfmpegRuntime`, sous chemin explicite, `shell=False`, délai borné et `PATH`
restreint au dossier du runtime.

## Fixtures locales

Commande exécutée :

```powershell
uv run python scripts/create_audio_fixtures.py --output .local/fixtures/07-metadata/audio
```

Le générateur refuse un dossier non vide. Les neuf copies synthétiques durent
environ trois secondes; une PNG 16×16 générée par Python standard accompagne
les tests de conservation de pochettes. Le manifeste local
`.local/fixtures/07-metadata/audio/manifest.json` enregistre la provenance, les
codecs, les durées, la taille et SHA-256 des fichiers.
ffprobe a observé MP3, FLAC, PCM WAV, PCM AIFF, Vorbis, Opus, AAC/ADTS,
M4A/AAC (codec `aac`) et M4A/ALAC (codec `alac`). Elles contiennent des tags
de test; elles ne contiennent aucune œuvre tierce et ne sont pas suivies par Git.

| Format synthétique | Conteneur observé | Codec observé | État à ce jalon |
| --- | --- | --- | --- |
| MP3 | MP3 | `mp3` | Généré et identifié; écriture tags à tester dans B |
| FLAC | FLAC | `flac` | Généré et identifié; écriture tags à tester dans B |
| WAV | WAV | `pcm_s16le` | Généré et identifié; compatibilité historique de l'adaptateur maintenue |
| AIFF | AIFF | `pcm_s16be` | Généré et identifié; écriture tags à tester dans B |
| Ogg/Vorbis | Ogg | `vorbis` | Généré et identifié; écriture tags à tester dans B |
| Opus | Ogg | `opus` | Généré et identifié; écriture tags à tester dans B |
| AAC brut | ADTS | `aac` | Généré et identifié; reste non éditable si aller-retour non sûr |
| M4A/AAC | MP4/M4A | `aac` | Généré et identifié; écriture tags à tester dans B |
| M4A/ALAC | MP4/M4A | `alac` | Généré et identifié; écriture tags à tester dans B |

## Contrôles du paquet Windows

`pwsh -NoProfile -File scripts/build_windows.ps1` a réussi après vérification
des neuf SHA-256 runtime et a vérifié les copies livrées ainsi que leurs deux
bannières de version. PyInstaller plaçait des copies de DLL à la racine lors
d'un premier essai; le script final copie ces fichiers uniquement après
PyInstaller pour éviter le doublonnage et garde un seul ensemble dans
`dist/MTEE/_internal/mtee/native/ffmpeg/bin`. Le répertoire final fait
412 961 278 octets (1 970 fichiers).

Le répertoire `dist/MTEE` a été copié vers un sous-dossier unique de `%TEMP%`
hors du checkout, puis lancé depuis cette copie avec un `--data-dir` isolé;
`MTEE.exe --smoke-test` a terminé avec le code 0. En utilisant ffmpeg/ffprobe
copiés et en gardant ce dossier externe comme répertoire courant, le générateur
a créé puis sondé les neuf fixtures à nouveau. Après ajout de la PNG et du hash
au manifeste, la suite d'intégration locale a regénéré les neuf audios et
validé les codecs et la présence de l'image de test. Le total du paquet copié
avec les fixtures et les données temporaires est 414 429 215 octets. Il n'y a pas eu
de test sur machine Windows propre, hors du compte développeur, ni de recette
UI/conversion.

## Vérifications de code

- `uv run ruff check .` — réussi.
- `uv run ruff format --check .` — réussi, 163 fichiers déjà formatés.
- `uv run pyright` — 0 erreur, 0 avertissement.
- `uv run pytest tests/unit/test_ffmpeg_runtime.py tests/unit/test_audio_fixture_generator.py tests/integration/test_audio_fixtures.py -q` — 7 tests réussis.
- Génération réelle : 9 fichiers créés par le runtime source puis recréés avec le runtime du paquet; codecs distincts AAC/ALAC identifiés.
- Recette de conversion, transfert tags, contrôles d'annulation/progression, lot réel et compatibilité matériel — non réalisés à cette tranche.

## Raccord B — métadonnées sur copies synthétiques

Après le contrôle du runtime, la suite de 06b a étendu l'édition contrôlée aux
neuf champs sur WAV PCM, MP3, AIFF, FLAC, Ogg/Vorbis, Ogg/Opus, M4A/AAC et
M4A/ALAC. `tests/integration/test_metadata_formats.py` génère ces fichiers
dans `tmp_path`, ajoute une pochette synthétique et un marqueur inconnu, édite
les champs par `MetadataEditService`, puis annule par Undo. Le hash SHA-256 du
PCM décodé avant/après chaque édition et Undo est identique. Les tests gardent
les tags/pochettes hors patch, les totaux `/12` et vérifient les valeurs relues.

| Politique constatée | Résultat automatisé |
| --- | --- |
| AAC/ADTS brut | Écriture refusée avec motif explicite; aucun round-trip revendiqué |
| ID3v2.3 date | Écriture refusée; essai direct Mutagen a révélé TYER/TDRC ambigu, alors que les autres champs v2.3 passent |
| M4A BPM | Atome `tmpo`, valeur entière de 1 à 1000 |
| M4A Key | Atome libre UTF-8 `initialkey`, lu par le reader natif en complément de EasyMP4 |
| Champs non ciblés / artwork | Tags inconnus et pochettes testés; FLAC picture, Ogg COVERART, MP4 covr et ID3 APIC |

21 tests ciblés de métadonnées réussis; `uv run ruff check .`,
`uv run ruff format --check .` (168 fichiers) et `uv run pyright` (0 erreur,
0 avertissement) réussis. Le rebuild B fait 412 978 343 octets (1 970 fichiers,
EXE 2,29 Mo), et contient exactement un `ffmpeg.exe` et un `ffprobe.exe`.
Copié sous `%TEMP%`, `MTEE.exe --smoke-test` termine code 0; le générateur
utilisant les DLL du dossier copié a recréé les 9 fixtures avec le codec attendu.
Il s'agit de preuves de code et de service sur copies synthétiques : aucune
recette UI, édition manuelle de chaque version, installation Windows propre,
ni validation d'une collection utilisateur n'a été réalisée.

## Service Convert, tests et paquet final de cette tranche

Le service et la vue Convert ont été implémentés après B. Le runtime énumère
huit profils disponibles (MP3, FLAC, WAV, AIFF, Vorbis, Opus, M4A/AAC et
M4A/ALAC). L'aperçu bloque une destination existante. Une conversion vérifie
la révision et le hash de la source, les paramètres et le flux audio de sortie,
puis publie sans remplacer un fichier déjà présent. L'annulation pendant le
processus enlève le temporaire. Le journal enregistre tentatives et filiation.
Le rapport de transfert distingue valeurs vérifiées, représentations modifiées
et champs/pochettes non transférés. La sortie n'est pas automatiquement
ajoutée à la bibliothèque; le transfert de pochettes n'est pas implémenté.

Les huit conversions ont été rejouées depuis le runtime extrait d'une copie
externe du paquet Windows final, vers des sous-dossiers distincts, avec une
source synthétique copiée sous un chemin accentué contenant espaces et
apostrophe. ffprobe a confirmé chacun des codecs attendus. La source de copie
a conservé le SHA-256
`f95cf15299c1238233ebbcf2349fea54aa6f1195d33de52f052096de4e333e15`.
Les sorties ont été écrites dans `%TEMP%`, jamais sur la fixture suivie.

Le rebuild courant (`scripts/build_windows.ps1`) a réussi sous Windows 11
10.0.26200, Python 3.12.14 et PyInstaller 6.22.2. Une copie du répertoire
`dist/MTEE` placée sous `%TEMP%` a été lancée avec `--smoke-test` et un
`--data-dir` isolé : code de sortie 0, 1 971 fichiers, 413 026 280 octets,
un seul `ffmpeg.exe` et un seul `ffprobe.exe`. Les conversions ci-dessus ont
utilisé ces exécutables copiés. Ce n'est pas un essai sur une installation
Windows propre.

Contrôles finaux de 07 : `uv run ruff check .` réussi; `uv run ruff format
--check .` réussi (178 fichiers); `uv run pyright` sans erreurs,
avertissements ni informations; suite ciblée de conversion/queue/décodage,
migrations et chargement QML réussie (25 tests); `uv run pytest -q` réussi,
deux tests sautés. Plusieurs exécutions pytest ont imprimé l'exception native
Windows libmpv `0xe24c4a02`, avec des traces dans `_event_loop`/fermeture. Les
tests pytest finissent néanmoins avec succès; la cause et l'éventuel lien avec
R05 ne sont pas démontrés. Il s'agit d'une hypothèse de crash, pas d'un
correctif prouvé.

La recette manuelle de l'onglet Convert, du glisser-déposer natif, de la
progression visible et des parcours de reprise n'a pas été réalisée. Aucun
essai sur la collection musicale de l'utilisateur ni sur une machine Windows
propre n'est revendiqué. L'audit des dépendances transitives de FFmpeg demeure
ouvert.

Le runtime et les fixtures rendent B exécutable; ils ne clôturent ni le jalon
07, ni les retours A0/A3 dont les parcours interactifs restent partiels.
