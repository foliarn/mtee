# Validation — Étape 09 (analyse audio sans apprentissage automatique)

État au 2026-09-25. Le pipeline a été exercé avec une fixture synthétique et
des copies placées dans `%TEMP%`. Aucun fichier de la collection personnelle
n'a été ouvert ou modifié. Les résultats ci-dessous prouvent le comportement
sur ces fixtures; ils ne mesurent pas la précision sur des enregistrements
musicaux réels.

## Résultat de référence mesuré

Fixture WAV générée par `tests/helpers/analysis_audio.py` : 14 s, PCM signé
16 bits, mono, 22 050 Hz; silence d'une seconde au début et à la fin, accord
synthétique de do majeur et impulsions au tempo de référence 120 BPM.
SHA-256 avant et après analyse :
`577d20019c97571767fd1b8b080458da1123bdf516ff84c072248b8e1ea705b1`.

| Analyseur | Résultat observé | Provenance/version | Portée de la preuve |
| --- | --- | --- | --- |
| Technique | WAV, `pcm_s16le`, 14 000 000 µs, 22 050 Hz, mono, 16 bits | `ffprobe-v1`; runtime FFmpeg `n9.0.2-3-ga5923073bf-20260924` | Inspection de la fixture, aucune validation d'autres codecs. |
| Silences | 2 intervalles, 2 000 000 µs au total | `ffmpeg-silencedetect-v1`, −60 dB, minimum 0,5 s | Les deux silences synthétiques connus sont retrouvés. |
| Loudness | −18,0 LUFS intégrés; LRA 0,8 LU; sample peak −4 dBFS; true peak −4 dBTP | `ffmpeg-ebur128-v1` | Contrôle des unités et du signal fabriqué, pas une référence de loudness publiée. |
| Tempo | 117,4538 BPM; alternatives 58,7269 et 234,9077 BPM; MAD inter-segment 0 | `librosa-0.11.0-beattrack-v1` | Écart de −2,5462 BPM par rapport aux impulsions à 120 BPM, sur un seul segment. |
| Tonalité | do majeur; un segment tonal | `librosa-0.11.0-chroma-krumhansl-v1` | Reconnaissance de l'accord synthétique; aucune mesure de robustesse en musique réelle. |

Les sorties des tests de silence, loudness, tempo et tonalité sont conformes
aux valeurs synthétiques attendues. Les tests couvrent les états sans résultat,
les alternatives moitié/double, les overrides manuels et leur conservation
après réanalyse, ainsi que l'obsolescence après changement de révision. Les
tests d'intégration vérifient aussi la migration SQLite 10 sur bases
temporaires, l'annulation, les résultats indépendants et le hash source.

## Dépendances et paquet Windows

Versions mesurées dans l'environnement verrouillé : Python 3.12.14,
librosa 0.11.0, NumPy 2.5.3, SciPy 1.18.1, PyInstaller 6.22.2. Le manifeste
FFmpeg épingle le build Windows ci-dessus et sa licence LGPL-3.0-or-later est
copiée et vérifiée par le script de build.

`pwsh -NoProfile -File scripts/build_windows.ps1` a réussi deux fois sous
Windows 11 10.0.26200. Le dossier final contient 2 550 fichiers pour
667 609 388 octets; `MTEE.exe` fait 20 381 481 octets. Le build note l'absence
de `tbb12.dll` utilisé par le backend TBB facultatif de Numba. PyInstaller
produit aussi des avertissements pour certaines imports optionnelles de
SciPy/pycparser. Le contrôle d'analyse dans une copie temporaire du paquet
reste réussi, donc ces avertissements ne correspondent pas à une méthode
manquante dans ce scénario; ils ne sont pas déclarés corrigés.

Sur une copie externe de `dist/MTEE`, la commande `--smoke-test` renvoie le
code 0. La commande `--analysis-smoke-test <copie-de-fixture> --data-dir
<dossier-temporaire>` renvoie également 0. La base créée dans le dossier
isolé contient `key`, `loudness`, `silence`, `technical` et `tempo`, tous en
état `available`; le run est `succeeded`. Le SHA-256 de la fixture copiée est
identique avant et après. La sortie JSON est présente quand le processus a une
console; dans le binaire graphique, le code de sortie et les lignes SQLite
sont utilisés pour vérifier le résultat.

## Contrôles exécutés et limites

- `uv run ruff check .`, `uv run ruff format --check .` et `uv run pyright` :
  réussis, sans erreur.
- Groupe dédié analyse, migration, QML et tests CLI : 22 tests réussis.
- `uv run pytest tests/unit tests/integration --ignore=tests/integration/test_mpv_playback.py --tb=short -q` : terminé avec code 0; deux tests sautés.
- La suite complète a été tentée. Elle a émis l'exception SEH
  `0xe24c4a02` dans le thread `_event_loop` de libmpv puis s'est terminée sur
  Windows par `-1073741819` (access violation), avec une trace dans
  `test_native_libmpv_decodes_seeks_and_pauses_wav`. Cause racine non
  déterminée : c'est une hypothèse de crash native, pas une preuve que les
  analyseurs causent le crash et pas un correctif livré.
- Le panneau Analysis et son chargement QML sont vérifiés par un test UI
  automatisé. Le parcours visible souris/clavier, l'écoute des estimations,
  les contrôles en vraie lecture et l'essai sur une installation propre
  n'ont pas été réalisés. La recette manuelle demandée par les plans reste
  ouverte.
- Aucun corpus musical réel n'a été comparé à des annotations indépendantes;
  la précision BPM/tonalité, les erreurs selon les genres, les abstentions et
  les ressources au cours de longues analyses restent à mesurer.

## Reproduction locale

Les tests créent leurs propres fichiers temporaires et n'écrivent pas dans
une collection utilisateur :

    uv run pytest tests/unit/test_silence_analysis.py tests/unit/test_loudness_analysis.py tests/unit/test_tempo_key_analysis.py tests/unit/test_analysis_overrides.py tests/integration/test_analysis_pipeline.py tests/integration/test_analysis_package_smoke.py tests/ui/test_analysis_panel.py
    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    pwsh -NoProfile -File scripts/build_windows.ps1

Le parcours paquet a utilisé une copie de `dist/MTEE` sous `%TEMP%`, une
fixture copiée et des répertoires `--data-dir` isolés. Aucun résultat
concernant une bibliothèque réelle n'est inféré de cette validation.
