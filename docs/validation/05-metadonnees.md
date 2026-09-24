# Validation du plan 05 — Édition manuelle des métadonnées

Date : 2026-09-24. Environnement : Windows x86-64, Python 3.12.14,
PySide 6.9.3, Mutagen 1.48.1 tel que verrouillé par uv. Tous les fichiers
modifiés par les tests sont générés sous les répertoires pytest temporaires.
Aucun fichier audio personnel n'a été utilisé.

## Portée d'écriture réellement activée

| Source | Champs | Résultat |
| --- | --- | --- |
| WAV PCM avec ID3v2.4 | Title, Artist, Album, Genre, Date, Comment, Track number, BPM, Key | Un seul slot et une seule valeur par champ. |
| WAV avec ID3v2.3 | Tous | Lecture seule. |
| WAV non PCM | Tous | Lecture seule. |
| MP3, AIFF, FLAC, Vorbis, Opus, MP4 et AAC | Tous | Lecture seule, faute d'essais d'écriture avec corpus autorisé. |

Un commentaire n'est éditable que lorsque son slot est sans ambiguïté ; les
commentaires d'autres langues ou descriptions ne sont pas réécrits. Une date
avec `TDRC` et `TYER` simultanés reste désactivée. Track number conserve le
total après `/`. Mixed values ne devient jamais une valeur de tag. Ces limites
sont affichées dans l'interface et détaillées dans
[la matrice des métadonnées](../metadata-mapping.md).

## Résultats automatisés

| Contrôle | Résultat observé |
| --- | --- |
| Ruff | Réussi : `All checks passed!` |
| Format Ruff | Réussi : 121 fichiers déjà formatés |
| Pyright | Réussi : 0 erreur, 0 avertissement, 0 information |
| Suite hors `native_audio` | Réussi : 148 passés, 2 ignorés, 1 test natif exclu, 18,86 s |
| Test natif libmpv isolé | Réussi : 1 passé, 0,14 s ; il vérifie le lecteur sur WAV PCM synthétique, pas l'édition. |
| Tests UI ciblés | Réussi : 10 passés, dont chargement QML, lecteur plein écran, saisie capturée sur la sélection initiale et résultat partiel d'une sélection de formats mixtes. |
| Migration 004 | Réussi : base v3 sauvegardée avant migration, données de réglage conservées. |

Deux exécutions de toute la suite dans un seul processus n'ont pas abouti : la
première est restée bloquée dans le test libmpv ; dans la seconde, libmpv a
passé, puis le premier test UI d'application n'a pas terminé en 30 secondes.
Les deux sous-ensembles passent séparément. Le résultat combiné n'est donc pas
présenté comme une suite complète réussie.

Les intégrations génèrent et modifient un WAV temporaire. Elles vérifient les
octets PCM, le taux d'échantillonnage, les frames TXXX, COMM et APIC, le total
des pistes, la suppression explicite d'un champ, les slots multiples en
lecture seule, le conflit de révision, le verrou de lecture du lecteur, Undo
après réouverture SQLite et la conservation de la sauvegarde après une panne
injectée entre `ReplaceFileW` et le commit SQLite. Le journal indique alors
`needs_recovery`, l'UI bloque une autre écriture sur cette piste et l'état
réel `replacement_present` est détecté au démarrage.

## Recette manuelle et distribution

Le build PyInstaller 6.22.2 a réussi sous Windows 11 x86-64 :
`dist/MTEE/MTEE.exe` (2,21 MB). L'EXE final lancé avec
`--data-dir .local/validation/05-package-final2 --smoke-test` a retourné 0 ;
la base isolée a `user_version=4` et contient `metadata_edit_operations`.
Cela valide le chargement et la migration embarquée sur ce poste, pas une
édition interactive dans le paquet ni un démarrage sur Windows propre.

La vérification interactive d'une saisie dans une vraie fenêtre Windows n'a
pas été effectuée dans cette exécution. Les tests offscreen vérifient le QML
et le routage asynchrone, mais ne remplacent pas une recette souris/clavier.

## Limites restantes

- La matrice n'est pas complète et aucun codec autre que PCM WAV n'est
  modifiable.
- Les tests permission refusée, attribut lecture seule, disque absent et
  manque d'espace ne sont pas exécutés.
- Une opération `needs_recovery` est détectée et signalée, mais MTEE ne propose
  pas encore de procédure interactive pour choisir entre restauration et
  confirmation de la nouvelle source.
- L'essai manuel de l'application et l'acceptation d'une distribution sur un
  Windows propre restent à faire.
