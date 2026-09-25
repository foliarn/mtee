# Validation — Étape 08 (waveform et lecteur plein écran)

État au 2026-09-25. Cette validation couvre des tableaux synthétiques, un
audio de trois secondes copié sous un chemin accentué, le cache, le chargement
QML et un paquet Windows lancé depuis `%TEMP%`. Les gestes visibles et la
précision de boucle en écoute réelle sont séparés des preuves automatisées.

## Implémentation exercée

- Le décodage réutilise `MediaDecodeService` et les blocs FFmpeg bornés de 64
  Kio; la génération réduit les trames en min/max par canal et construit une
  pyramide sans conserver le PCM.
- Le cache binaire porte source/révision, configuration et version d'algorithme;
  il est écrit par fichier temporaire puis `os.replace`, vérifié au chargement,
  invalidé quand la révision change et purgé par quota sous `--data-dir/cache`.
- `WaveformModel` suit le morceau en cours, annule le job précédent, rejette
  les résultats périmés, limite la fenêtre QML à 1 200 points et expose état,
  progression, seek, zoom, panoramique et repères.
- Le Canvas de `WaveformView.qml` dessine enveloppe, playhead et A/B. Clic seek,
  molette zoom, +/- zoom clavier, flèches panoramique, Tab/Entrée sur A/B et
  clic droit pour vider la boucle. `PlayerService` reste l'unique lecteur;
  `MpvBackend` relaie les propriétés `ab-loop-a` et `ab-loop-b`.

## Résultats automatisés

| Contrôle | Résultat observé |
| --- | --- |
| Réduction min/max | L'impulsion d'un échantillon reste présente jusqu'au niveau final; le canal stéréo silencieux garde min=max=0. |
| Timing | Les plages sont demi-ouvertes et converties en indices couvrant la plage. |
| Cache | Round-trip, changement de révision, contenu tronqué, publication dans son répertoire, et invalidation des seules anciennes révisions testés. |
| Audio court | Copie synthétique 3 s, nom accentué/espaces/apostrophe, ffprobe et cache testés; la source conserve SHA-256 `f95cf15299c1238233ebbcf2349fea54aa6f1195d33de52f052096de4e333e15`. 150 bins de 20 ms et neuf niveaux jusqu'à un bin. |
| PlayerService | Seek / protocoles A/B, bornes invalides et effacement lors du changement de piste testés avec fake backend. |
| UI QML | `WaveformView` et ses contrôles se chargent dans Fullscreen player de démo; la vue garde le même état de lecture. Aucun lecteur mpv réel n'est remplacé. |
| Ciblé | 20 tests dédiés reduction/timing/cache/player/UI réussis. `ruff check .`, `ruff format --check .` (187 fichiers) et `pyright` réussis (0 erreur, avertissement ou information). |
| Suite complète | `uv run pytest -q` code 0, deux tests sautés. Plusieurs tests impriment `Windows fatal exception: code 0xe24c4a02` dans le thread `_event_loop` de libmpv. Un essai précédent s'est terminé avec trace d'accès violation; un nouveau run complet a fini code 0. Cause non attribuée, aucun correctif de crash revendiqué. |

## Paquet Windows

Rebuild `pwsh -NoProfile -File scripts/build_windows.ps1` réussi sous Windows 11
10.0.26200, Python 3.12.14 et PyInstaller 6.22.2. `MTEE.exe` fait 2,36 Mo.
Copie externe
`%TEMP%\MTEE-08-final-a92527c89f864576bee8adcc5ee8f819`: 1 972 fichiers,
413 059 197 octets, exactement un `ffmpeg.exe` et un `ffprobe.exe`. Smoke-test
avec un `--data-dir` temporaire isolé: code 0. La copie a aussi généré la
waveform courte depuis le runtime embarqué et laissé le SHA-256 de la source
copiée inchangé.

L'interface native interactive n'a pas été parcourue: l'outil computer-use
disponible dans cette session indique que les commandes d'applications natives
sont désactivées. Les tests de chargement QML sont automatisés, pas une recette
souris/clavier sur la fenêtre du paquet.

## Mesures et limites restantes

Fixture synthétique de deux heures (mono, MP3 32 kbit/s, 28 800 435 octets),
traitée à 22,05 kHz stéréo depuis le paquet copié : 7 200 000 000 µs,
360 000 bins de 20 ms, 20 niveaux jusqu'à un bin, 93,57 s de décodage,
24 885 octets de cache compressé. Le processus Python a été observé avec un
working set d'environ 66 MiB pendant le décodage; ce relevé ponctuel n'est pas
un pic instrumenté. SHA-256 source inchangé :
`01d9f1a1e8c9a912f4b5ccc722cb1b593290db4c276b78d701c73289b9b46fc3`.
La fixture et son cache restent dans `%TEMP%`; aucune collection utilisateur.
La timeline affichée est construite en bins de 20 ms; le plan et le code ne
promettent pas de seek à l'échantillon près. La précision réelle de A/B,
l'annulation visible pendant génération, les facteurs DPI, le retour de la vue
après utilisation manuelle, et le test sur installation Windows propre ne sont
pas réalisés. Une tentative d'observer le tour A/B pendant la lecture n'a pas
permis de conclure car libmpv cessait de publier des positions et émettait
l'exception native ci-dessus; les commandes sont prouvées par test unitaire,
pas la précision du moteur de boucle.
